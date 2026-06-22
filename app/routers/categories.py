"""Manpower category endpoints."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..auth import get_current_user, require_roles
from ..database import get_db
from ..models import ManpowerCategory, Role
from ..schemas import CategoryIn, CategoryOut

router = APIRouter(prefix="/api/categories", tags=["categories"])


@router.get("", response_model=list[CategoryOut])
def list_categories(
    db: Session = Depends(get_db), _: object = Depends(get_current_user)
) -> list[ManpowerCategory]:
    return db.query(ManpowerCategory).order_by(ManpowerCategory.name).all()


@router.post("", response_model=CategoryOut, status_code=201)
def create_category(
    payload: CategoryIn,
    db: Session = Depends(get_db),
    _: object = Depends(require_roles(Role.admin)),
) -> ManpowerCategory:
    if db.query(ManpowerCategory).filter(ManpowerCategory.name == payload.name).first():
        raise HTTPException(status_code=409, detail="Category already exists")
    category = ManpowerCategory(name=payload.name, description=payload.description)
    db.add(category)
    db.commit()
    db.refresh(category)
    return category
