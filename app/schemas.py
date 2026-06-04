"""Pydantic request/response schemas."""

from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field

from .models import AvailabilityStatus, RequestStatus, Role


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# --- Auth ---------------------------------------------------------------------

class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: Role
    full_name: str


class UserOut(ORMModel):
    id: int
    username: str
    full_name: str
    role: Role
    project_id: int | None = None


# --- Categories ---------------------------------------------------------------

class CategoryIn(BaseModel):
    name: str
    description: str = ""


class CategoryOut(ORMModel):
    id: int
    name: str
    description: str


# --- Projects -----------------------------------------------------------------

class RequirementIn(BaseModel):
    required_passport: str = ""
    requires_ppe: bool = True
    requires_medical: bool = False
    required_training: str = ""
    transport_required: bool = False
    notes: str = ""


class RequirementOut(ORMModel):
    required_passport: str
    requires_ppe: bool
    requires_medical: bool
    required_training: str
    transport_required: bool
    notes: str


class ProjectIn(BaseModel):
    name: str
    client_name: str = ""
    site_location: str = ""
    station: str = ""
    working_hours: str = ""
    supervisor_name: str = ""
    hse_contact: str = ""
    transport_rules: str = ""
    requirement: RequirementIn | None = None


class ProjectOut(ORMModel):
    id: int
    name: str
    client_name: str
    site_location: str
    station: str
    working_hours: str
    supervisor_name: str
    hse_contact: str
    transport_rules: str
    is_active: bool
    requirement: RequirementOut | None = None


# --- Employees ----------------------------------------------------------------

class EmployeeIn(BaseModel):
    employee_code: str
    name: str
    nationality: str = ""
    category_id: int
    current_project_id: int | None = None
    current_location: str = ""
    availability_status: AvailabilityStatus = AvailabilityStatus.available
    passport_type: str = ""
    passport_expiry: date | None = None
    ppe_status: bool = False
    medical_expiry: date | None = None
    training_certificates: str = ""
    camp_location: str = ""
    transport_route: str = ""
    supervisor: str = ""
    remarks: str = ""


class EmployeeOut(ORMModel):
    id: int
    employee_code: str
    name: str
    nationality: str
    category_id: int
    current_project_id: int | None
    current_location: str
    availability_status: AvailabilityStatus
    passport_type: str
    passport_expiry: date | None
    ppe_status: bool
    medical_expiry: date | None
    training_certificates: str
    camp_location: str
    transport_route: str
    supervisor: str
    remarks: str


# --- Requests -----------------------------------------------------------------

class RequestItemIn(BaseModel):
    category_id: int
    quantity: int = Field(gt=0)


class RequestIn(BaseModel):
    project_id: int
    station: str = ""
    required_date: date
    shift: str = "day"
    remarks: str = ""
    items: list[RequestItemIn]


class RequestItemOut(ORMModel):
    id: int
    category_id: int
    quantity: int
    available_qty: int
    eligible_qty: int
    shortage_qty: int
    reason: str


class ApprovalOut(ORMModel):
    id: int
    stage: RequestStatus
    actor_role: Role
    remarks: str
    created_at: datetime


class RequestOut(ORMModel):
    id: int
    project_id: int
    station: str
    required_date: date
    shift: str
    status: RequestStatus
    remarks: str
    created_at: datetime
    items: list[RequestItemOut]
    approvals: list[ApprovalOut]


class TransitionIn(BaseModel):
    remarks: str = ""


# --- Availability -------------------------------------------------------------

class AvailabilityLine(BaseModel):
    category_id: int
    category_name: str
    requested: int
    available: int
    eligible: int
    shortage: int
    reason: str


class AvailabilityCheckIn(BaseModel):
    project_id: int
    required_date: date
    items: list[RequestItemIn]


# --- Dashboard ----------------------------------------------------------------

class DashboardProjectRow(BaseModel):
    project_id: int
    project: str
    requested: int
    eligible: int
    shortage: int
    open_requests: int


class DashboardSummary(BaseModel):
    projects: list[DashboardProjectRow]
    total_available_manpower: int
    total_shortage: int
    pending_approvals: int
    expired_passports: int
    mobilized_requests: int
    rejected_requests: int
