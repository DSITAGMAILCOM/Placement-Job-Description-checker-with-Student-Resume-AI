from datetime import date, datetime
from decimal import Decimal

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    email: Mapped[str] = mapped_column(String(150), nullable=False, unique=True)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False, default="STUDENT")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    student: Mapped["Student | None"] = relationship(
        back_populates="user",
        uselist=False,
        cascade="all, delete-orphan",
    )
    created_companies: Mapped[list["Company"]] = relationship(back_populates="creator")


class Student(Base):
    __tablename__ = "students"
    __table_args__ = (Index("idx_students_user_id", "user_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )
    phone: Mapped[str] = mapped_column(String(20), nullable=False)
    branch: Mapped[str | None] = mapped_column(String(50), nullable=True)
    cgpa: Mapped[Decimal] = mapped_column(Numeric(3, 2), nullable=False)
    graduation_year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    call_consent: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    user: Mapped["User"] = relationship(back_populates="student")
    resumes: Mapped[list["Resume"]] = relationship(
        back_populates="student",
        cascade="all, delete-orphan",
    )
    matches: Mapped[list["Match"]] = relationship(
        back_populates="student",
        cascade="all, delete-orphan",
    )
    call_logs: Mapped[list["CallLog"]] = relationship(
        back_populates="student",
        cascade="all, delete-orphan",
    )


class Resume(Base):
    __tablename__ = "resumes"
    __table_args__ = (
        Index("idx_resumes_student_id", "student_id"),
        Index(
            "idx_resumes_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_with={"m": 16, "ef_construction": 64},
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    student_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("students.id", ondelete="CASCADE"),
        nullable=False,
    )
    file_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    raw_text: Mapped[str] = mapped_column(Text, nullable=False)
    parsed_skills: Mapped[dict | list | None] = mapped_column(JSONB, nullable=True)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(384), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    student: Mapped["Student"] = relationship(back_populates="resumes")
    matches: Mapped[list["Match"]] = relationship(
        back_populates="resume",
        cascade="all, delete-orphan",
    )


class Company(Base):
    __tablename__ = "companies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    created_by: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    company_name: Mapped[str] = mapped_column(String(150), nullable=False)
    role: Mapped[str] = mapped_column(String(150), nullable=False)
    min_cgpa: Mapped[Decimal] = mapped_column(
        Numeric(3, 2), default=Decimal("0.00"), nullable=False
    )
    eligible_branches: Mapped[list[str] | None] = mapped_column(JSONB, nullable=True)
    ctc: Mapped[str | None] = mapped_column(String(50), nullable=True)
    deadline: Mapped[date | None] = mapped_column(Date, nullable=True)
    registration_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    jd_text: Mapped[str] = mapped_column(Text, nullable=False)
    jd_embedding: Mapped[list[float] | None] = mapped_column(Vector(384), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    creator: Mapped["User | None"] = relationship(back_populates="created_companies")
    matches: Mapped[list["Match"]] = relationship(
        back_populates="company",
        cascade="all, delete-orphan",
    )
    call_logs: Mapped[list["CallLog"]] = relationship(
        back_populates="company",
        cascade="all, delete-orphan",
    )


class Match(Base):
    __tablename__ = "matches"
    __table_args__ = (Index("idx_matches_company_score", "company_id", "fit_score"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    student_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("students.id", ondelete="CASCADE"),
        nullable=False,
    )
    resume_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("resumes.id", ondelete="CASCADE"),
        nullable=False,
    )
    company_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
    )
    fit_score: Mapped[int] = mapped_column(Integer, nullable=False)
    missing_skills: Mapped[list[str] | None] = mapped_column(JSONB, nullable=True)
    match_pitch: Mapped[str | None] = mapped_column(Text, nullable=True)
    match_status: Mapped[str] = mapped_column(
        String(30), default="PENDING_CALL", nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    student: Mapped["Student"] = relationship(back_populates="matches")
    resume: Mapped["Resume"] = relationship(back_populates="matches")
    company: Mapped["Company"] = relationship(back_populates="matches")
    call_logs: Mapped[list["CallLog"]] = relationship(
        back_populates="match",
        cascade="all, delete-orphan",
    )


class CallLog(Base):
    __tablename__ = "call_logs"
    __table_args__ = (
        Index("idx_call_logs_match_id", "match_id"),
        Index("idx_call_logs_twilio_sid", "twilio_call_sid"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    match_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("matches.id", ondelete="CASCADE"),
        nullable=False,
    )
    student_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("students.id", ondelete="CASCADE"),
        nullable=False,
    )
    company_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
    )
    twilio_call_sid: Mapped[str | None] = mapped_column(
        String(100), unique=True, nullable=True
    )
    call_status: Mapped[str] = mapped_column(
        String(30), default="INITIATED", nullable=False
    )
    student_outcome: Mapped[str] = mapped_column(
        String(30), default="UNKNOWN", nullable=False
    )
    transcript: Mapped[str | None] = mapped_column(Text, nullable=True)
    duration_sec: Mapped[int | None] = mapped_column(Integer, nullable=True)
    link_sent: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    called_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    match: Mapped["Match"] = relationship(back_populates="call_logs")
    student: Mapped["Student"] = relationship(back_populates="call_logs")
    company: Mapped["Company"] = relationship(back_populates="call_logs")
