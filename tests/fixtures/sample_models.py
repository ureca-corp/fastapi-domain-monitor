"""
파서 테스트용 샘플 모델 파일.
academy-management-system의 실제 패턴을 최소화하여 재현.
"""
from enum import StrEnum
from typing import Optional
from uuid import UUID

from sqlalchemy import DateTime, Enum as SAEnum, Column
from sqlmodel import JSON, Field, Relationship, SQLModel


# ── Enums ────────────────────────────────────────────────────


class ActiveStatus(StrEnum):
    ACTIVE = "active"
    INACTIVE = "inactive"


class AccountRole(StrEnum):
    TEACHER = "teacher"
    STUDENT = "student"


class GradingStatus(StrEnum):
    GRADED = "graded"
    PENDING_REVIEW = "pending_review"


# ── Join Table ───────────────────────────────────────────────


class StudentClass(SQLModel, table=True):
    """원생-반 N:M 조인 테이블"""
    __tablename__ = "student_classes"

    id: UUID = Field(primary_key=True)
    student_id: UUID = Field(foreign_key="students.id", index=True)
    class_id: UUID = Field(foreign_key="classes.id", index=True)


# ── BaseModel 상속 (id, created_at, updated_at, deleted_at 포함) ───────


class Account(SQLModel, table=True):
    """계정 (BaseModel 상속 시뮬레이션)"""
    __tablename__ = "accounts"

    id: UUID = Field(primary_key=True)
    login_id: str = Field(max_length=50, unique=True)
    password_hash: str = Field(max_length=255)
    active_status: str = Field(default=ActiveStatus.ACTIVE, max_length=20)
    role: str = Field(max_length=20)

    teacher: Optional["Teacher"] = Relationship(
        back_populates="account",
        sa_relationship_kwargs={"uselist": False},
    )
    student: Optional["Student"] = Relationship(
        back_populates="account",
        sa_relationship_kwargs={"uselist": False},
    )


class Teacher(SQLModel, table=True):
    __tablename__ = "teachers"

    id: UUID = Field(primary_key=True)
    account_id: UUID = Field(foreign_key="accounts.id", unique=True)
    name: str = Field(max_length=100)

    account: Account = Relationship(back_populates="teacher")


class Student(SQLModel, table=True):
    __tablename__ = "students"

    id: UUID = Field(primary_key=True)
    account_id: UUID = Field(foreign_key="accounts.id", unique=True)
    name: str = Field(max_length=100)
    contact: str | None = Field(default=None, max_length=50)

    account: Account = Relationship(back_populates="student")
    classes: list["Class"] = Relationship(
        back_populates="students",
        link_model=StudentClass,
    )


class Class(SQLModel, table=True):
    __tablename__ = "classes"

    id: UUID = Field(primary_key=True)
    teacher_id: UUID = Field(foreign_key="teachers.id", index=True)
    name: str = Field(max_length=100)

    students: list[Student] = Relationship(
        back_populates="classes",
        link_model=StudentClass,
    )


# ── sa_column 패턴 ───────────────────────────────────────────


class Exam(SQLModel, table=True):
    __tablename__ = "exams"

    id: UUID = Field(primary_key=True)
    teacher_id: UUID = Field(index=True)   # 크로스도메인 FK (foreign_key 없음)
    title: str
    status: str = Field(default="draft")
    lifecycle_status: str = Field(
        default="exam_draft",
        sa_column=Column(
            SAEnum(GradingStatus, name="grading_status_enum"),
            nullable=False,
        ),
    )
    scores: list = Field(sa_column=Column(JSON))
    pass_score: int | None = Field(default=None)

    sections: list["Section"] = Relationship(back_populates="exam")


class Section(SQLModel, table=True):
    __tablename__ = "sections"

    id: UUID = Field(primary_key=True)
    exam_id: UUID = Field(foreign_key="exams.id", index=True)
    display_order: int
    scores: list[int] = Field(sa_column=Column(JSON))

    exam: Exam = Relationship(back_populates="sections")
