"""Ad-hoc availability checking endpoint (Section 4.5)."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..availability import check_request_items
from ..auth import get_current_user
from ..database import get_db
from ..models import Project
from ..schemas import AvailabilityCheckIn, AvailabilityLine

router = APIRouter(prefix="/api/availability", tags=["availability"])


@router.post("/check", response_model=list[AvailabilityLine])
def check(
    payload: AvailabilityCheckIn,
    db: Session = Depends(get_db),
    _: object = Depends(get_current_user),
) -> list[AvailabilityLine]:
    project = db.get(Project, payload.project_id)
    if project is None:
        raise HTTPException(status_code=400, detail="Unknown project_id")
    items = [(i.category_id, i.quantity) for i in payload.items]
    results = check_request_items(db, project, payload.required_date, items)
    return [
        AvailabilityLine(
            category_id=r.category_id,
            category_name=r.category_name,
            requested=r.requested,
            available=r.available,
            eligible=r.eligible,
            shortage=r.shortage,
            reason=r.reason_text,
        )
        for r in results
    ]
