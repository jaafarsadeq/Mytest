"""Approval workflow transitions (Section 4.6).

Defines which roles may move a request from one status to the next, and a
helper to (re)run the availability check and persist results onto the
request's items.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from .availability import check_category, check_equipment_type
from .models import EquipmentType, ManpowerCategory, Request, RequestStatus, Role

# Map each allowed transition to the set of roles permitted to perform it.
# The MVP focuses on the client -> supervisor -> operations path; HSE and
# transport stages are available but optional.
TRANSITIONS: dict[tuple[RequestStatus, RequestStatus], set[Role]] = {
    (RequestStatus.draft, RequestStatus.submitted): {Role.client, Role.admin},
    (RequestStatus.submitted, RequestStatus.supervisor_review): {Role.supervisor, Role.admin},
    (RequestStatus.supervisor_review, RequestStatus.operations_approval): {
        Role.supervisor,
        Role.admin,
    },
    (RequestStatus.supervisor_review, RequestStatus.rejected): {Role.supervisor, Role.admin},
    (RequestStatus.operations_approval, RequestStatus.confirmed): {Role.admin},
    (RequestStatus.operations_approval, RequestStatus.rejected): {Role.admin},
    (RequestStatus.confirmed, RequestStatus.mobilized): {Role.admin, Role.transport},
    (RequestStatus.mobilized, RequestStatus.closed): {Role.admin},
}


def allowed(current: RequestStatus, target: RequestStatus, role: Role) -> bool:
    roles = TRANSITIONS.get((current, target))
    return bool(roles) and role in roles


def next_statuses(current: RequestStatus, role: Role) -> list[RequestStatus]:
    return [
        target
        for (src, target), roles in TRANSITIONS.items()
        if src == current and role in roles
    ]


def run_availability_check(db: Session, request: Request) -> None:
    """Recompute the planning availability snapshot for each line.

    This fills the *planning* figures (available/eligible from inventory) and
    the reason breakdown. The operational ``shortage_qty`` is driven by the
    company supervisor's daily in-place confirmation, so it is recomputed from
    ``quantity - in_place_qty`` rather than from the planning estimate.
    """
    project = request.project
    for item in request.items:
        category = db.get(ManpowerCategory, item.category_id)
        if category is None:
            continue
        result = check_category(db, project, category, item.quantity, request.required_date)
        item.available_qty = result.available
        item.eligible_qty = result.eligible
        item.shortage_qty = max(0, item.quantity - item.in_place_qty)
        item.reason = result.reason_text

    for eq_item in request.equipment_items:
        eq_type = db.get(EquipmentType, eq_item.equipment_type_id)
        if eq_type is None:
            continue
        eq_result = check_equipment_type(
            db, project, eq_type, eq_item.quantity, request.required_date
        )
        eq_item.available_qty = eq_result.available
        eq_item.shortage_qty = max(0, eq_item.quantity - eq_item.in_place_qty)
        eq_item.reason = eq_result.reason_text


def confirm_in_place(
    db: Session,
    request: Request,
    manpower: dict[int, int],
    equipment: dict[int, int],
) -> None:
    """Apply the company supervisor's daily in-place confirmation.

    ``manpower``/``equipment`` map a *request item id* to the quantity actually
    in place. Shortage is recomputed as ``requested - in_place`` per line.
    """
    for item in request.items:
        if item.id in manpower:
            item.in_place_qty = max(0, min(manpower[item.id], item.quantity))
            item.shortage_qty = max(0, item.quantity - item.in_place_qty)
    for eq_item in request.equipment_items:
        if eq_item.id in equipment:
            eq_item.in_place_qty = max(0, min(equipment[eq_item.id], eq_item.quantity))
            eq_item.shortage_qty = max(0, eq_item.quantity - eq_item.in_place_qty)
