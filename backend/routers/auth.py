import hashlib
import os
import secrets

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from passlib.context import CryptContext

from ..auth import get_current_user
from ..database import get_connection
from ..jwt_utils import create_token

router = APIRouter(prefix="/auth", tags=["auth"])
pwd_context = CryptContext(schemes=["bcrypt"])

class LoginIn(BaseModel):
    username: str
    password: str


class RegisterIn(BaseModel):
    username: str
    email: str
    password: str
    role: str = "user"

class TokenOut(BaseModel):
    token: str


def _load_admin_credentials() -> tuple[str, str, str]:
    """Return configured admin username, password and role."""

    username = os.getenv("ADMIN_USERNAME", "admin")
    password = os.getenv("ADMIN_PASSWORD", "admin")
    role = os.getenv("ADMIN_ROLE", "admin")
    return username, password, role


def _password_matches(candidate: str, stored: str) -> bool:
    """Validate ``candidate`` against the configured ``stored`` password."""

    try:
        identified = pwd_context.identify(stored)
    except Exception:  # pragma: no cover - defensive guard for unexpected formats
        identified = None

    if identified:
        try:
            return bool(pwd_context.verify(candidate, stored))
        except Exception:  # pragma: no cover - invalid bcrypt hash
            return False

    if len(stored) == 64:
        hashed = hashlib.sha256(candidate.encode()).hexdigest()
        if secrets.compare_digest(hashed, stored.lower()):
            return True

    return secrets.compare_digest(candidate, stored)


@router.post("/register")
def register(data: RegisterIn):
    hashed = pwd_context.hash(data.password)
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO users (username, email, hashed_password, role) VALUES (%s,%s,%s,%s) RETURNING id",
        (data.username, data.email, hashed, data.role),
    )
    user_id = cur.fetchone()[0]
    conn.commit()
    cur.close()
    conn.close()
    return {"id": user_id, "username": data.username, "email": data.email, "role": data.role}

@router.post("/login", response_model=TokenOut)
def login(data: LoginIn):
    expected_username, expected_password, role = _load_admin_credentials()

    if data.username != expected_username:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    if not _password_matches(data.password, expected_password):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    token = create_token({"user_id": 1, "role": role})
    return {"token": token}


@router.get("/verify")
def verify(_: dict = Depends(get_current_user)):
    return {"status": "ok"}
