from typing import Literal

import httpx
from fastapi import APIRouter, Depends
from pydantic import BaseModel

from ..auth import require_admin_token
from ..services import checkbox

router = APIRouter(
    prefix="/admin/integrations",
    tags=["admin_integrations"],
    dependencies=[Depends(require_admin_token)],
)


class CheckBoxHealthResponse(BaseModel):
    status: Literal["ok", "warning", "error", "disabled"]
    http_status: int | None = None
    message: str
    details: list[str]


@router.get("/checkbox/health", response_model=CheckBoxHealthResponse)
def checkbox_health() -> CheckBoxHealthResponse:
    if not checkbox.is_enabled():
        return CheckBoxHealthResponse(
            status="disabled",
            message="CheckBox integration is disabled via CHECKBOX_ENABLED.",
            details=["CHECKBOX_ENABLED=false"],
        )

    missing_required: list[str] = []
    for key in ("CHECKBOX_CASHIER_LOGIN", "CHECKBOX_CASHIER_PASSWORD"):
        if not checkbox._env(key):
            missing_required.append(key)

    optional_missing = [
        key
        for key in ("CHECKBOX_LICENSE_KEY",)
        if not checkbox._env(key)
    ]

    if missing_required:
        return CheckBoxHealthResponse(
            status="error",
            message="Missing required CheckBox credentials.",
            details=[f"missing env: {k}" for k in missing_required],
        )

    details: list[str] = []
    if optional_missing:
        details.extend([f"optional env missing: {k}" for k in optional_missing])

    try:
        token = checkbox.get_token_for_healthcheck()
        details.append("cashier signin: ok")

        shift_http_status, shift_data = checkbox.get_cashier_shift_status(token)
        shift_status = (shift_data or {}).get("status") if isinstance(shift_data, dict) else None
        details.append(f"cashier shift check: http {shift_http_status}, status={shift_status or 'unknown'}")

        return CheckBoxHealthResponse(
            status="warning" if optional_missing else "ok",
            http_status=shift_http_status,
            message="CheckBox integration is operational." if not optional_missing else "CheckBox works but optional keys are missing.",
            details=details,
        )
    except httpx.HTTPStatusError as exc:
        code = exc.response.status_code
        if code in (401, 403):
            message = "CheckBox authorization failed: неверные креды/доступ."
        else:
            message = f"CheckBox returned HTTP {code}."
        details.append(f"http error at {exc.request.method} {exc.request.url}")
        return CheckBoxHealthResponse(
            status="error",
            http_status=code,
            message=message,
            details=details,
        )
    except (httpx.ConnectError, httpx.ReadTimeout, httpx.ConnectTimeout, httpx.NetworkError):
        return CheckBoxHealthResponse(
            status="error",
            message="CheckBox network error (network): timeout/DNS/connectivity issue.",
            details=["network"],
        )
    except RuntimeError as exc:
        return CheckBoxHealthResponse(
            status="error",
            message=str(exc),
            details=details,
        )
