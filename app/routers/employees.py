"""Employee / manpower database endpoints (Section 4.2)."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..auth import get_current_user, require_roles
from ..database import get_db
from ..models import Employee, ManpowerCategory, Role
from ..schemas import EmployeeIn, EmployeeOut

router = APIRouter(prefix="/api/employees", tags=["employees"])


@router.get("", response_model=list[EmployeeOut])
def list_employees(
    category_id: int | None = None,
    project_id: int | None = None,
    db: Session = Depends(get_db),
    _: object = Depends(get_current_user),
) -> list[Employee]:
    query = db.query(Employee)
    if category_id is not None:
        query = query.filter(Employee.category_id == category_id)
    if project_id is not None:
        query = query.filter(Employee.current_project_id == project_id)
    return query.order_by(Employee.name).all()


@router.post("", response_model=EmployeeOut, status_code=201)
def create_employee(
    payload: EmployeeIn,
    db: Session = Depends(get_db),
    _: object = Depends(require_roles(Role.admin)),
) -> Employee:
    if db.get(ManpowerCategory, payload.category_id) is None:
        raise HTTPException(status_code=400, detail="Unknown category_id")
    if db.query(Employee).filter(Employee.employee_code == payload.employee_code).first():
        raise HTTPException(status_code=409, detail="Employee code already exists")
    employee = Employee(**payload.model_dump())
    db.add(employee)
    db.commit()
    db.refresh(employee)
    return employee


@router.put("/{employee_id}", response_model=EmployeeOut)
def update_employee(
    employee_id: int,
    payload: EmployeeIn,
    db: Session = Depends(get_db),
    _: object = Depends(require_roles(Role.admin)),
) -> Employee:
    employee = db.get(Employee, employee_id)
    if employee is None:
        raise HTTPException(status_code=404, detail="Employee not found")
    for key, value in payload.model_dump().items():
        setattr(employee, key, value)
    db.commit()
    db.refresh(employee)
    return employee
