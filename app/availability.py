"""Availability & eligibility checking engine (Section 4.5).

For a given project, category, date, and requested quantity it computes:
available, eligible, and shortage quantities plus a human-readable reason
breaking down why otherwise-available workers are not eligible.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from sqlalchemy.orm import Session

from .models import (
    AvailabilityStatus,
    Employee,
    Equipment,
    EquipmentType,
    ManpowerCategory,
    Project,
    ProjectRequirement,
)


@dataclass
class CategoryAvailability:
    category_id: int
    category_name: str
    requested: int
    available: int = 0
    eligible: int = 0
    shortage: int = 0
    reasons: list[str] = field(default_factory=list)
    eligible_employee_ids: list[int] = field(default_factory=list)

    @property
    def reason_text(self) -> str:
        return "; ".join(self.reasons)


def _employee_is_eligible(
    emp: Employee, project: Project, req: ProjectRequirement | None, on_date: date
) -> tuple[bool, str | None]:
    """Return ``(eligible, reason_if_not)`` for one available employee."""
    # Assigned to a *different* active project.
    if emp.current_project_id and emp.current_project_id != project.id:
        return False, "assigned to another project"

    if req is None:
        return True, None

    # Safety passport type must match the project's required passport.
    if req.required_passport:
        if (emp.passport_type or "").upper() != req.required_passport.upper():
            return False, f"missing {req.required_passport} passport"
        if emp.passport_expiry is None or emp.passport_expiry < on_date:
            return False, f"expired {req.required_passport} passport"

    if req.requires_ppe and not emp.ppe_status:
        return False, "incomplete PPE"

    if req.requires_medical:
        if emp.medical_expiry is None or emp.medical_expiry < on_date:
            return False, "expired/missing medical"

    if req.required_training:
        needed = {t.strip().lower() for t in req.required_training.split(",") if t.strip()}
        held = {t.strip().lower() for t in (emp.training_certificates or "").split(",")}
        missing = needed - held
        if missing:
            return False, f"missing training: {', '.join(sorted(missing))}"

    return True, None


def check_category(
    db: Session,
    project: Project,
    category: ManpowerCategory,
    requested: int,
    on_date: date,
) -> CategoryAvailability:
    """Compute availability for a single manpower category."""
    result = CategoryAvailability(
        category_id=category.id, category_name=category.name, requested=requested
    )
    req = project.requirement

    employees = (
        db.query(Employee)
        .filter(Employee.category_id == category.id)
        .filter(Employee.availability_status == AvailabilityStatus.available)
        .all()
    )
    result.available = len(employees)

    reason_counts: dict[str, int] = {}
    for emp in employees:
        ok, reason = _employee_is_eligible(emp, project, req, on_date)
        if ok:
            result.eligible += 1
            result.eligible_employee_ids.append(emp.id)
        elif reason:
            reason_counts[reason] = reason_counts.get(reason, 0) + 1

    result.shortage = max(0, requested - result.eligible)
    result.reasons = [f"{count} {reason}" for reason, count in sorted(reason_counts.items())]
    return result


def check_request_items(
    db: Session,
    project: Project,
    on_date: date,
    items: list[tuple[int, int]],
) -> list[CategoryAvailability]:
    """Check a list of ``(category_id, quantity)`` lines for a project/date."""
    results: list[CategoryAvailability] = []
    for category_id, quantity in items:
        category = db.get(ManpowerCategory, category_id)
        if category is None:
            continue
        results.append(check_category(db, project, category, quantity, on_date))
    return results


@dataclass
class EquipmentAvailability:
    type_id: int
    type_name: str
    requested: int
    available: int = 0
    shortage: int = 0
    reasons: list[str] = field(default_factory=list)

    @property
    def reason_text(self) -> str:
        return "; ".join(self.reasons)


def check_equipment_type(
    db: Session,
    project: Project,
    eq_type: EquipmentType,
    requested: int,
    on_date: date,
) -> EquipmentAvailability:
    """Compute availability for a single equipment type.

    An item is available when its status is ``available``, its inspection is
    valid for the date, and it is not committed to a different project.
    """
    result = EquipmentAvailability(
        type_id=eq_type.id, type_name=eq_type.name, requested=requested
    )
    equipment = (
        db.query(Equipment)
        .filter(Equipment.type_id == eq_type.id)
        .filter(Equipment.availability_status == AvailabilityStatus.available)
        .all()
    )

    reason_counts: dict[str, int] = {}
    for item in equipment:
        if item.current_project_id and item.current_project_id != project.id:
            reason_counts["assigned to another project"] = (
                reason_counts.get("assigned to another project", 0) + 1
            )
            continue
        if item.inspection_expiry is None or item.inspection_expiry < on_date:
            reason_counts["expired/missing inspection"] = (
                reason_counts.get("expired/missing inspection", 0) + 1
            )
            continue
        result.available += 1

    result.shortage = max(0, requested - result.available)
    result.reasons = [f"{count} {reason}" for reason, count in sorted(reason_counts.items())]
    return result
