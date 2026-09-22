from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Callable

from fastapi import Cookie, Depends, Header, HTTPException, Request, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .db import get_db, settings
from .models import Membership, Organization, Session, User

SESSION_COOKIE = "__Host-session" if settings.auth_cookie_secure else "session"
CSRF_COOKIE = "__Host-csrf" if settings.auth_cookie_secure else "csrf"
ROLE_PERMISSIONS = {
    "owner": {"*"},
    "admin": {"admin:manage", "finance:write", "finance:approve", "finance:post", "tax:write", "audit:read"},
    "tax": {"tax:write", "finance:write", "audit:read"},
    "finance": {"finance:write", "finance:approve", "finance:post", "audit:read"},
    "auditor": {"audit:read"},
    "viewer": set(),
}

@dataclass(frozen=True)
class CurrentUser:
    user_id: int
    organization_id: int
    email: str
    display_name: str
    role: str
    session_id: int


def _hash_password(password: str, salt: bytes | None = None) -> str:
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=2**15, r=8, p=1, dklen=32)
    return "scrypt$32768$8$1$" + base64.urlsafe_b64encode(salt).decode() + "$" + base64.urlsafe_b64encode(digest).decode()


def verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, n, r, p, salt_b64, digest_b64 = encoded.split("$")
        if algorithm != "scrypt":
            return False
        salt = base64.urlsafe_b64decode(salt_b64.encode())
        expected = base64.urlsafe_b64decode(digest_b64.encode())
        actual = hashlib.scrypt(password.encode(), salt=salt, n=int(n), r=int(r), p=int(p), dklen=len(expected))
        return hmac.compare_digest(actual, expected)
    except (ValueError, TypeError):
        return False


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _set_auth_cookies(response: Response, session_token: str, csrf_token: str, expires: datetime) -> None:
    common = {"secure": settings.auth_cookie_secure, "httponly": True, "samesite": "strict", "path": "/", "expires": expires}
    response.set_cookie(SESSION_COOKIE, session_token, **common)
    response.set_cookie(CSRF_COOKIE, csrf_token, secure=settings.auth_cookie_secure, httponly=False, samesite="strict", path="/", expires=expires)


async def authenticate(db: AsyncSession, email: str, password: str, organization_id: int) -> tuple[Session, User, Membership, str, str]:
    user = await db.scalar(select(User).where(User.email == email.strip().lower(), User.is_active.is_(True)))
    if not user or not verify_password(password, user.password_hash):
        raise HTTPException(status_code=401, detail={"error": {"code": "AUTHENTICATION_FAILED", "message": "Invalid credentials."}})
    membership = await db.scalar(select(Membership).where(Membership.user_id == user.id, Membership.organization_id == organization_id))
    if not membership:
        raise HTTPException(status_code=403, detail={"error": {"code": "ORGANIZATION_ACCESS_DENIED", "message": "You do not have access to this organization."}})
    now = datetime.now(timezone.utc)
    session_token = secrets.token_urlsafe(32)
    csrf_token = secrets.token_urlsafe(32)
    session = Session(user_id=user.id, organization_id=organization_id, token_hash=_token_hash(session_token), csrf_hash=_token_hash(csrf_token), expires_at=now + timedelta(hours=settings.session_ttl_hours))
    db.add(session)
    await db.flush()
    return session, user, membership, session_token, csrf_token


async def current_user(session_token: str | None, db: AsyncSession) -> CurrentUser:
    if not session_token:
        raise HTTPException(status_code=401, detail={"error": {"code": "AUTHENTICATION_REQUIRED", "message": "Authentication is required."}})
    now = datetime.now(timezone.utc)
    row = await db.execute(select(Session, User, Membership).join(User, User.id == Session.user_id).join(Membership, (Membership.user_id == User.id) & (Membership.organization_id == Session.organization_id)).where(Session.token_hash == _token_hash(session_token), Session.revoked_at.is_(None), Session.expires_at > now, User.is_active.is_(True)))
    result = row.first()
    if not result:
        raise HTTPException(status_code=401, detail={"error": {"code": "SESSION_INVALID", "message": "The session is invalid or expired."}})
    session, user, membership = result
    return CurrentUser(user.id, session.organization_id, user.email, user.display_name, membership.role, session.id)


async def get_current_user(session_token: str | None = Cookie(default=None, alias=SESSION_COOKIE), db: AsyncSession = Depends(get_db)) -> CurrentUser:
    return await current_user(session_token, db)


async def require_csrf(request: Request, user: CurrentUser = Depends(get_current_user), csrf_cookie: str | None = Cookie(default=None, alias=CSRF_COOKIE), csrf_header: str | None = Header(default=None, alias="X-CSRF-Token"), db: AsyncSession = Depends(get_db)) -> CurrentUser:
    if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
        session = await db.get(Session, user.session_id)\n        if not session or not csrf_cookie or not csrf_header or not hmac.compare_digest(csrf_cookie, csrf_header) or not hmac.compare_digest(_token_hash(csrf_cookie), session.csrf_hash):
            raise HTTPException(status_code=403, detail={"error": {"code": "CSRF_REQUIRED", "message": "A valid CSRF token is required."}})
    return user


def require_permission(permission: str) -> Callable:
    async def dependency(user: CurrentUser = Depends(require_csrf)) -> CurrentUser:
        permissions = ROLE_PERMISSIONS.get(user.role, set())
        if "*" not in permissions and permission not in permissions:
            raise HTTPException(status_code=403, detail={"error": {"code": "PERMISSION_DENIED", "message": "You are not authorized for this operation."}})
        return user
    return dependency
