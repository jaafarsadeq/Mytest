"""Approval workflow transitions (Section 4.6).

Defines which roles may move a request from one status to the next, and a
helper to (re)run the availability check and persist results onto the
request's items.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from .availability import check_category
from .models import ManpowerCategory, Request, RequestStatus, Role

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
    """Recompute availability for each item and store the snapshot."""
    project = request.project
    for item in request.items:
        category = db.get(ManpowerCategory, item.category_id)
        if category is None:
            continue
        result = check_category(db, project, category, item.quantity, request.required_date)
        item.available_qty = result.available
        item.eligible_qty = result.eligible
        item.shortage_qty = result.shortage
        item.reason = result.reason_text
