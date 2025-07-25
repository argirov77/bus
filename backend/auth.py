from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import os
import jwt

from .jwt_utils import decode_token

security = HTTPBearer(auto_error=False)


def _get_payload(credentials: HTTPAuthorizationCredentials | None) -> dict:
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing admin token",
        )
    try:
        payload = decode_token(credentials.credentials)
    except jwt.PyJWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing admin token",
        )
    return payload


def require_admin_token(
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
):
    payload = _get_payload(credentials)
    if payload.get("role") != "admin":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing admin token",
        )
    return payload



def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
):
    return _get_payload(credentials)
