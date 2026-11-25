from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.core.config import settings
from app.db.models import Company, Match, Resume, Student, User
from app.services.ai_engine import generate_match_reasoning


def _branch_is_eligible(student_branch: str | None, eligible_branches: list[str] | None) -> bool:
    if not eligible_branches:
        return True
    normalized = {b.strip().upper() for b in eligible_branches if b and b.strip()}
    if not normalized or "ALL" in normalized:
        return True
    if not student_branch:
        return False
    return student_branch.strip().upper() in normalized


def run_hybrid_matching(
    db: Session,
    company: Company,
    min_fit_score: int = settings.DEFAULT_FIT_THRESHOLD,
) -> list[Match]:
    """
    3-Stage Hybrid Resume-to-JD Matching Engine:
    Stage 1: SQL Hard Eligibility Filter (CGPA, branch, call_consent, active resume)
    Stage 2: pgvector cosine similarity ranking
    Stage 3: LangChain missing skills + 2-sentence personalized match pitch
    """
    if company.jd_embedding is None:
        raise ValueError("Company JD does not have a vector embedding yet.")

    similarity_expr = (1 - Resume.embedding.cosine_distance(company.jd_embedding)).label(
        "cosine_sim"
    )

    stmt = (
        select(Student, User, Resume, similarity_expr)
        .join(User, Student.user_id == User.id)
        .join(Resume, (Resume.student_id == Student.id) & (Resume.is_active.is_(True)))
        .where(Student.cgpa >= company.min_cgpa)
        .where(Student.call_consent.is_(True))
        .where(Resume.embedding.is_not(None))
        .order_by(similarity_expr.desc())
    )

    rows = db.execute(stmt).all()
    matched_records: list[Match] = []

    for student, user, resume, cosine_sim in rows:
        if not _branch_is_eligible(student.branch, company.eligible_branches):
            continue

        sim_val = float(cosine_sim or 0.0)
        # Calibrate MiniLM-L6-v2 cosine similarity (typically 0.15..0.75 for resume-vs-JD) into 0-100
        vector_score = max(0, min(100, int(round(((sim_val - 0.15) / 0.60) * 100))))

        # Pre-filter only clearly unrelated resumes before invoking LangChain reasoning
        if vector_score < max(25, min_fit_score - 35):
            continue

        reasoning = generate_match_reasoning(
            student_name=user.name,
            branch=student.branch,
            cgpa=float(student.cgpa),
            parsed_skills=resume.parsed_skills,
            resume_text=resume.raw_text,
            company_name=company.company_name,
            role=company.role,
            jd_text=company.jd_text,
            vector_score=vector_score,
        )

        # Blend calibrated pgvector similarity (40%) and LLM technical alignment (60%)
        blended_score = max(
            0,
            min(100, int(round(0.4 * vector_score + 0.6 * reasoning.llm_alignment_score))),
        )
        if blended_score < min_fit_score:
            continue

        existing = (
            db.query(Match)
            .filter(
                Match.student_id == student.id,
                Match.company_id == company.id,
            )
            .first()
        )
        if existing:
            existing.resume_id = resume.id
            existing.fit_score = blended_score
            existing.missing_skills = reasoning.missing_skills
            existing.match_pitch = reasoning.match_pitch
            match_obj = existing
        else:
            match_obj = Match(
                student_id=student.id,
                resume_id=resume.id,
                company_id=company.id,
                fit_score=blended_score,
                missing_skills=reasoning.missing_skills,
                match_pitch=reasoning.match_pitch,
                match_status="PENDING_CALL",
            )
            db.add(match_obj)

        db.flush()
        matched_records.append(match_obj)

    db.commit()

    # Reload with relationships for clean serialization
    if not matched_records:
        return []
    ids = [m.id for m in matched_records]
    return (
        db.query(Match)
        .options(
            joinedload(Match.student).joinedload(Student.user),
            joinedload(Match.company),
        )
        .filter(Match.id.in_(ids))
        .order_by(Match.fit_score.desc())
        .all()
    )
