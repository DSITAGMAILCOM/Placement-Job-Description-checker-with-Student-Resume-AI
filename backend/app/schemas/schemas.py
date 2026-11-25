from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, EmailStr, Field


# ── Auth ──────────────────────────────────────────────────────────────────────

class SignupRequest(BaseModel):
    name: str = Field(..., min_length=2, max_length=100)
    email: EmailStr
    password: str = Field(..., min_length=6, max_length=128)
    role: Literal["ADMIN", "STUDENT"] = "STUDENT"
    phone: str | None = Field(default=None, max_length=20)
    branch: str | None = Field(default=None, max_length=50)
    cgpa: Decimal | None = Field(default=None, ge=0, le=10)
    graduation_year: int | None = Field(default=None, ge=2020, le=2035)
    call_consent: bool = False


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class StudentProfileOut(BaseModel):
    id: int
    phone: str
    branch: str | None
    cgpa: float
    graduation_year: int | None
    call_consent: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class UserOut(BaseModel):
    id: int
    name: str
    email: EmailStr
    role: str
    created_at: datetime
    student: StudentProfileOut | None = None

    model_config = {"from_attributes": True}


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


# ── Student & Resume ──────────────────────────────────────────────────────────

class StudentProfileUpdate(BaseModel):
    phone: str = Field(..., min_length=7, max_length=20)
    branch: str = Field(..., min_length=1, max_length=50)
    cgpa: Decimal = Field(..., ge=0, le=10)
    graduation_year: int | None = Field(default=None, ge=2020, le=2035)
    call_consent: bool = True


class ParsedResumeData(BaseModel):
    skills: list[str] = Field(default_factory=list)
    projects: list[str] = Field(default_factory=list)
    education: list[str] = Field(default_factory=list)
    summary: str = ""


class ResumeOut(BaseModel):
    id: int
    student_id: int
    file_name: str | None
    parsed_skills: dict | list | None
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class StudentAdminOut(BaseModel):
    id: int
    user_id: int
    name: str
    email: str
    phone: str
    branch: str | None
    cgpa: float
    graduation_year: int | None
    call_consent: bool
    has_active_resume: bool
    parsed_skills: list[str] = Field(default_factory=list)
    created_at: datetime


# ── Company & Matching ────────────────────────────────────────────────────────

class CompanyCreate(BaseModel):
    company_name: str = Field(..., min_length=1, max_length=150)
    role: str = Field(..., min_length=1, max_length=150)
    min_cgpa: Decimal = Field(default=Decimal("0.00"), ge=0, le=10)
    eligible_branches: list[str] = Field(default_factory=list)
    ctc: str | None = Field(default=None, max_length=50)
    deadline: date | None = None
    registration_url: str | None = None
    jd_text: str = Field(..., min_length=20)


class CompanyOut(BaseModel):
    id: int
    company_name: str
    role: str
    min_cgpa: float
    eligible_branches: list[str] | None
    ctc: str | None
    deadline: date | None
    registration_url: str | None
    jd_text: str
    created_at: datetime

    model_config = {"from_attributes": True}


class MatchRunRequest(BaseModel):
    min_fit_score: int = Field(default=70, ge=0, le=100)


class MatchOut(BaseModel):
    id: int
    student_id: int
    student_name: str
    student_email: str
    student_phone: str
    student_branch: str | None
    student_cgpa: float
    call_consent: bool
    resume_id: int
    company_id: int
    company_name: str
    company_role: str
    company_ctc: str | None
    company_deadline: date | None
    registration_url: str | None
    fit_score: int
    missing_skills: list[str]
    match_pitch: str | None
    match_status: str
    created_at: datetime


# ── Calling & Logs ────────────────────────────────────────────────────────────

class CallTriggerRequest(BaseModel):
    match_id: int | None = None
    match_ids: list[int] | None = None
    company_id: int | None = None
    min_fit_score: int = Field(default=70, ge=0, le=100)


class CallTriggerResult(BaseModel):
    match_id: int
    student_name: str
    phone: str
    status: str
    twilio_call_sid: str | None = None
    error: str | None = None


class SendMatchEmailRequest(BaseModel):
    match_id: int | None = None
    match_ids: list[int] | None = None
    company_id: int | None = None
    min_fit_score: int = Field(default=70, ge=0, le=100)


class SendMatchEmailResult(BaseModel):
    match_id: int
    student_name: str
    email: str
    status: str
    error: str | None = None


class CallLogOut(BaseModel):
    id: int
    match_id: int
    student_id: int
    student_name: str
    company_id: int
    company_name: str
    company_role: str
    twilio_call_sid: str | None
    call_status: str
    student_outcome: str
    transcript: str | None
    duration_sec: int | None
    link_sent: bool
    called_at: datetime


# ── Dashboard ─────────────────────────────────────────────────────────────────

class CompanyConversionMetric(BaseModel):
    company_id: int
    company_name: str
    role: str
    matched_count: int
    calls_placed: int
    answered_count: int
    interested_count: int
    conversion_rate: float


class DashboardSummaryOut(BaseModel):
    total_students: int
    active_drives: int
    total_matches: int
    calls_placed: int
    answer_rate: float
    interested_rate: float
    company_metrics: list[CompanyConversionMetric]
