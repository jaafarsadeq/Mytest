"""Daily request endpoints + approval workflow (Sections 4.4 & 4.6)."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..auth import get_current_user, require_roles
from ..database import get_db
from ..models import (
    EquipmentRequestItem,
    EquipmentType,
    ManpowerCategory,
    Project,
    Request,
    RequestApproval,
    RequestItem,
    RequestStatus,
    Role,
    User,
)
from ..schemas import ConfirmInPlaceIn, RequestIn, RequestOut, TransitionIn
from ..workflow import allowed, confirm_in_place, run_availability_check

router = APIRouter(prefix="/api/requests", tags=["requests"])


def _get_request(db: Session, request_id: int) -> Request:
    request = db.get(Request, request_id)
    if request is None:
        raise HTTPException(status_code=404, detail="Request not found")
    return request


@router.get("", response_model=list[RequestOut])
def list_requests(
    project_id: int | None = None,
    status: RequestStatus | None = None,
    db: Session = Depends(get_db),
    _: object = Depends(get_current_user),
) -> list[Request]:
    query = db.query(Request)
    if project_id is not None:
        query = query.filter(Request.project_id == project_id)
    if status is not None:
        query = query.filter(Request.status == status)
    return query.order_by(Request.required_date.desc(), Request.id.desc()).all()


@router.get("/{request_id}", response_model=RequestOut)
def get_request(
    request_id: int, db: Session = Depends(get_db), _: object = Depends(get_current_user)
) -> Request:
    return _get_request(db, request_id)


@router.post("", response_model=RequestOut, status_code=201)
def create_request(
    payload: RequestIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(Role.client, Role.admin)),
) -> Request:
    project = db.get(Project, payload.project_id)
    if project is None:
        raise HTTPException(status_code=400, detail="Unknown project_id")
    if not payload.items and not payload.equipment_items:
        raise HTTPException(
            status_code=400, detail="At least one manpower or equipment line is required"
        )

    request = Request(
        project_id=payload.project_id,
        station=payload.station or project.station,
        required_date=payload.required_date,
        shift=payload.shift,
        remarks=payload.remarks,
        status=RequestStatus.draft,
        created_by=user.id,
    )
    for item in payload.items:
        if db.get(ManpowerCategory, item.category_id) is None:
            raise HTTPException(status_code=400, detail=f"Unknown category_id {item.category_id}")
        request.items.append(
            RequestItem(
                category_id=item.category_id,
                quantity=item.quantity,
                shortage_qty=item.quantity,  # nothing in place yet
            )
        )
    for eq in payload.equipment_items:
        if db.get(EquipmentType, eq.equipment_type_id) is None:
            raise HTTPException(
                status_code=400, detail=f"Unknown equipment_type_id {eq.equipment_type_id}"
            )
        request.equipment_items.append(
            EquipmentRequestItem(
                equipment_type_id=eq.equipment_type_id,
                quantity=eq.quantity,
                shortage_qty=eq.quantity,
            )
        )
    db.add(request)
    db.flush()
    run_availability_check(db, request)  # snapshot availability at creation
    db.commit()
    db.refresh(request)
    return request


@router.post("/{request_id}/recheck", response_model=RequestOut)
def recheck_availability(
    request_id: int,
    db: Session = Depends(get_db),
    _: object = Depends(get_current_user),
) -> Request:
    """Re-run the availability/eligibility check against current data."""
    request = _get_request(db, request_id)
    run_availability_check(db, request)
    db.commit()
    db.refresh(request)
    return request


@router.post("/{request_id}/confirm", response_model=RequestOut)
def confirm_in_place_endpoint(
    request_id: int,
    payload: ConfirmInPlaceIn,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(Role.supervisor, Role.admin)),
) -> Request:
    """Company supervisor confirms how much manpower/equipment is in place."""
    request = _get_request(db, request_id)
    manpower = {line.item_id: line.in_place for line in payload.manpower}
    equipment = {line.item_id: line.in_place for line in payload.equipment}
    confirm_in_place(db, request, manpower, equipment)
    db.commit()
    db.refresh(request)
    return request


@router.post("/{request_id}/transition/{target}", response_model=RequestOut)
def transition(
    request_id: int,
    target: RequestStatus,
    payload: TransitionIn = TransitionIn(),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Request:
    """Advance (or reject) a request, enforcing the role-based workflow."""
    request = _get_request(db, request_id)
    if not allowed(request.status, target, user.role):
        raise HTTPException(
            status_code=403,
            detail=(
                f"Role '{user.role.value}' cannot move request from "
                f"'{request.status.value}' to '{target.value}'"
            ),
        )
    # Refresh availability whenever entering supervisor review or approval.
    if target in {RequestStatus.supervisor_review, RequestStatus.operations_approval}:
        run_availability_check(db, request)

    request.status = target
    db.add(
        RequestApproval(
            request_id=request.id,
            stage=target,
            actor_id=user.id,
            actor_role=user.role,
            remarks=payload.remarks,
        )
    )
    db.commit()
    db.refresh(request)
    return request
