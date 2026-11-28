from pathlib import Path
import sys

# Ensure backend package imports work regardless of working directory
BACKEND_DIR = Path(__file__).resolve().parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from mcp.server.mcpserver import MCPServer
from sqlalchemy.orm import joinedload

from app.db.models import CallLog, Company, Match, Student
from app.db.session import SessionLocal
from app.services.matching_service import run_hybrid_matching
from app.services.notification_service import send_match_details_email
from app.services.vapi_service import trigger_outbound_vapi_call

mcp = MCPServer(
    name="placecall-ai",
    instructions=(
        "PlaceCall AI MCP Server for managing campus placement students, company drives, "
        "resume-to-JD matching, email notifications, and Vapi outbound phone calls."
    ),
)


@mcp.tool()
def list_students(
    branch: str | None = None,
    min_cgpa: float | None = None,
    call_consent: bool | None = None,
) -> list[dict]:
    """List registered students with their branch, CGPA, phone, email, active resume, and parsed skills."""
    db = SessionLocal()
    try:
        query = db.query(Student).options(
            joinedload(Student.user),
            joinedload(Student.resumes),
        )
        if branch:
            query = query.filter(Student.branch.ilike(branch.strip()))
        if min_cgpa is not None:
            query = query.filter(Student.cgpa >= min_cgpa)
        if call_consent is not None:
            query = query.filter(Student.call_consent.is_(call_consent))

        rows = query.order_by(Student.created_at.desc()).all()
        output = []
        for s in rows:
            active_resume = next((r for r in s.resumes if r.is_active), None)
            skills = []
            if active_resume and isinstance(active_resume.parsed_skills, dict):
                skills = active_resume.parsed_skills.get("skills", []) or []
            output.append(
                {
                    "student_id": s.id,
                    "name": s.user.name,
                    "email": s.user.email,
                    "phone": s.phone,
                    "branch": s.branch,
                    "cgpa": float(s.cgpa),
                    "call_consent": s.call_consent,
                    "has_active_resume": active_resume is not None,
                    "skills": skills,
                }
            )
        return output
    finally:
        db.close()


@mcp.tool()
def list_companies() -> list[dict]:
    """List all published company placement drives."""
    db = SessionLocal()
    try:
        companies = db.query(Company).order_by(Company.created_at.desc()).all()
        return [
            {
                "company_id": c.id,
                "company_name": c.company_name,
                "role": c.role,
                "min_cgpa": float(c.min_cgpa),
                "eligible_branches": c.eligible_branches,
                "ctc": c.ctc,
                "deadline": str(c.deadline) if c.deadline else None,
                "registration_url": c.registration_url,
            }
            for c in companies
        ]
    finally:
        db.close()


@mcp.tool()
def run_company_matching(company_id: int, min_fit_score: int = 70) -> list[dict]:
    """Run 3-stage hybrid SQL + pgvector + LangChain matching for a company drive."""
    db = SessionLocal()
    try:
        company = db.query(Company).filter(Company.id == company_id).first()
        if not company:
            return [{"error": f"Company {company_id} not found"}]
        matches = run_hybrid_matching(db, company=company, min_fit_score=min_fit_score)
        return [
            {
                "match_id": m.id,
                "student_name": m.student.user.name,
                "student_email": m.student.user.email,
                "student_phone": m.student.phone,
                "company_name": m.company.company_name,
                "role": m.company.role,
                "fit_score": m.fit_score,
                "missing_skills": m.missing_skills or [],
                "match_pitch": m.match_pitch,
                "match_status": m.match_status,
            }
            for m in matches
        ]
    finally:
        db.close()


@mcp.tool()
def list_matches(
    company_id: int | None = None,
    min_fit_score: int | None = None,
) -> list[dict]:
    """List student-to-company matches stored in PostgreSQL."""
    db = SessionLocal()
    try:
        query = db.query(Match).options(
            joinedload(Match.student).joinedload(Student.user),
            joinedload(Match.company),
        )
        if company_id is not None:
            query = query.filter(Match.company_id == company_id)
        if min_fit_score is not None:
            query = query.filter(Match.fit_score >= min_fit_score)
        matches = query.order_by(Match.fit_score.desc(), Match.created_at.desc()).all()
        return [
            {
                "match_id": m.id,
                "student_name": m.student.user.name,
                "student_email": m.student.user.email,
                "student_phone": m.student.phone,
                "company_name": m.company.company_name,
                "role": m.company.role,
                "fit_score": m.fit_score,
                "missing_skills": m.missing_skills or [],
                "match_pitch": m.match_pitch,
                "match_status": m.match_status,
            }
            for m in matches
        ]
    finally:
        db.close()


@mcp.tool()
def send_match_email(match_id: int) -> dict:
    """Send complete match analysis, job description, and registration link to the student's email."""
    db = SessionLocal()
    try:
        m = (
            db.query(Match)
            .options(
                joinedload(Match.student).joinedload(Student.user),
                joinedload(Match.resume),
                joinedload(Match.company),
            )
            .filter(Match.id == match_id)
            .first()
        )
        if not m:
            return {"status": "ERROR", "error": f"Match {match_id} not found"}

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
        return {
            "match_id": m.id,
            "student_name": m.student.user.name,
            "email": m.student.user.email,
            "status": "SENT" if ok else "FAILED",
            "error": err,
        }
    finally:
        db.close()


@mcp.tool()
def trigger_vapi_phone_call(match_id: int) -> dict:
    """Place an outbound Vapi phone call to a matched student with resume & JD context injected."""
    db = SessionLocal()
    try:
        m = (
            db.query(Match)
            .options(
                joinedload(Match.student).joinedload(Student.user),
                joinedload(Match.resume),
                joinedload(Match.company),
            )
            .filter(Match.id == match_id)
            .first()
        )
        if not m:
            return {"status": "ERROR", "error": f"Match {match_id} not found"}
        if not m.student.call_consent:
            return {
                "match_id": m.id,
                "status": "SKIPPED_NO_CONSENT",
                "error": "Student has not opted in to automated calls.",
            }

        call_log = CallLog(
            match_id=m.id,
            student_id=m.student_id,
            company_id=m.company_id,
            call_status="INITIATED",
            student_outcome="UNKNOWN",
        )
        db.add(call_log)
        db.flush()

        try:
            vapi_call_id = trigger_outbound_vapi_call(db=db, match=m, call_log=call_log)
            call_log.twilio_call_sid = vapi_call_id
            m.match_status = "CALLED"
            db.commit()
            return {
                "match_id": m.id,
                "student_name": m.student.user.name,
                "phone": m.student.phone,
                "status": "INITIATED",
                "vapi_call_id": vapi_call_id,
            }
        except Exception as exc:
            call_log.call_status = "FAILED"
            db.commit()
            return {
                "match_id": m.id,
                "student_name": m.student.user.name,
                "phone": m.student.phone,
                "status": "FAILED",
                "error": str(exc),
            }
    finally:
        db.close()


@mcp.tool()
def list_call_logs(company_id: int | None = None) -> list[dict]:
    """List placement call logs, statuses, outcomes, durations, and transcripts."""
    db = SessionLocal()
    try:
        query = db.query(CallLog).options(
            joinedload(CallLog.student).joinedload(Student.user),
            joinedload(CallLog.company),
        )
        if company_id is not None:
            query = query.filter(CallLog.company_id == company_id)
        logs = query.order_by(CallLog.called_at.desc()).limit(25).all()
        return [
            {
                "call_log_id": c.id,
                "match_id": c.match_id,
                "student_name": c.student.user.name,
                "company_name": c.company.company_name,
                "call_status": c.call_status,
                "student_outcome": c.student_outcome,
                "duration_sec": c.duration_sec,
                "link_sent": c.link_sent,
                "transcript": c.transcript,
            }
            for c in logs
        ]
    finally:
        db.close()


if __name__ == "__main__":
    mcp.run(transport="stdio")
