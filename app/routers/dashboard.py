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
    Equipment,
    Project,
    Request,
    RequestStatus,
)
from ..schemas import (
    DailyStatusBoard,
    DailyStatusLine,
    DailyStatusProject,
    DashboardProjectRow,
    DashboardSummary,
)

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
    total_available_equipment = (
        db.query(func.count(Equipment.id))
        .filter(Equipment.availability_status == AvailabilityStatus.available)
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
    expired_inspections = (
        db.query(func.count(Equipment.id))
        .filter(Equipment.inspection_expiry.isnot(None))
        .filter(Equipment.inspection_expiry < date.today())
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
        total_available_equipment=total_available_equipment,
        total_shortage=total_shortage,
        pending_approvals=pending,
        expired_passports=expired_passports,
        expired_inspections=expired_inspections,
        mobilized_requests=mobilized,
        rejected_requests=rejected,
    )


# Statuses to include in the daily operational board (active requests).
_ACTIVE_STATUSES = _OPEN_STATUSES | {RequestStatus.mobilized}


@router.get("/daily", response_model=DailyStatusBoard)
def daily_status(
    on_date: date | None = None,
    db: Session = Depends(get_db),
    _: object = Depends(get_current_user),
) -> DailyStatusBoard:
    """Daily status board: per project, manpower & equipment in place vs shortage."""
    target = on_date or date.today()
    projects_out: list[DailyStatusProject] = []

    for project in db.query(Project).order_by(Project.name).all():
        requests = (
            db.query(Request)
            .filter(Request.project_id == project.id)
            .filter(Request.required_date == target)
            .filter(Request.status.in_(_ACTIVE_STATUSES))
            .all()
        )
        if not requests:
            continue

        # Aggregate manpower lines by category, equipment by type.
        man: dict[str, dict[str, int]] = {}
        eq: dict[str, dict[str, int]] = {}
        for req in requests:
            for item in req.items:
                bucket = man.setdefault(
                    item.category.name, {"requested": 0, "in_place": 0}
                )
                bucket["requested"] += item.quantity
                bucket["in_place"] += item.in_place_qty
            for eitem in req.equipment_items:
                bucket = eq.setdefault(
                    eitem.equipment_type.name, {"requested": 0, "in_place": 0}
                )
                bucket["requested"] += eitem.quantity
                bucket["in_place"] += eitem.in_place_qty

        man_lines = _to_lines(man)
        eq_lines = _to_lines(eq)
        man_req = sum(line.requested for line in man_lines)
        man_in = sum(line.in_place for line in man_lines)
        eq_req = sum(line.requested for line in eq_lines)
        eq_in = sum(line.in_place for line in eq_lines)
        total_shortage = (man_req - man_in) + (eq_req - eq_in)

        projects_out.append(
            DailyStatusProject(
                project_id=project.id,
                project=project.name,
                client_supervisor=project.client_supervisor,
                company_supervisor=project.company_supervisor,
                manpower=man_lines,
                equipment=eq_lines,
                manpower_requested=man_req,
                manpower_in_place=man_in,
                manpower_shortage=max(0, man_req - man_in),
                equipment_requested=eq_req,
                equipment_in_place=eq_in,
                equipment_shortage=max(0, eq_req - eq_in),
                status="in place" if total_shortage <= 0 else "shortage",
            )
        )

    return DailyStatusBoard(date=target, projects=projects_out)


def _to_lines(grouped: dict[str, dict[str, int]]) -> list[DailyStatusLine]:
    lines: list[DailyStatusLine] = []
    for name in sorted(grouped):
        requested = grouped[name]["requested"]
        in_place = grouped[name]["in_place"]
        shortage = max(0, requested - in_place)
        lines.append(
            DailyStatusLine(
                name=name,
                requested=requested,
                in_place=in_place,
                shortage=shortage,
                status="in place" if shortage == 0 else "shortage",
            )
        )
    return lines
