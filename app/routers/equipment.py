"""Equipment inventory endpoints (Section 4.3)."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..auth import get_current_user, require_roles
from ..database import get_db
from ..models import Equipment, EquipmentType, Role
from ..schemas import (
    EquipmentIn,
    EquipmentOut,
    EquipmentTypeIn,
    EquipmentTypeOut,
)

router = APIRouter(prefix="/api/equipment", tags=["equipment"])


# --- Equipment types ----------------------------------------------------------

@router.get("/types", response_model=list[EquipmentTypeOut])
def list_types(
    db: Session = Depends(get_db), _: object = Depends(get_current_user)
) -> list[EquipmentType]:
    return db.query(EquipmentType).order_by(EquipmentType.name).all()


@router.post("/types", response_model=EquipmentTypeOut, status_code=201)
def create_type(
    payload: EquipmentTypeIn,
    db: Session = Depends(get_db),
    _: object = Depends(require_roles(Role.admin)),
) -> EquipmentType:
    if db.query(EquipmentType).filter(EquipmentType.name == payload.name).first():
        raise HTTPException(status_code=409, detail="Equipment type already exists")
    eq_type = EquipmentType(name=payload.name, description=payload.description)
    db.add(eq_type)
    db.commit()
    db.refresh(eq_type)
    return eq_type


# --- Equipment inventory ------------------------------------------------------

@router.get("", response_model=list[EquipmentOut])
def list_equipment(
    type_id: int | None = None,
    project_id: int | None = None,
    db: Session = Depends(get_db),
    _: object = Depends(get_current_user),
) -> list[Equipment]:
    query = db.query(Equipment)
    if type_id is not None:
        query = query.filter(Equipment.type_id == type_id)
    if project_id is not None:
        query = query.filter(Equipment.current_project_id == project_id)
    return query.order_by(Equipment.equipment_code).all()


@router.post("", response_model=EquipmentOut, status_code=201)
def create_equipment(
    payload: EquipmentIn,
    db: Session = Depends(get_db),
    _: object = Depends(require_roles(Role.admin)),
) -> Equipment:
    if db.get(EquipmentType, payload.type_id) is None:
        raise HTTPException(status_code=400, detail="Unknown type_id")
    if db.query(Equipment).filter(Equipment.equipment_code == payload.equipment_code).first():
        raise HTTPException(status_code=409, detail="Equipment code already exists")
    equipment = Equipment(**payload.model_dump())
    db.add(equipment)
    db.commit()
    db.refresh(equipment)
    return equipment


@router.put("/{equipment_id}", response_model=EquipmentOut)
def update_equipment(
    equipment_id: int,
    payload: EquipmentIn,
    db: Session = Depends(get_db),
    _: object = Depends(require_roles(Role.admin)),
) -> Equipment:
    equipment = db.get(Equipment, equipment_id)
    if equipment is None:
        raise HTTPException(status_code=404, detail="Equipment not found")
    for key, value in payload.model_dump().items():
        setattr(equipment, key, value)
    db.commit()
    db.refresh(equipment)
    return equipment
