"""End-to-end tests covering auth, availability checking, and the workflow.

Runs against a temporary SQLite database so it needs no external services.
"""

import os
import tempfile
from datetime import date, timedelta

import pytest

# Use an isolated temp DB before importing the app.
_tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp.name}"
os.environ["SEED_ON_STARTUP"] = "true"

from fastapi.testclient import TestClient  # noqa: E402

from app.database import Base, SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models import (  # noqa: E402
    AvailabilityStatus,
    Employee,
    ManpowerCategory,
    Project,
    ProjectRequirement,
)
from app.seed import seed  # noqa: E402


@pytest.fixture(scope="module")
def client():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    seed(db)
    db.close()
    with TestClient(app) as c:
        yield c


def auth_header(client, username, password):
    res = client.post("/api/auth/login", json={"username": username, "password": password})
    assert res.status_code == 200, res.text
    return {"Authorization": f"Bearer {res.json()['access_token']}"}


def test_login_success_and_failure(client):
    assert "access_token" in client.post(
        "/api/auth/login", json={"username": "admin", "password": "admin123"}
    ).json()
    bad = client.post("/api/auth/login", json={"username": "admin", "password": "wrong"})
    assert bad.status_code == 401


def test_requires_auth(client):
    assert client.get("/api/projects").status_code == 401


def test_projects_and_categories_seeded(client):
    headers = auth_header(client, "admin", "admin123")
    projects = client.get("/api/projects", headers=headers).json()
    names = {p["name"] for p in projects}
    assert {"BNGL Station", "GPP"} <= names
    cats = client.get("/api/categories", headers=headers).json()
    assert any(c["name"] == "Laborer" for c in cats)


def test_rbac_client_cannot_create_project(client):
    headers = auth_header(client, "client", "client123")
    res = client.post("/api/projects", headers=headers, json={"name": "X"})
    assert res.status_code == 403


def test_availability_check_reports_shortage():
    """Use a controlled dataset to assert the eligibility math exactly."""
    db = SessionLocal()
    try:
        cat = ManpowerCategory(name="TestLaborer")
        db.add(cat)
        db.flush()
        project = Project(name="TestProj")
        project.requirement = ProjectRequirement(required_passport="BGC", requires_ppe=True)
        db.add(project)
        db.flush()

        today = date.today()
        valid = today + timedelta(days=30)
        expired = today - timedelta(days=1)
        # 3 eligible, 1 expired passport, 1 wrong passport, 1 no PPE, 1 assigned elsewhere
        other = Project(name="OtherProj")
        db.add(other)
        db.flush()
        specs = [
            ("BGC", valid, True, None),       # eligible
            ("BGC", valid, True, None),       # eligible
            ("BGC", valid, True, None),       # eligible
            ("BGC", expired, True, None),     # expired passport
            ("GPP", valid, True, None),       # wrong passport
            ("BGC", valid, False, None),      # no PPE
            ("BGC", valid, True, other.id),   # assigned elsewhere
        ]
        for i, (ptype, exp, ppe, proj) in enumerate(specs):
            db.add(
                Employee(
                    employee_code=f"T{i}",
                    name=f"T{i}",
                    category_id=cat.id,
                    availability_status=AvailabilityStatus.available,
                    passport_type=ptype,
                    passport_expiry=exp,
                    ppe_status=ppe,
                    current_project_id=proj,
                )
            )
        db.commit()

        from app.availability import check_category

        result = check_category(db, project, cat, requested=5, on_date=today)
        assert result.available == 7
        assert result.eligible == 3
        assert result.shortage == 2
        assert any("expired" in r for r in result.reasons)
        assert any("assigned to another project" in r for r in result.reasons)
    finally:
        db.close()


def test_full_request_workflow(client):
    client_headers = auth_header(client, "client", "client123")
    super_headers = auth_header(client, "supervisor", "super123")
    admin_headers = auth_header(client, "admin", "admin123")

    projects = client.get("/api/projects", headers=admin_headers).json()
    bngl = next(p for p in projects if p["name"] == "BNGL Station")
    cats = client.get("/api/categories", headers=admin_headers).json()
    laborer = next(c for c in cats if c["name"] == "Laborer")

    # Client creates a request.
    create = client.post(
        "/api/requests",
        headers=client_headers,
        json={
            "project_id": bngl["id"],
            "required_date": str(date.today()),
            "items": [{"category_id": laborer["id"], "quantity": 25}],
        },
    )
    assert create.status_code == 201, create.text
    req = create.json()
    assert req["status"] == "draft"
    assert req["items"][0]["available_qty"] >= req["items"][0]["eligible_qty"]
    rid = req["id"]

    # Client submits.
    r = client.post(f"/api/requests/{rid}/transition/submitted", headers=client_headers)
    assert r.status_code == 200 and r.json()["status"] == "submitted"

    # Supervisor cannot skip straight to confirmed.
    bad = client.post(
        f"/api/requests/{rid}/transition/confirmed", headers=super_headers
    )
    assert bad.status_code == 403

    # Supervisor reviews then confirms manpower.
    client.post(f"/api/requests/{rid}/transition/supervisor_review", headers=super_headers)
    client.post(
        f"/api/requests/{rid}/transition/operations_approval", headers=super_headers
    )
    # Operations (admin) approves, then mobilizes, then closes.
    client.post(f"/api/requests/{rid}/transition/confirmed", headers=admin_headers)
    mob = client.post(f"/api/requests/{rid}/transition/mobilized", headers=admin_headers)
    assert mob.json()["status"] == "mobilized"
    closed = client.post(f"/api/requests/{rid}/transition/closed", headers=admin_headers)
    assert closed.json()["status"] == "closed"

    # Approvals audit trail recorded.
    detail = client.get(f"/api/requests/{rid}", headers=admin_headers).json()
    assert len(detail["approvals"]) >= 5


def test_dashboard_summary(client):
    headers = auth_header(client, "viewer", "viewer123")
    data = client.get("/api/dashboard/summary", headers=headers).json()
    assert data["total_available_manpower"] > 0
    assert any(row["project"] == "BNGL Station" for row in data["projects"])
