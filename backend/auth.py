from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import os

security = HTTPBearer(auto_error=False)


def require_admin_token(
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
):
    """Ensure the provided token matches ``ADMIN_TOKEN``."""
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing admin token",
        )

    expected = os.getenv("ADMIN_TOKEN", "adminsecret")
    if credentials.credentials != expected:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing admin token",
        )

    return {"role": "admin"}
