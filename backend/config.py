import os
from typing import List


def _normalize_origin(value: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError("Frontend origin is empty")
    return normalized.rstrip("/")


def get_client_frontend_origin() -> str:
    origin = os.getenv("CLIENT_FRONTEND_ORIGIN", "")
    if not origin.strip():
        raise RuntimeError("CLIENT_FRONTEND_ORIGIN is not configured")
    return _normalize_origin(origin)


def get_admin_frontend_origin() -> str | None:
    origin = os.getenv("ADMIN_FRONTEND_ORIGIN", "")
    if not origin.strip():
        return None
    return _normalize_origin(origin)


def get_frontend_origins() -> List[str]:
    origins = [get_client_frontend_origin()]
    admin_origin = get_admin_frontend_origin()
    if admin_origin:
        origins.append(admin_origin)
    return origins
