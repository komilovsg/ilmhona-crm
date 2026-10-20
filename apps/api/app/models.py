"""ORM models. The schema itself is written by hand in migrations/versions; the tests run
against the migrated database, so a mismatch fails there."""

from datetime import date, datetime, time
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    FetchedValue,
    ForeignKey,
    Integer,
    LargeBinary,
    Numeric,
    SmallInteger,
    Text,
    Time,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, CITEXT, JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

UUID_PK = text("gen_random_uuid()")
NOW = text("now()")


class Base(DeclarativeBase):
    pass


class Versioned:
    """`version` counts the changes of a row (bumped by a database trigger): a client that edits
    a row sends the version it loaded, and an older one is a conflict (#25)."""

    # eager_defaults: the trigger's new version comes back with the UPDATE, no lazy reload
    __mapper_args__ = {"eager_defaults": True}  # noqa: RUF012
    version: Mapped[int] = mapped_column(
        Integer, server_default=text("1"), server_onupdate=FetchedValue()
    )


class Branch(Base):
    __tablename__ = "branch"
    id: Mapped[UUID] = mapped_column(PG_UUID, primary_key=True, server_default=UUID_PK)
    name: Mapped[str] = mapped_column(Text, unique=True)


class Role(Versioned, Base):
    __tablename__ = "role"
    id: Mapped[UUID] = mapped_column(PG_UUID, primary_key=True, server_default=UUID_PK)
    name: Mapped[str] = mapped_column(Text, unique=True)
    # code is set for the seeded system roles only; it is how code finds them (superadmin).
    code: Mapped[str | None] = mapped_column(Text, unique=True)
    is_system: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=NOW)


class RolePermission(Base):
    __tablename__ = "role_permission"
    role_id: Mapped[UUID] = mapped_column(
        PG_UUID, ForeignKey("role.id", ondelete="CASCADE"), primary_key=True
    )
    section: Mapped[str] = mapped_column(Text, primary_key=True)
    level: Mapped[str] = mapped_column(Text)


class AppUser(Versioned, Base):
    __tablename__ = "app_user"
    id: Mapped[UUID] = mapped_column(PG_UUID, primary_key=True, server_default=UUID_PK)
    login: Mapped[str] = mapped_column(CITEXT, unique=True)
    full_name: Mapped[str] = mapped_column(Text)
    phone: Mapped[str | None] = mapped_column(Text, unique=True)
    email: Mapped[str | None] = mapped_column(Text)
    branch_id: Mapped[UUID | None] = mapped_column(PG_UUID, ForeignKey("branch.id"))
    role_id: Mapped[UUID] = mapped_column(PG_UUID, ForeignKey("role.id"))
    is_active: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    password_hash: Mapped[str] = mapped_column(Text)
    must_change_password: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    # starting rate per month of an instructor for a cohort (copied into the cohort's own rate)
    default_rate: Mapped[Decimal] = mapped_column(Numeric(12, 2), server_default=text("0"))
    temp_password_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=NOW)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=NOW)


class AuditLog(Base):
    __tablename__ = "audit_log"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[UUID | None] = mapped_column(
        PG_UUID, ForeignKey("app_user.id", ondelete="SET NULL")
    )
    action: Mapped[str] = mapped_column(Text)
    entity: Mapped[str] = mapped_column(Text)
    entity_id: Mapped[str | None] = mapped_column(Text)
    # branch of the changed row: a branch-scoped user reads only their branch's entries
    branch_id: Mapped[UUID | None] = mapped_column(PG_UUID, ForeignKey("branch.id"))
    diff: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    # display name of the entity when the entry was written (the row may be gone or renamed later)
    label: Mapped[str | None] = mapped_column(Text)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=NOW)


class RefreshToken(Base):
    """Rotating refresh tokens. A used token that shows up again revokes its whole family."""

    __tablename__ = "refresh_token"
    id: Mapped[UUID] = mapped_column(PG_UUID, primary_key=True, server_default=UUID_PK)
    user_id: Mapped[UUID] = mapped_column(PG_UUID, ForeignKey("app_user.id", ondelete="CASCADE"))
    family_id: Mapped[UUID] = mapped_column(PG_UUID)
    token_hash: Mapped[bytes] = mapped_column(LargeBinary, unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=NOW)


class LoginAttempt(Base):
    """Failed logins per login name, known or not: a lockout reveals nothing about accounts."""

    __tablename__ = "login_attempt"
    login: Mapped[str] = mapped_column(CITEXT, primary_key=True)
    failures: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Room(Versioned, Base):
    __tablename__ = "room"
    id: Mapped[UUID] = mapped_column(PG_UUID, primary_key=True, server_default=UUID_PK)
    branch_id: Mapped[UUID] = mapped_column(PG_UUID, ForeignKey("branch.id"))
    name: Mapped[str] = mapped_column(Text)
    capacity: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=NOW)


class Course(Versioned, Base):
    __tablename__ = "course"
    id: Mapped[UUID] = mapped_column(PG_UUID, primary_key=True, server_default=UUID_PK)
    name: Mapped[str] = mapped_column(Text, unique=True)
    direction: Mapped[str | None] = mapped_column(Text)
    default_price_month: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    duration_months: Mapped[int] = mapped_column(Integer)
    format: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=NOW)


class Cohort(Versioned, Base):
    __tablename__ = "cohort"
    id: Mapped[UUID] = mapped_column(PG_UUID, primary_key=True, server_default=UUID_PK)
    # 'G-NNN' from cohort_code_seq (database default)
    code: Mapped[str] = mapped_column(
        Text, server_default=text("'G-' || lpad(nextval('cohort_code_seq')::text, 3, '0')")
    )
    course_id: Mapped[UUID] = mapped_column(PG_UUID, ForeignKey("course.id"))
    branch_id: Mapped[UUID] = mapped_column(PG_UUID, ForeignKey("branch.id"))
    instructor_id: Mapped[UUID | None] = mapped_column(PG_UUID, ForeignKey("app_user.id"))
    room_id: Mapped[UUID] = mapped_column(PG_UUID, ForeignKey("room.id"))
    start_date: Mapped[date] = mapped_column(Date)
    end_date: Mapped[date] = mapped_column(Date)
    weekdays: Mapped[list[int]] = mapped_column(ARRAY(SmallInteger))
    start_time: Mapped[time] = mapped_column(Time)
    end_time: Mapped[time] = mapped_column(Time)
    capacity: Mapped[int] = mapped_column(Integer)
    price_month: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    status: Mapped[str] = mapped_column(Text, server_default=text("'набор'"))
    # what the instructor earns per month the cohort runs (default: the instructor's default_rate)
    instructor_rate: Mapped[Decimal] = mapped_column(Numeric(12, 2), server_default=text("0"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=NOW)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=NOW)


class Lesson(Versioned, Base):
    __tablename__ = "lesson"
    id: Mapped[UUID] = mapped_column(PG_UUID, primary_key=True, server_default=UUID_PK)
    cohort_id: Mapped[UUID] = mapped_column(PG_UUID, ForeignKey("cohort.id", ondelete="CASCADE"))
    room_id: Mapped[UUID] = mapped_column(PG_UUID, ForeignKey("room.id"))
    lesson_date: Mapped[date] = mapped_column(Date)
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    cancelled: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    # 'generated' from the cohort schedule (rebuilt on change); 'manual' added or moved by hand
    source: Mapped[str] = mapped_column(Text, server_default=text("'generated'"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=NOW)


class Student(Versioned, Base):
    __tablename__ = "student"
    id: Mapped[UUID] = mapped_column(PG_UUID, primary_key=True, server_default=UUID_PK)
    full_name: Mapped[str] = mapped_column(Text)
    gender: Mapped[str | None] = mapped_column(Text)
    phone: Mapped[str | None] = mapped_column(Text)
    branch_id: Mapped[UUID] = mapped_column(PG_UUID, ForeignKey("branch.id"))
    source_lead_id: Mapped[UUID | None] = mapped_column(PG_UUID)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=NOW)


class Enrollment(Versioned, Base):
    __tablename__ = "enrollment"
    id: Mapped[UUID] = mapped_column(PG_UUID, primary_key=True, server_default=UUID_PK)
    cohort_id: Mapped[UUID] = mapped_column(PG_UUID, ForeignKey("cohort.id"))
    student_id: Mapped[UUID] = mapped_column(PG_UUID, ForeignKey("student.id"))
    status: Mapped[str] = mapped_column(Text, server_default=text("'активный'"))
    enrolled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=NOW)


class Attendance(Base):
    """One cell of the attendance grid. Cells are written one by one (never a whole lesson in one
    statement), so two people marking the same lesson never overwrite each other's other cells."""

    __tablename__ = "attendance"
    lesson_id: Mapped[UUID] = mapped_column(
        PG_UUID, ForeignKey("lesson.id", ondelete="RESTRICT"), primary_key=True
    )
    enrollment_id: Mapped[UUID] = mapped_column(
        PG_UUID, ForeignKey("enrollment.id", ondelete="CASCADE"), primary_key=True
    )
    present: Mapped[bool] = mapped_column(Boolean)
    reason: Mapped[str | None] = mapped_column(Text)
    marked_by: Mapped[UUID | None] = mapped_column(
        PG_UUID, ForeignKey("app_user.id", ondelete="SET NULL")
    )
    marked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=NOW)


class Grade(Versioned, Base):
    """Homework and final (0-40 each, empty = not graded yet). The attendance part (0-20) is
    never stored: it is computed from the attendance cells (`app.metrics`)."""

    __tablename__ = "grade"
    enrollment_id: Mapped[UUID] = mapped_column(
        PG_UUID, ForeignKey("enrollment.id", ondelete="CASCADE"), primary_key=True
    )
    homework: Mapped[int | None] = mapped_column(SmallInteger)
    final: Mapped[int | None] = mapped_column(SmallInteger)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=NOW)


class Payment(Versioned, Base):
    __tablename__ = "payment"
    id: Mapped[UUID] = mapped_column(PG_UUID, primary_key=True, server_default=UUID_PK)
    enrollment_id: Mapped[UUID] = mapped_column(PG_UUID, ForeignKey("enrollment.id"))
    month_no: Mapped[int] = mapped_column(Integer)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    method: Mapped[str] = mapped_column(Text)
    paid_at: Mapped[date] = mapped_column(Date)
    status: Mapped[str] = mapped_column(Text, server_default=text("'ожидает'"))
    confirmed_by: Mapped[UUID | None] = mapped_column(
        PG_UUID, ForeignKey("app_user.id", ondelete="SET NULL")
    )
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    note: Mapped[str | None] = mapped_column(Text)
    idempotency_key: Mapped[UUID] = mapped_column(PG_UUID, unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=NOW)


class InstructorPayout(Versioned, Base):
    """What was actually paid to an instructor for a cohort's month (#9): profit is computed from
    these rows, never from the schedule."""

    __tablename__ = "instructor_payout"
    id: Mapped[UUID] = mapped_column(PG_UUID, primary_key=True, server_default=UUID_PK)
    instructor_id: Mapped[UUID] = mapped_column(PG_UUID, ForeignKey("app_user.id"))
    cohort_id: Mapped[UUID] = mapped_column(PG_UUID, ForeignKey("cohort.id"))
    period: Mapped[date] = mapped_column(Date)  # first day of the month
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    paid_at: Mapped[date] = mapped_column(Date)
    method: Mapped[str] = mapped_column(Text)
    note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=NOW)
