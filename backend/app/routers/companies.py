from datetime import date
from decimal import Decimal
import json

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile, status
from sqlalchemy.orm import Session, joinedload

from app.core.config import settings
from app.core.security import get_current_user, require_admin
from app.db.models import Company, Match, Student, User
from app.db.session import get_db
from app.schemas.schemas import (
    CompanyCreate,
    CompanyOut,
    MatchOut,
    MatchRunRequest,
    SendMatchEmailRequest,
    SendMatchEmailResult,
)
from app.services.embedding_service import generate_embedding
from app.services.matching_service import run_hybrid_matching
from app.services.notification_service import send_match_details_email
from app.services.pdf_service import extract_text_from_pdf

router = APIRouter(tags=["Companies & Matching"])


def _serialize_match(m: Match) -> MatchOut:
    return MatchOut(
        id=m.id,
        student_id=m.student_id,
        student_name=m.student.user.name,
        student_email=m.student.user.email,
        student_phone=m.student.phone,
        student_branch=m.student.branch,
        student_cgpa=float(m.student.cgpa),
        call_consent=m.student.call_consent,
        resume_id=m.resume_id,
        company_id=m.company_id,
        company_name=m.company.company_name,
        company_role=m.company.role,
        company_ctc=m.company.ctc,
        company_deadline=m.company.deadline,
        registration_url=m.company.registration_url,
        fit_score=m.fit_score,
        missing_skills=m.missing_skills or [],
        match_pitch=m.match_pitch,
        match_status=m.match_status,
        created_at=m.created_at,
    )


@router.post("/companies", response_model=CompanyOut, status_code=status.HTTP_201_CREATED)
async def create_company(
    request: Request,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Create a new company drive from either application/json or multipart/form-data (with optional JD PDF)."""
    content_type = request.headers.get("content-type", "")
    if "multipart/form-data" in content_type:
        form = await request.form()
        company_name = str(form.get("company_name", "")).strip()
        role = str(form.get("role", "")).strip()
        min_cgpa = Decimal(str(form.get("min_cgpa") or "0.00"))
        raw_branches = str(form.get("eligible_branches") or "[]")
        try:
            eligible_branches = json.loads(raw_branches) if raw_branches.startswith("[") else [
                b.strip() for b in raw_branches.split(",") if b.strip()
            ]
        except Exception:
            eligible_branches = [b.strip() for b in raw_branches.split(",") if b.strip()]
        ctc = str(form.get("ctc") or "").strip() or None
        deadline_raw = str(form.get("deadline") or "").strip()
        deadline = date.fromisoformat(deadline_raw) if deadline_raw else None
        registration_url = str(form.get("registration_url") or "").strip() or None
        jd_text = str(form.get("jd_text") or "").strip()
        jd_file = form.get("jd_file")
        if isinstance(jd_file, UploadFile) or hasattr(jd_file, "read"):
            pdf_bytes = await jd_file.read()
            if pdf_bytes:
                try:
                    extracted = extract_text_from_pdf(pdf_bytes)
                    jd_text = f"{jd_text}\n\n{extracted}".strip() if jd_text else extracted
                except ValueError as exc:
                    raise HTTPException(status_code=400, detail=str(exc)) from exc
        if not company_name or not role or len(jd_text) < 20:
            raise HTTPException(
                status_code=400,
                detail="company_name, role, and job description text/PDF (min 20 chars) are required.",
            )
    else:
        body = await request.json()
        payload = CompanyCreate(**body)
        company_name = payload.company_name.strip()
        role = payload.role.strip()
        min_cgpa = payload.min_cgpa
        eligible_branches = [b.strip().upper() for b in payload.eligible_branches if b.strip()]
        ctc = payload.ctc
        deadline = payload.deadline
        registration_url = payload.registration_url
        jd_text = payload.jd_text.strip()

    jd_embedding = generate_embedding(f"{company_name} {role}\n{jd_text}")

    company = Company(
        created_by=current_user.id,
        company_name=company_name,
        role=role,
        min_cgpa=min_cgpa,
        eligible_branches=eligible_branches,
        ctc=ctc,
        deadline=deadline,
        registration_url=registration_url,
        jd_text=jd_text,
        jd_embedding=jd_embedding,
    )
    db.add(company)
    db.commit()
    db.refresh(company)
    return CompanyOut.model_validate(company)


@router.get("/companies", response_model=list[CompanyOut])
def list_companies(
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    companies = db.query(Company).order_by(Company.created_at.desc()).all()
    return [CompanyOut.model_validate(c) for c in companies]


@router.get("/companies/{company_id}", response_model=CompanyOut)
def get_company(
    company_id: int,
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    company = db.query(Company).filter(Company.id == company_id).first()
    if not company:
        raise HTTPException(status_code=404, detail="Company drive not found.")
    return CompanyOut.model_validate(company)


@router.post("/companies/{company_id}/match", response_model=list[MatchOut])
def match_company_candidates(
    company_id: int,
    payload: MatchRunRequest | None = None,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    company = db.query(Company).filter(Company.id == company_id).first()
    if not company:
        raise HTTPException(status_code=404, detail="Company drive not found.")

    threshold = payload.min_fit_score if payload else settings.DEFAULT_FIT_THRESHOLD
    matches = run_hybrid_matching(db, company=company, min_fit_score=threshold)
    return [_serialize_match(m) for m in matches]


@router.get("/matches", response_model=list[MatchOut])
def list_matches(
    company_id: int | None = Query(default=None),
    min_score: int | None = Query(default=None, ge=0, le=100),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    query = db.query(Match).options(
        joinedload(Match.student).joinedload(Student.user),
        joinedload(Match.company),
    )

    if current_user.role == "STUDENT":
        student = db.query(Student).filter(Student.user_id == current_user.id).first()
        if not student:
            return []
        query = query.filter(Match.student_id == student.id)
    else:
        if company_id is not None:
            query = query.filter(Match.company_id == company_id)

    if min_score is not None:
        query = query.filter(Match.fit_score >= min_score)

    matches = query.order_by(Match.fit_score.desc(), Match.created_at.desc()).all()
    return [_serialize_match(m) for m in matches]


@router.post("/matches/send-email", response_model=list[SendMatchEmailResult])
def send_match_emails(
    payload: SendMatchEmailRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Email complete match analysis, JD details, and registration link to matched student(s)."""
    query = db.query(Match).options(
        joinedload(Match.student).joinedload(Student.user),
        joinedload(Match.resume),
        joinedload(Match.company),
    )

    if current_user.role == "STUDENT":
        student = db.query(Student).filter(Student.user_id == current_user.id).first()
        if not student or payload.match_id is None:
            raise HTTPException(status_code=403, detail="Students can only email their own match.")
        query = query.filter(Match.id == payload.match_id, Match.student_id == student.id)
    elif payload.match_id is not None:
        query = query.filter(Match.id == payload.match_id)
    elif payload.match_ids:
        query = query.filter(Match.id.in_(payload.match_ids))
    elif payload.company_id is not None:
        query = query.filter(
            Match.company_id == payload.company_id,
            Match.fit_score >= payload.min_fit_score,
        )
    else:
        raise HTTPException(
            status_code=400,
            detail="Provide match_id, match_ids, or company_id to send match emails.",
        )

    matches = query.all()
    if not matches:
        raise HTTPException(status_code=404, detail="No matching records found.")

    results: list[SendMatchEmailResult] = []
    for m in matches:
        parsed = m.resume.parsed_skills if m.resume else {}
        matched_skills = (
            parsed.get("skills", [])
            if isinstance(parsed, dict)
            else (parsed if isinstance(parsed, list) else [])
        )
        ok, err = send_match_details_email(
            to_email=m.student.user.email,
            student_name=m.student.user.name,
            student_branch=m.student.branch,
            student_cgpa=float(m.student.cgpa),
            company_name=m.company.company_name,
            role=m.company.role,
            fit_score=m.fit_score,
            match_pitch=m.match_pitch,
            matched_skills=matched_skills,
            missing_skills=m.missing_skills or [],
            ctc=m.company.ctc,
            deadline=str(m.company.deadline) if m.company.deadline else None,
            registration_url=m.company.registration_url,
            jd_text=m.company.jd_text,
        )
        results.append(
            SendMatchEmailResult(
                match_id=m.id,
                student_name=m.student.user.name,
                email=m.student.user.email,
                status="SENT" if ok else "FAILED",
                error=err,
            )
        )
    return results
