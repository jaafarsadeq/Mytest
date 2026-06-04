"""FastAPI application entrypoint.

Creates tables, optionally seeds demo data, mounts the static UI, and
registers all API routers.
"""

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from . import __version__
from .config import SEED_ON_STARTUP
from .database import Base, SessionLocal, engine
from .routers import (
    auth,
    availability,
    categories,
    dashboard,
    employees,
    equipment,
    projects,
    requests,
)
from .seed import seed

STATIC_DIR = Path(__file__).parent / "static"


@asynccontextmanager
async def lifespan(_: FastAPI):
    Base.metadata.create_all(bind=engine)
    if SEED_ON_STARTUP:
        db = SessionLocal()
        try:
            seed(db)
        finally:
            db.close()
    yield


app = FastAPI(
    title="Manpower & Equipment Request System",
    version=__version__,
    description="MVP for managing daily manpower requests, availability "
    "checking, and supervisor/operations approval.",
    lifespan=lifespan,
)

app.include_router(auth.router)
app.include_router(projects.router)
app.include_router(categories.router)
app.include_router(employees.router)
app.include_router(equipment.router)
app.include_router(availability.router)
app.include_router(requests.router)
app.include_router(dashboard.router)


@app.get("/api/health", tags=["health"])
def health() -> dict:
    return {"status": "ok", "version": __version__}


@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


# Serve the lightweight UI (CSS/JS) under /static.
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
