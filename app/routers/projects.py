"""Project master endpoints (Section 4.1)."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..auth import get_current_user, require_roles
from ..database import get_db
from ..models import Project, ProjectRequirement, Role
from ..schemas import ProjectIn, ProjectOut

router = APIRouter(prefix="/api/projects", tags=["projects"])


@router.get("", response_model=list[ProjectOut])
def list_projects(
    db: Session = Depends(get_db), _: object = Depends(get_current_user)
) -> list[Project]:
    return db.query(Project).order_by(Project.name).all()


@router.get("/{project_id}", response_model=ProjectOut)
def get_project(
    project_id: int, db: Session = Depends(get_db), _: object = Depends(get_current_user)
) -> Project:
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


@router.post("", response_model=ProjectOut, status_code=201)
def create_project(
    payload: ProjectIn,
    db: Session = Depends(get_db),
    _: object = Depends(require_roles(Role.admin)),
) -> Project:
    if db.query(Project).filter(Project.name == payload.name).first():
        raise HTTPException(status_code=409, detail="Project already exists")
    data = payload.model_dump(exclude={"requirement"})
    # Client name mirrors the project/division name when not given explicitly.
    if not data.get("client_name"):
        data["client_name"] = payload.name
    project = Project(**data)
    if payload.requirement is not None:
        project.requirement = ProjectRequirement(**payload.requirement.model_dump())
    db.add(project)
    db.commit()
    db.refresh(project)
    return project


@router.put("/{project_id}", response_model=ProjectOut)
def update_project(
    project_id: int,
    payload: ProjectIn,
    db: Session = Depends(get_db),
    _: object = Depends(require_roles(Role.admin)),
) -> Project:
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    for key, value in payload.model_dump(exclude={"requirement"}).items():
        setattr(project, key, value)
    if not project.client_name:
        project.client_name = project.name
    if payload.requirement is not None:
        if project.requirement is None:
            project.requirement = ProjectRequirement(**payload.requirement.model_dump())
        else:
            for key, value in payload.requirement.model_dump().items():
                setattr(project.requirement, key, value)
    db.commit()
    db.refresh(project)
    return project
