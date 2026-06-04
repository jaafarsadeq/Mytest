"""Seed demo data for testing the workflow with BNGL and GPP (Phase 1)."""

from __future__ import annotations

import random
from datetime import date, timedelta

from sqlalchemy.orm import Session

from .auth import hash_password
from .models import (
    AvailabilityStatus,
    Employee,
    Equipment,
    EquipmentType,
    ManpowerCategory,
    Project,
    ProjectRequirement,
    Role,
    User,
)

EQUIPMENT_TYPES = [
    "Crane",
    "Forklift",
    "Pickup",
    "Bus",
    "Coaster",
    "Excavator",
    "Generator",
    "Air compressor",
]

DEMO_USERS = [
    ("admin", "admin123", "Operations Manager", Role.admin),
    ("client", "client123", "BNGL Client User", Role.client),
    ("supervisor", "super123", "Site Supervisor", Role.supervisor),
    ("hse", "hse123", "HSE Officer", Role.hse),
    ("transport", "transport123", "Transport Coordinator", Role.transport),
    ("viewer", "viewer123", "Management Viewer", Role.viewer),
]

CATEGORIES = [
    "Laborer",
    "Electrician",
    "Rigger",
    "Mechanical fitter",
    "Scaffolder",
    "Civil worker",
    "Steel bar fixer",
    "Driver",
    "Operator",
]

NATIONALITIES = ["Indian", "Pakistani", "Bangladeshi", "Filipino", "Nepali", "Egyptian"]


def already_seeded(db: Session) -> bool:
    return db.query(User).first() is not None


def seed(db: Session) -> None:
    if already_seeded(db):
        return

    today = date.today()

    # --- Categories -----------------------------------------------------------
    categories = {name: ManpowerCategory(name=name) for name in CATEGORIES}
    db.add_all(categories.values())
    db.flush()

    # --- Equipment types ------------------------------------------------------
    eq_types = {name: EquipmentType(name=name) for name in EQUIPMENT_TYPES}
    db.add_all(eq_types.values())
    db.flush()

    # --- Projects + requirements ---------------------------------------------
    # Each project is named after the client division; client_name mirrors it.
    bngl = Project(
        name="BNGL Station",
        client_name="BNGL Station",
        site_location="Basrah",
        station="Station 4",
        working_hours="07:00-17:00",
        supervisor_name="Site Supervisor",
        client_supervisor="Mr. Ali (Client)",
        company_supervisor="Mr. Hassan (Our Team)",
        hse_contact="HSE Officer",
        transport_rules="Transport from camp mandatory",
        requirement=ProjectRequirement(
            required_passport="BGC",
            requires_ppe=True,
            requires_medical=False,
            transport_required=True,
            notes="Black and white safety glasses, gloves, ear plugs.",
        ),
    )
    gpp = Project(
        name="GPP",
        client_name="GPP",
        site_location="Gas Plant",
        station="Unit 2",
        working_hours="06:00-16:00",
        supervisor_name="Site Supervisor",
        client_supervisor="Mr. Omar (Client)",
        company_supervisor="Mr. Karim (Our Team)",
        hse_contact="HSE Officer",
        transport_rules="Transport from camp",
        requirement=ProjectRequirement(
            required_passport="GPP",
            requires_ppe=True,
            requires_medical=True,
            transport_required=True,
            notes="Plant induction + medical required.",
        ),
    )
    mqnt = Project(
        name="DIV1 MQNT",
        client_name="DIV1 MQNT",
        site_location="Majnoon",
        station="Division 1",
        working_hours="07:00-17:00",
        supervisor_name="Site Supervisor",
        client_supervisor="Mr. Salim (Client)",
        company_supervisor="Mr. Jaafar (Our Team)",
        hse_contact="HSE Officer",
        transport_rules="Transport from camp",
        requirement=ProjectRequirement(
            required_passport="BGC",
            requires_ppe=True,
            requires_medical=False,
            transport_required=True,
            notes="BGC passport + PPE required.",
        ),
    )
    db.add_all([bngl, gpp, mqnt])
    db.flush()

    # --- Equipment inventory --------------------------------------------------
    valid_inspection = today + timedelta(days=200)
    expired_inspection = today - timedelta(days=5)
    eq_rng = random.Random(7)
    eq_counter = 0
    for type_name, count in [
        ("Crane", 3),
        ("Forklift", 6),
        ("Pickup", 8),
        ("Bus", 5),
        ("Coaster", 4),
        ("Excavator", 3),
        ("Generator", 4),
        ("Air compressor", 3),
    ]:
        eq_type = eq_types[type_name]
        for _ in range(count):
            eq_counter += 1
            inspection_expired = eq_rng.random() < 0.15
            assigned_gpp = eq_rng.random() < 0.1
            db.add(
                Equipment(
                    equipment_code=f"EQP{eq_counter:04d}",
                    type_id=eq_type.id,
                    capacity="-",
                    plate_number=f"PL-{1000 + eq_counter}",
                    current_project_id=gpp.id if assigned_gpp else None,
                    current_location="Yard",
                    availability_status=AvailabilityStatus.available,
                    inspection_expiry=(
                        expired_inspection if inspection_expired else valid_inspection
                    ),
                    ivms_status=eq_rng.random() < 0.8,
                    maintenance_status="ok",
                    fuel_status="full",
                )
            )

    # --- Users ----------------------------------------------------------------
    for username, password, full_name, role in DEMO_USERS:
        project_id = bngl.id if role is Role.client else None
        db.add(
            User(
                username=username,
                full_name=full_name,
                hashed_password=hash_password(password),
                role=role,
                project_id=project_id,
            )
        )

    # --- Employees ------------------------------------------------------------
    # Deterministic spread so the availability demo is reproducible.
    rng = random.Random(42)
    valid_passport = today + timedelta(days=180)
    expired_passport = today - timedelta(days=10)
    valid_medical = today + timedelta(days=120)

    counter = 0
    for cat_name, count in [
        ("Laborer", 30),
        ("Electrician", 8),
        ("Rigger", 6),
        ("Mechanical fitter", 10),
        ("Scaffolder", 5),
        ("Civil worker", 6),
        ("Steel bar fixer", 4),
        ("Driver", 5),
        ("Operator", 4),
    ]:
        category = categories[cat_name]
        for _ in range(count):
            counter += 1
            # ~70% hold BGC, ~20% GPP, ~10% none — to create eligibility gaps.
            roll = rng.random()
            if roll < 0.7:
                passport_type = "BGC"
            elif roll < 0.9:
                passport_type = "GPP"
            else:
                passport_type = ""
            passport_expired = rng.random() < 0.15
            assigned_gpp = rng.random() < 0.1

            db.add(
                Employee(
                    employee_code=f"EMP{counter:04d}",
                    name=f"{cat_name} Worker {counter}",
                    nationality=rng.choice(NATIONALITIES),
                    category_id=category.id,
                    # Kept "available" but tied to GPP so the BNGL check
                    # reports them as "assigned to another project".
                    current_project_id=gpp.id if assigned_gpp else None,
                    current_location="Camp A",
                    availability_status=AvailabilityStatus.available,
                    passport_type=passport_type,
                    passport_expiry=(
                        expired_passport if passport_expired else valid_passport
                    ),
                    ppe_status=rng.random() < 0.85,
                    medical_expiry=valid_medical if rng.random() < 0.8 else None,
                    training_certificates="H2S, Fire Safety",
                    camp_location="Camp A",
                    transport_route="Route 1",
                    supervisor="Site Supervisor",
                )
            )

    db.commit()
