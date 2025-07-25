from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from passlib.context import CryptContext

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
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT id, hashed_password, role FROM users WHERE username=%s", (data.username,)
    )
    row = cur.fetchone()
    cur.close()
    conn.close()
    if not row or not pwd_context.verify(data.password, row[1]):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    token = create_token({"user_id": row[0], "role": row[2]})
    return {"token": token}
