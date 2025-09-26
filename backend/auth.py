from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, List, Optional

import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .jwt_utils import decode_token
from .services import ticket_links

security = HTTPBearer(auto_error=False)


@dataclass
class RequestContext:
    """Holds authentication context for the current request."""

    is_admin: bool
    admin: Optional[dict[str, Any]] = None
    link: Optional[dict[str, Any]] = None
    scopes: List[str] = field(default_factory=list)
    ticket_id: Optional[Any] = None
    purchase_id: Optional[Any] = None
    lang: Optional[str] = None
    jti: Optional[str] = None


def _populate_request_state(request: Request, context: RequestContext) -> None:
    """Copy context data to the request state for downstream handlers."""

    request.state.is_admin = context.is_admin
    request.state.admin = context.admin
    request.state.link_scopes = context.scopes
    request.state.ticket_id = context.ticket_id
    request.state.purchase_id = context.purchase_id
    request.state.lang = context.lang
    request.state.jti = context.jti
    request.state.request_context = context


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


def get_request_context(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
) -> RequestContext:
    """Resolve authentication context for the incoming request."""

    admin_error: HTTPException | None = None

    # Try admin bearer token first
    if credentials and credentials.scheme.lower() == "bearer":
        try:
            payload = _get_payload(credentials)
        except HTTPException as exc:  # Invalid admin token, fall back to link token
            admin_error = exc
        else:
            if payload.get("role") == "admin":
                context = RequestContext(is_admin=True, admin=payload, scopes=[])
                _populate_request_state(request, context)
                return context
            admin_error = HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or missing admin token",
            )

    token = request.headers.get("X-Ticket-Token") or request.query_params.get("token")
    if not token:
        if admin_error is not None:
            raise admin_error
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing ticket token",
        )

    try:
        payload = ticket_links.verify(token)
    except ticket_links.TicketLinkError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing ticket token",
        ) from exc

    raw_scopes = payload.get("scopes")
    if raw_scopes is None:
        scopes: List[str] = []
    elif isinstance(raw_scopes, (list, tuple, set)):
        scopes = [str(scope) for scope in raw_scopes]
    else:
        scopes = [str(raw_scopes)]
    context = RequestContext(
        is_admin=False,
        link=payload,
        scopes=scopes,
        ticket_id=payload.get("ticket_id"),
        purchase_id=payload.get("purchase_id"),
        lang=payload.get("lang"),
        jti=payload.get("jti"),
    )

    _populate_request_state(request, context)

    return context


def require_link_token(context: RequestContext = Depends(get_request_context)) -> RequestContext:
    """Ensure that a request has either an admin or ticket link token."""

    return context


def require_scope(*scopes: str):
    """Dependency factory for ensuring a request has the required scopes."""

    async def dependency(
        request: Request,
        context: RequestContext = Depends(require_link_token),
    ) -> RequestContext:
        if context.is_admin:
            return context

        if scopes and not all(scope in context.scopes for scope in scopes):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient scope",
            )
        return context

    return dependency
