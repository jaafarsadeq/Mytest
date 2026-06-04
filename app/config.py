"""Application configuration.

Reads from environment variables so the same code runs against SQLite
(default, zero external services) or PostgreSQL in production by setting
``DATABASE_URL`` (e.g. ``postgresql+psycopg://user:pass@host/db``).
"""

import os

# Default to a local SQLite file so the app runs with no external services.
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./manpower.db")

# Secret used to sign auth tokens. Override in production via env var.
SECRET_KEY = os.getenv("SECRET_KEY", "change-me-in-production-please")

# Token lifetime in seconds (default: 12 hours).
TOKEN_TTL_SECONDS = int(os.getenv("TOKEN_TTL_SECONDS", str(12 * 60 * 60)))

# Whether to seed demo data (projects, employees, users) on startup.
SEED_ON_STARTUP = os.getenv("SEED_ON_STARTUP", "true").lower() in {"1", "true", "yes"}
