"""Operations dashboard endpoint (Section 4.8)."""

from datetime import date

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..auth import get_current_user
from ..database import get_db
from ..models import (
    AvailabilityStatus,
    Employee,
    Project,
    Request,
    RequestItem,
    RequestStatus,
)
from ..schemas import DashboardProjectRow, DashboardSummary

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])

# Statuses that represent an open (not closed/rejected) request.
_OPEN_STATUSES = {
    RequestStatus.draft,
    RequestStatus.submitted,
    RequestStatus.supervisor_review,
    RequestStatus.hse_verification,
    RequestStatus.transport_verification,
    RequestStatus.operations_approval,
    RequestStatus.confirmed,
}
_PENDING_STATUSES = {
    RequestStatus.submitted,
    RequestStatus.supervisor_review,
    RequestStatus.operations_approval,
}


@router.get("/summary", response_model=DashboardSummary)
def summary(
    db: Session = Depends(get_db), _: object = Depends(get_current_user)
) -> DashboardSummary:
    rows: list[DashboardProjectRow] = []
    total_shortage = 0

    for project in db.query(Project).order_by(Project.name).all():
        open_requests = (
            db.query(Request)
            .filter(Request.project_id == project.id)
            .filter(Request.status.in_(_OPEN_STATUSES))
            .all()
        )
        requested = sum(item.quantity for r in open_requests for item in r.items)
        eligible = sum(item.eligible_qty for r in open_requests for item in r.items)
        shortage = sum(item.shortage_qty for r in open_requests for item in r.items)
        total_shortage += shortage
        rows.append(
            DashboardProjectRow(
                project_id=project.id,
                project=project.name,
                requested=requested,
                eligible=eligible,
                shortage=shortage,
                open_requests=len(open_requests),
            )
        )

    total_available = (
        db.query(func.count(Employee.id))
        .filter(Employee.availability_status == AvailabilityStatus.available)
        .scalar()
        or 0
    )
    pending = (
        db.query(func.count(Request.id))
        .filter(Request.status.in_(_PENDING_STATUSES))
        .scalar()
        or 0
    )
    expired_passports = (
        db.query(func.count(Employee.id))
        .filter(Employee.passport_expiry.isnot(None))
        .filter(Employee.passport_expiry < date.today())
        .scalar()
        or 0
    )
    mobilized = (
        db.query(func.count(Request.id))
        .filter(Request.status == RequestStatus.mobilized)
        .scalar()
        or 0
    )
    rejected = (
        db.query(func.count(Request.id))
        .filter(Request.status == RequestStatus.rejected)
        .scalar()
        or 0
    )

    return DashboardSummary(
        projects=rows,
        total_available_manpower=total_available,
        total_shortage=total_shortage,
        pending_approvals=pending,
        expired_passports=expired_passports,
        mobilized_requests=mobilized,
        rejected_requests=rejected,
    )
