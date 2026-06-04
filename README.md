# Manpower & Equipment Request System

An MVP web application for managing daily **manpower and equipment requests**
from client sites (BNGL, GPP, DIV1 MQNT, …), checking availability against
**project-specific eligibility rules**, and moving requests through a
**supervisor → operations approval** workflow — replacing manual
WhatsApp/Excel coordination.

This is **Phase 1 / Section 10 (MVP)** of the project Method Statement, plus
an equipment module and a daily status board:

- Projects & project requirements (named after the client/division, e.g.
  `DIV1 MQNT`, with both a **client supervisor** who orders and a
  **company supervisor** from your team who responds)
- Employees / manpower database
- Manpower categories
- **Equipment inventory** (cranes, forklifts, buses, … — Section 4.3)
- Daily manpower **and equipment** request form
- Availability & eligibility checking (manpower and equipment)
- **Daily status board** — per project, manpower and equipment *in place*
  vs *shortage*, based on the company supervisor's daily confirmation
- Approval workflow (supervisor + operations)
- Operations dashboard

> Transport assignments, HSE verification, notifications and the standalone
> client portal are scoped for later phases and intentionally **not**
> included here.

## Tech stack

| Layer    | Choice                                                          |
| -------- | -------------------------------------------------------------- |
| Backend  | Python **FastAPI** + **SQLAlchemy 2.0**                        |
| Database | **SQLite** by default; **PostgreSQL** via `DATABASE_URL`       |
| Auth     | Role-based, PBKDF2 password hashing + HMAC-signed bearer tokens |
| Frontend | Lightweight static HTML/CSS/JS (mobile-responsive)             |

No external services are required to run the app — it works out of the box
on SQLite. Point `DATABASE_URL` at PostgreSQL for production.

## Quick start

```bash
./run.sh
```

Then open <http://localhost:8000>. Interactive API docs are at
<http://localhost:8000/docs>.

Or run manually:

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

### Demo logins (seeded automatically on first run)

| Username     | Password       | Role        |
| ------------ | -------------- | ----------- |
| `admin`      | `admin123`     | Admin / Operations Manager |
| `client`     | `client123`    | Client User |
| `supervisor` | `super123`     | Site Supervisor |
| `hse`        | `hse123`       | HSE |
| `transport`  | `transport123` | Transport Coordinator |
| `viewer`     | `viewer123`    | Viewer |

The seed also creates the **BNGL Station**, **GPP** and **DIV1 MQNT**
projects (each with a client supervisor and a company supervisor), the nine
manpower categories, ~78 employees, the eight equipment types and ~36
equipment items — all with a realistic spread of passport, PPE, medical,
inspection and assignment states so the availability checker and daily
status board have something meaningful to report.

## How availability checking works (Section 4.5)

For each requested category the engine reports:

```
Requested: 25 Laborers
Available: 30          (in category, status = available)
Eligible:  13          (also pass the project's eligibility rules)
Shortage:  12
Reason:    3 assigned to another project; 7 expired BGC passport;
           3 incomplete PPE; 4 missing BGC passport
```

An available employee is **eligible** for a project when they:

- are not currently assigned to a *different* project,
- hold the project's **required safety passport**, unexpired for the date,
- have **PPE** complete (if the project requires it),
- have a valid **medical** (if required), and
- hold any **required training** certificates.

## Approval workflow (Section 4.6)

```
draft → submitted → supervisor_review → operations_approval
      → confirmed → mobilized → closed
                  ↘ rejected
```

Each transition is restricted by role (e.g. only a client/admin may submit,
only a supervisor/admin may confirm manpower, only admin may give final
operations approval). Every transition is recorded in an approval audit
trail. Availability is automatically re-checked when a request enters
supervisor review or operations approval.

## Daily status — in place vs shortage

Each request line carries an **in place** quantity. Your **company
supervisor** opens the app each day and confirms how many of each manpower
category and equipment type are actually on site
(`POST /api/requests/{id}/confirm`); the system computes
**shortage = requested − in place** per line.

The **Daily Status** tab (`GET /api/dashboard/daily?on_date=YYYY-MM-DD`)
then shows, for every project active on that date:

```
DIV1 MQNT   client: Mr. Salim   our team: Mr. Jaafar      [shortage]
  Manpower   Laborer    requested 10  in place 7  shortage 3
  Equipment  Forklift   requested  2  in place 1  shortage 1
```

The planning availability engine (Section 4.5) still estimates how many are
*available/eligible* in the inventory for forecasting, while the in-place
confirmation reflects the actual situation on the ground.

## Project layout

```
app/
  main.py          FastAPI app, lifespan startup, static UI mount
  config.py        env-driven configuration (DATABASE_URL, secrets)
  database.py      engine + session factory + declarative base
  models.py        ORM models (users, projects, employees, requests, …)
  schemas.py       Pydantic request/response models
  auth.py          password hashing, token signing, RBAC dependencies
  availability.py  manpower + equipment availability checking engine
  workflow.py      approval transitions + daily in-place confirmation
  seed.py          demo data (projects, categories, equipment, employees)
  routers/         auth, projects, categories, employees, equipment,
                   availability, requests, dashboard
  static/          index.html, style.css, app.js (the UI)
tests/
  test_app.py      end-to-end tests (auth, RBAC, availability, equipment,
                   confirmation, daily status, workflow)
```

## Configuration

| Variable            | Default                  | Purpose                                  |
| ------------------- | ------------------------ | ---------------------------------------- |
| `DATABASE_URL`      | `sqlite:///./manpower.db`| DB connection (use `postgresql+psycopg://…`) |
| `SECRET_KEY`        | dev placeholder          | **Set in production** — signs auth tokens |
| `TOKEN_TTL_SECONDS` | `43200` (12h)            | Token lifetime                           |
| `SEED_ON_STARTUP`   | `true`                   | Seed demo data if the DB is empty        |

## Tests

```bash
pip install pytest httpx
python -m pytest -q
```

## Roadmap (later phases)

- **Phase 2:** Transport assignments, HSE verification, document
  expiry alerts, Excel/PDF export.
- **Phase 3:** Client portal (self-service request submission & tracking).
- **Phase 4:** AI assistant (shortage prediction, allocation suggestions,
  daily mobilization reports).
