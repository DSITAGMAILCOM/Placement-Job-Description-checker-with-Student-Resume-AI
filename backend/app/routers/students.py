from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from sqlalchemy.orm import Session, joinedload

from app.core.security import require_admin, require_student
from app.db.models import Resume, Student, User
from app.db.session import get_db
from app.schemas.schemas import (
    ResumeOut,
    StudentAdminOut,
    StudentProfileOut,
    StudentProfileUpdate,
)
from app.services.ai_engine import extract_resume_structure
from app.services.embedding_service import generate_embedding
from app.services.pdf_service import extract_text_from_pdf

router = APIRouter(tags=["Students & Resumes"])


@router.put("/students/profile", response_model=StudentProfileOut)
def update_student_profile(
    payload: StudentProfileUpdate,
    current_user: User = Depends(require_student),
    db: Session = Depends(get_db),
):
    student = db.query(Student).filter(Student.user_id == current_user.id).first()
    if not student:
        student = Student(
            user_id=current_user.id,
            phone=payload.phone.strip(),
            branch=payload.branch.strip().upper(),
            cgpa=payload.cgpa,
            graduation_year=payload.graduation_year,
            call_consent=payload.call_consent,
        )
        db.add(student)
    else:
        student.phone = payload.phone.strip()
        student.branch = payload.branch.strip().upper()
        student.cgpa = payload.cgpa
        student.graduation_year = payload.graduation_year
        student.call_consent = payload.call_consent

    db.commit()
    db.refresh(student)
    return StudentProfileOut.model_validate(student)


@router.get("/students", response_model=list[StudentAdminOut])
def list_students(
    branch: str | None = Query(default=None),
    min_cgpa: float | None = Query(default=None, ge=0, le=10),
    call_consent: bool | None = Query(default=None),
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
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

    students = query.order_by(Student.created_at.desc()).all()
    results: list[StudentAdminOut] = []
    for s in students:
        active_resume = next((r for r in s.resumes if r.is_active), None)
        skills: list[str] = []
        if active_resume and isinstance(active_resume.parsed_skills, dict):
            skills = active_resume.parsed_skills.get("skills", []) or []
        elif active_resume and isinstance(active_resume.parsed_skills, list):
            skills = active_resume.parsed_skills

        results.append(
            StudentAdminOut(
                id=s.id,
                user_id=s.user_id,
                name=s.user.name,
                email=s.user.email,
                phone=s.phone,
                branch=s.branch,
                cgpa=float(s.cgpa),
                graduation_year=s.graduation_year,
                call_consent=s.call_consent,
                has_active_resume=active_resume is not None,
                parsed_skills=skills,
                created_at=s.created_at,
            )
        )
    return results


@router.post("/resumes/upload", response_model=ResumeOut, status_code=status.HTTP_201_CREATED)
async def upload_resume(
    file: UploadFile = File(...),
    current_user: User = Depends(require_student),
    db: Session = Depends(get_db),
):
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only PDF files are supported.",
        )

    student = db.query(Student).filter(Student.user_id == current_user.id).first()
    if not student:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Please complete your student profile before uploading a resume.",
        )

    pdf_bytes = await file.read()
    try:
        raw_text = extract_text_from_pdf(pdf_bytes)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    parsed = extract_resume_structure(raw_text)
    embedding = generate_embedding(raw_text)

    # Archive any previous active resume
    db.query(Resume).filter(
        Resume.student_id == student.id,
        Resume.is_active.is_(True),
    ).update({"is_active": False})

    resume = Resume(
        student_id=student.id,
        file_name=file.filename,
        raw_text=raw_text,
        parsed_skills=parsed.model_dump(),
        embedding=embedding,
        is_active=True,
    )
    db.add(resume)
    db.commit()
    db.refresh(resume)
    return ResumeOut.model_validate(resume)


@router.get("/resumes/active", response_model=ResumeOut | None)
def get_active_resume(
    current_user: User = Depends(require_student),
    db: Session = Depends(get_db),
):
    student = db.query(Student).filter(Student.user_id == current_user.id).first()
    if not student:
        return None
    resume = (
        db.query(Resume)
        .filter(Resume.student_id == student.id, Resume.is_active.is_(True))
        .order_by(Resume.created_at.desc())
        .first()
    )
    if not resume:
        return None
    return ResumeOut.model_validate(resume)
