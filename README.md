# Manpower & Equipment Request System

An MVP web application for managing daily **manpower requests** from client
sites (BNGL, GPP, MQ, EPC, ROO, …), checking availability against
**project-specific eligibility rules**, and moving requests through a
**supervisor → operations approval** workflow — replacing manual
WhatsApp/Excel coordination.

This is **Phase 1 / Section 10 (MVP)** of the project Method Statement:

- Projects & project requirements
- Employees / manpower database
- Manpower categories
- Daily manpower request form
- Availability & eligibility checking
- Approval workflow (supervisor + operations)
- Operations dashboard

> Equipment, transport, HSE verification, notifications and the client
> portal are scoped for later phases and intentionally **not** included here.

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

The seed also creates the **BNGL Station** and **GPP** projects, the nine
manpower categories, and ~78 employees with a realistic spread of passport,
PPE, medical and assignment states so the availability checker has
something meaningful to report.

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

## Project layout

```
app/
  main.py          FastAPI app, lifespan startup, static UI mount
  config.py        env-driven configuration (DATABASE_URL, secrets)
  database.py      engine + session factory + declarative base
  models.py        ORM models (users, projects, employees, requests, …)
  schemas.py       Pydantic request/response models
  auth.py          password hashing, token signing, RBAC dependencies
  availability.py  eligibility/availability checking engine
  workflow.py      approval-workflow transition rules
  seed.py          demo data (BNGL, GPP, categories, employees, users)
  routers/         auth, projects, categories, employees,
                   availability, requests, dashboard
  static/          index.html, style.css, app.js (the UI)
tests/
  test_app.py      end-to-end tests (auth, RBAC, availability, workflow)
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

- **Phase 2:** Equipment & transport modules, HSE verification, document
  expiry alerts, Excel/PDF export.
- **Phase 3:** Client portal (self-service request submission & tracking).
- **Phase 4:** AI assistant (shortage prediction, allocation suggestions,
  daily mobilization reports).
