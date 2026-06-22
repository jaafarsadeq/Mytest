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
    # Defaults to the project name when left blank (client name = project).
    client_name: str = ""
    site_location: str = ""
    station: str = ""
    working_hours: str = ""
    supervisor_name: str = ""
    client_supervisor: str = ""
    company_supervisor: str = ""
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
    client_supervisor: str
    company_supervisor: str
    hse_contact: str
    transport_rules: str
    is_active: bool
    requirement: RequirementOut | None = None


# --- Equipment ----------------------------------------------------------------

class EquipmentTypeIn(BaseModel):
    name: str
    description: str = ""


class EquipmentTypeOut(ORMModel):
    id: int
    name: str
    description: str


class EquipmentIn(BaseModel):
    equipment_code: str
    type_id: int
    capacity: str = ""
    plate_number: str = ""
    current_project_id: int | None = None
    current_location: str = ""
    availability_status: AvailabilityStatus = AvailabilityStatus.available
    inspection_expiry: date | None = None
    operator_assigned: str = ""
    ivms_status: bool = False
    maintenance_status: str = "ok"
    fuel_status: str = ""
    remarks: str = ""


class EquipmentOut(ORMModel):
    id: int
    equipment_code: str
    type_id: int
    capacity: str
    plate_number: str
    current_project_id: int | None
    current_location: str
    availability_status: AvailabilityStatus
    inspection_expiry: date | None
    operator_assigned: str
    ivms_status: bool
    maintenance_status: str
    fuel_status: str
    remarks: str


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


class EquipmentItemIn(BaseModel):
    equipment_type_id: int
    quantity: int = Field(gt=0)


class RequestIn(BaseModel):
    project_id: int
    station: str = ""
    required_date: date
    shift: str = "day"
    remarks: str = ""
    items: list[RequestItemIn] = []
    equipment_items: list[EquipmentItemIn] = []


class RequestItemOut(ORMModel):
    id: int
    category_id: int
    quantity: int
    available_qty: int
    eligible_qty: int
    in_place_qty: int
    shortage_qty: int
    reason: str


class EquipmentRequestItemOut(ORMModel):
    id: int
    equipment_type_id: int
    quantity: int
    available_qty: int
    in_place_qty: int
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
    equipment_items: list[EquipmentRequestItemOut]
    approvals: list[ApprovalOut]


class TransitionIn(BaseModel):
    remarks: str = ""


# --- Daily in-place confirmation ---------------------------------------------

class InPlaceLine(BaseModel):
    item_id: int
    in_place: int = Field(ge=0)


class ConfirmInPlaceIn(BaseModel):
    """Company supervisor's daily confirmation of what is actually in place."""

    manpower: list[InPlaceLine] = []
    equipment: list[InPlaceLine] = []


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
    total_available_equipment: int
    total_shortage: int
    pending_approvals: int
    expired_passports: int
    expired_inspections: int
    mobilized_requests: int
    rejected_requests: int


# --- Daily status board -------------------------------------------------------

class DailyStatusLine(BaseModel):
    name: str
    requested: int
    in_place: int
    shortage: int
    status: str  # "in place" | "shortage"


class DailyStatusProject(BaseModel):
    project_id: int
    project: str
    client_supervisor: str
    company_supervisor: str
    manpower: list[DailyStatusLine]
    equipment: list[DailyStatusLine]
    manpower_requested: int
    manpower_in_place: int
    manpower_shortage: int
    equipment_requested: int
    equipment_in_place: int
    equipment_shortage: int
    status: str  # "in place" | "shortage"


class DailyStatusBoard(BaseModel):
    date: date
    projects: list[DailyStatusProject]
