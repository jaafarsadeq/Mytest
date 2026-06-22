"""Authentication and authorization helpers.

Uses only the standard library (PBKDF2 password hashing + HMAC-signed
tokens) so no extra crypto dependencies are needed for the MVP.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
from collections.abc import Iterable

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from .config import SECRET_KEY, TOKEN_TTL_SECONDS
from .database import get_db
from .models import Role, User

_PBKDF2_ROUNDS = 200_000
bearer_scheme = HTTPBearer(auto_error=False)


# --- Password hashing ---------------------------------------------------------

def hash_password(password: str) -> str:
    """Return a salted PBKDF2-SHA256 hash, encoded as ``rounds$salt$hash``."""
    salt = secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, _PBKDF2_ROUNDS)
    return f"{_PBKDF2_ROUNDS}${salt.hex()}${dk.hex()}"


def verify_password(password: str, stored: str) -> bool:
    """Verify a password against a stored PBKDF2 hash in constant time."""
    try:
        rounds_s, salt_hex, hash_hex = stored.split("$")
        rounds = int(rounds_s)
        salt = bytes.fromhex(salt_hex)
    except (ValueError, AttributeError):
        return False
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, rounds)
    return hmac.compare_digest(dk.hex(), hash_hex)


# --- Token signing ------------------------------------------------------------

def _b64encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _b64decode(data: str) -> bytes:
    pad = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + pad)


def create_token(user: User) -> str:
    """Create a signed token carrying the user id, role, and expiry."""
    payload = {
        "sub": user.id,
        "role": user.role.value,
        "exp": int(time.time()) + TOKEN_TTL_SECONDS,
    }
    body = _b64encode(json.dumps(payload, separators=(",", ":")).encode())
    sig = hmac.new(SECRET_KEY.encode(), body.encode(), hashlib.sha256).digest()
    return f"{body}.{_b64encode(sig)}"


def decode_token(token: str) -> dict:
    """Validate a token's signature and expiry, returning its payload."""
    try:
        body, sig = token.split(".")
    except ValueError as exc:
        raise ValueError("malformed token") from exc
    expected = hmac.new(SECRET_KEY.encode(), body.encode(), hashlib.sha256).digest()
    if not hmac.compare_digest(_b64decode(sig), expected):
        raise ValueError("bad signature")
    payload = json.loads(_b64decode(body))
    if payload.get("exp", 0) < int(time.time()):
        raise ValueError("token expired")
    return payload


# --- FastAPI dependencies -----------------------------------------------------

def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    """Resolve the authenticated user from the bearer token."""
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        payload = decode_token(credentials.credentials)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid token: {exc}",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc
    user = db.get(User, payload["sub"])
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unknown user")
    return user


def require_roles(*roles: Role):
    """Dependency factory enforcing that the user holds one of ``roles``."""

    allowed = set(roles)

    def checker(user: User = Depends(get_current_user)) -> User:
        if user.role not in allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Requires one of roles: {', '.join(r.value for r in allowed)}",
            )
        return user

    return checker


def roles_label(roles: Iterable[Role]) -> str:
    return ", ".join(r.value for r in roles)
