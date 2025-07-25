from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import os

router = APIRouter(prefix="/auth", tags=["auth"])

class LoginIn(BaseModel):
    username: str
    password: str

class TokenOut(BaseModel):
    token: str

@router.post("/login", response_model=TokenOut)
def login(data: LoginIn):
    expected_user = os.getenv("ADMIN_USERNAME", "admin")
    expected_pass = os.getenv("ADMIN_PASSWORD", "admin")
    if data.username != expected_user or data.password != expected_pass:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    token = os.getenv("ADMIN_TOKEN", "adminsecret")
    return {"token": token}
