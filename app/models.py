"""SQLAlchemy ORM models for the MVP.

Covers the Section 10 tables: users, roles, projects, project_requirements,
manpower_categories, employees, requests, request_items, request_approvals.
"""

from __future__ import annotations

import enum
from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


class Role(str, enum.Enum):
    """Role-based access roles (Section 6 / Authentication)."""

    admin = "admin"
    client = "client"
    supervisor = "supervisor"
    hse = "hse"
    transport = "transport"
    viewer = "viewer"


class RequestStatus(str, enum.Enum):
    """Approval workflow stages (Section 4.6).

    The MVP exercises Draft -> Submitted -> Supervisor review -> Approved /
    Rejected -> Mobilized -> Closed. HSE/Transport stages exist in the enum
    for forward compatibility but are not required to advance in the MVP.
    """

    draft = "draft"
    submitted = "submitted"
    supervisor_review = "supervisor_review"
    hse_verification = "hse_verification"
    transport_verification = "transport_verification"
    operations_approval = "operations_approval"
    confirmed = "confirmed"
    mobilized = "mobilized"
    closed = "closed"
    rejected = "rejected"


class AvailabilityStatus(str, enum.Enum):
    """Employee availability states."""

    available = "available"
    assigned = "assigned"
    leave = "leave"
    unavailable = "unavailable"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(128), default="")
    hashed_password: Mapped[str] = mapped_column(String(256))
    role: Mapped[Role] = mapped_column(Enum(Role), default=Role.viewer)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    # Optional: client users may be scoped to a single project.
    project_id: Mapped[int | None] = mapped_column(ForeignKey("projects.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class ManpowerCategory(Base):
    __tablename__ = "manpower_categories"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    description: Mapped[str] = mapped_column(String(256), default="")

    employees: Mapped[list["Employee"]] = relationship(back_populates="category")


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    client_name: Mapped[str] = mapped_column(String(128), default="")
    site_location: Mapped[str] = mapped_column(String(128), default="")
    station: Mapped[str] = mapped_column(String(128), default="")
    working_hours: Mapped[str] = mapped_column(String(64), default="")
    supervisor_name: Mapped[str] = mapped_column(String(128), default="")
    hse_contact: Mapped[str] = mapped_column(String(128), default="")
    transport_rules: Mapped[str] = mapped_column(Text, default="")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    requirement: Mapped["ProjectRequirement | None"] = relationship(
        back_populates="project", uselist=False, cascade="all, delete-orphan"
    )


class ProjectRequirement(Base):
    """Project-specific eligibility rules (Section 4.1)."""

    __tablename__ = "project_requirements"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), unique=True)
    # e.g. "BGC" — the safety passport an employee must hold for this project.
    required_passport: Mapped[str] = mapped_column(String(64), default="")
    requires_ppe: Mapped[bool] = mapped_column(Boolean, default=True)
    requires_medical: Mapped[bool] = mapped_column(Boolean, default=False)
    required_training: Mapped[str] = mapped_column(String(256), default="")
    transport_required: Mapped[bool] = mapped_column(Boolean, default=False)
    notes: Mapped[str] = mapped_column(Text, default="")

    project: Mapped[Project] = relationship(back_populates="requirement")


class Employee(Base):
    """Manpower database profile (Section 4.2)."""

    __tablename__ = "employees"

    id: Mapped[int] = mapped_column(primary_key=True)
    employee_code: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(128))
    nationality: Mapped[str] = mapped_column(String(64), default="")
    category_id: Mapped[int] = mapped_column(ForeignKey("manpower_categories.id"))
    current_project_id: Mapped[int | None] = mapped_column(
        ForeignKey("projects.id"), nullable=True
    )
    current_location: Mapped[str] = mapped_column(String(128), default="")
    availability_status: Mapped[AvailabilityStatus] = mapped_column(
        Enum(AvailabilityStatus), default=AvailabilityStatus.available
    )
    passport_type: Mapped[str] = mapped_column(String(64), default="")
    passport_expiry: Mapped[date | None] = mapped_column(Date, nullable=True)
    ppe_status: Mapped[bool] = mapped_column(Boolean, default=False)
    medical_expiry: Mapped[date | None] = mapped_column(Date, nullable=True)
    training_certificates: Mapped[str] = mapped_column(String(256), default="")
    camp_location: Mapped[str] = mapped_column(String(128), default="")
    transport_route: Mapped[str] = mapped_column(String(128), default="")
    supervisor: Mapped[str] = mapped_column(String(128), default="")
    remarks: Mapped[str] = mapped_column(Text, default="")

    category: Mapped[ManpowerCategory] = relationship(back_populates="employees")
    current_project: Mapped[Project | None] = relationship()


class Request(Base):
    """Daily manpower request (Section 4.4)."""

    __tablename__ = "requests"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"))
    station: Mapped[str] = mapped_column(String(128), default="")
    required_date: Mapped[date] = mapped_column(Date)
    shift: Mapped[str] = mapped_column(String(32), default="day")
    status: Mapped[RequestStatus] = mapped_column(
        Enum(RequestStatus), default=RequestStatus.draft
    )
    remarks: Mapped[str] = mapped_column(Text, default="")
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    project: Mapped[Project] = relationship()
    items: Mapped[list["RequestItem"]] = relationship(
        back_populates="request", cascade="all, delete-orphan"
    )
    approvals: Mapped[list["RequestApproval"]] = relationship(
        back_populates="request", cascade="all, delete-orphan"
    )


class RequestItem(Base):
    """A manpower line on a request, with availability check results."""

    __tablename__ = "request_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    request_id: Mapped[int] = mapped_column(ForeignKey("requests.id"))
    category_id: Mapped[int] = mapped_column(ForeignKey("manpower_categories.id"))
    quantity: Mapped[int] = mapped_column(Integer)
    # Snapshot of the most recent availability check for this line.
    available_qty: Mapped[int] = mapped_column(Integer, default=0)
    eligible_qty: Mapped[int] = mapped_column(Integer, default=0)
    shortage_qty: Mapped[int] = mapped_column(Integer, default=0)
    reason: Mapped[str] = mapped_column(Text, default="")

    request: Mapped[Request] = relationship(back_populates="items")
    category: Mapped[ManpowerCategory] = relationship()


class RequestApproval(Base):
    """Audit trail of workflow transitions (Section 4.6)."""

    __tablename__ = "request_approvals"

    id: Mapped[int] = mapped_column(primary_key=True)
    request_id: Mapped[int] = mapped_column(ForeignKey("requests.id"))
    stage: Mapped[RequestStatus] = mapped_column(Enum(RequestStatus))
    actor_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    actor_role: Mapped[Role] = mapped_column(Enum(Role))
    remarks: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    request: Mapped[Request] = relationship(back_populates="approvals")
