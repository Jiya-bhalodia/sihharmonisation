from datetime import datetime
import hashlib
import re

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session
from redis import Redis
from redis.exceptions import RedisError

from app.config import get_settings
from app.database import get_db
from app.models.orm import ApprovalRequest, AuditLog, User
from app.security import (
    ROLES, authenticate, current_user, free_demo_user, hash_password, issue_token,
    require_permission, write_audit,
)
from app.utils.ids import new_id

router = APIRouter()

_LOGIN_RATE_LIMIT_CHECK = """
local pair_count = tonumber(redis.call('GET', KEYS[1]) or '0')
local ip_count = tonumber(redis.call('GET', KEYS[2]) or '0')
if pair_count >= tonumber(ARGV[1]) or ip_count >= tonumber(ARGV[2]) then
  local pair_ttl = redis.call('TTL', KEYS[1])
  local ip_ttl = redis.call('TTL', KEYS[2])
  return {1, math.max(pair_ttl, ip_ttl, 1)}
end
return {0, 0}
"""
_LOGIN_RATE_LIMIT_FAILURE = """
local pair_count = redis.call('INCR', KEYS[1])
if pair_count == 1 then redis.call('EXPIRE', KEYS[1], ARGV[1]) end
local ip_count = redis.call('INCR', KEYS[2])
if ip_count == 1 then redis.call('EXPIRE', KEYS[2], ARGV[1]) end
return {pair_count, ip_count}
"""


def _login_rate_limit_keys(request: Request, email: str) -> tuple[str, str]:
    client_ip = request.client.host if request.client else "unknown"
    pair_hash = hashlib.sha256(f"{client_ip}\0{email.strip().lower()}".encode()).hexdigest()
    ip_hash = hashlib.sha256(client_ip.encode()).hexdigest()
    return f"bhumix:login:pair:{pair_hash}", f"bhumix:login:ip:{ip_hash}"


def _check_login_rate_limit(request: Request, email: str) -> tuple[str, str]:
    settings = get_settings()
    pair_key, ip_key = _login_rate_limit_keys(request, email)
    client = Redis.from_url(settings.REDIS_URL, socket_connect_timeout=2, socket_timeout=2)
    try:
        blocked, retry_after = client.eval(
            _LOGIN_RATE_LIMIT_CHECK,
            2,
            pair_key,
            ip_key,
            settings.LOGIN_RATE_LIMIT_ATTEMPTS,
            settings.LOGIN_RATE_LIMIT_IP_ATTEMPTS,
        )
        if blocked:
            raise HTTPException(
                status_code=429,
                detail="Too many failed login attempts. Try again later.",
                headers={"Retry-After": str(max(int(retry_after), 1))},
            )
    except RedisError as error:
        raise HTTPException(503, "Login protection is temporarily unavailable") from error
    finally:
        client.close()
    return pair_key, ip_key


def _record_failed_login(pair_key: str, ip_key: str) -> None:
    settings = get_settings()
    client = Redis.from_url(settings.REDIS_URL, socket_connect_timeout=2, socket_timeout=2)
    try:
        client.eval(
            _LOGIN_RATE_LIMIT_FAILURE,
            2,
            pair_key,
            ip_key,
            settings.LOGIN_RATE_LIMIT_WINDOW_SECONDS,
        )
    except RedisError as error:
        raise HTTPException(503, "Login protection is temporarily unavailable") from error
    finally:
        client.close()


def ensure_production_auth():
    if get_settings().is_local_demo_mode or not get_settings().AUTH_ENABLED:
        raise HTTPException(404, "User administration is unavailable in demo mode")


class LoginRequest(BaseModel):
    email: str
    password: str

    @field_validator("email")
    @classmethod
    def valid_email(cls, value: str) -> str:
        value = value.strip().lower()
        if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", value):
            raise ValueError("Enter a valid email address")
        return value

    @field_validator("password")
    @classmethod
    def valid_demo_password(cls, value: str) -> str:
        # The hosted FREE_DEMO_MODE uses ephemeral evaluator access only.
        if get_settings().FREE_DEMO_MODE and len(value) < 8:
            raise ValueError("Password must be at least 8 characters")
        return value


class UserCreate(BaseModel):
    email: str
    full_name: str = Field(min_length=1, max_length=160)
    role: str
    password: str = Field(min_length=12, max_length=256)

    @field_validator("email")
    @classmethod
    def valid_email(cls, value: str) -> str:
        value = value.strip().lower()
        if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", value):
            raise ValueError("Enter a valid email address")
        return value


class UserStatusUpdate(BaseModel):
    is_active: bool


class ApprovalRequestCreate(BaseModel):
    email: str
    full_name: str = Field(min_length=1, max_length=160)
    requested_role: str

    @field_validator("email")
    @classmethod
    def valid_email(cls, value: str) -> str:
        value = value.strip().lower()
        if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", value):
            raise ValueError("Enter a valid email address")
        return value


class ApprovalDecision(BaseModel):
    status: str


@router.post("/login")
def login(req: LoginRequest, request: Request, db: Session = Depends(get_db)):
    settings = get_settings()
    if settings.is_local_demo_mode or not settings.AUTH_ENABLED:
        raise HTTPException(400, "Token login is enabled only in authenticated deployments")
    if settings.FREE_DEMO_MODE:
        # Intentionally demo-only: arbitrary valid credentials map to a fixed,
        # read-only evaluator identity; submitted passwords are never stored.
        user = free_demo_user()
    else:
        pair_key, ip_key = _check_login_rate_limit(request, req.email)
        try:
            user = authenticate(db, req.email, req.password)
        except HTTPException as error:
            if error.status_code == 401:
                _record_failed_login(pair_key, ip_key)
            raise
    return {"access_token": issue_token(user), "token_type": "bearer",
            "expires_in": get_settings().AUTH_TOKEN_TTL_MINUTES * 60,
            "user": {"id": user.id, "email": user.email, "full_name": user.full_name, "role": user.role}}


@router.get("/me")
def me(user: User | None = Depends(current_user)):
    if user is None:
        return {"authenticated": False, "mode": "demo"}
    return {"authenticated": True, "id": user.id, "email": user.email,
            "full_name": user.full_name, "role": user.role}


def _require_approval_manager(user: User | None) -> None:
    settings = get_settings()
    if settings.FREE_DEMO_MODE:
        if user is None or user.role != "evaluator":
            raise HTTPException(403, "Approval review is available to the hosted demo evaluator")
        return
    ensure_production_auth()
    require_permission(user, "users:manage")


@router.get("/approval-requests")
def list_approval_requests(db: Session = Depends(get_db), actor: User | None = Depends(current_user)):
    _require_approval_manager(actor)
    return db.query(ApprovalRequest).order_by(ApprovalRequest.created_at.desc()).limit(100).all()


@router.post("/approval-requests", status_code=201)
def create_approval_request(req: ApprovalRequestCreate, db: Session = Depends(get_db),
                            actor: User | None = Depends(current_user)):
    _require_approval_manager(actor)
    if req.requested_role not in (ROLES - {"administrator"}):
        raise HTTPException(400, "Select a supported staff role")
    request_row = ApprovalRequest(
        id=new_id("AR"), email=req.email, full_name=req.full_name.strip(),
        requested_role=req.requested_role, status="pending", created_at=datetime.utcnow(),
    )
    db.add(request_row)
    db.commit()
    db.refresh(request_row)
    return request_row


@router.patch("/approval-requests/{request_id}")
def decide_approval_request(request_id: str, req: ApprovalDecision, db: Session = Depends(get_db),
                            actor: User | None = Depends(current_user)):
    _require_approval_manager(actor)
    if req.status not in {"approved", "rejected"}:
        raise HTTPException(400, "Decision must be approved or rejected")
    request_row = db.query(ApprovalRequest).filter(ApprovalRequest.id == request_id).first()
    if request_row is None:
        raise HTTPException(404, "Approval request not found")
    if request_row.status != "pending":
        raise HTTPException(409, "This request has already been decided")
    request_row.status = req.status
    request_row.decided_at = datetime.utcnow()
    request_row.decided_by = actor.email if actor else None
    db.commit()
    db.refresh(request_row)
    return request_row


@router.post("/users", status_code=201)
def create_user(req: UserCreate, request: Request, db: Session = Depends(get_db),
                actor: User | None = Depends(current_user)):
    ensure_production_auth()
    require_permission(actor, "users:manage")
    if req.role not in ROLES:
        raise HTTPException(400, f"role must be one of {sorted(ROLES)}")
    email = req.email
    if db.query(User).filter(User.email == email).first():
        raise HTTPException(409, "A user with this email already exists")
    try:
        password_hash = hash_password(req.password)
    except ValueError as error:
        raise HTTPException(400, str(error))
    user = User(id=new_id("US"), email=email, full_name=req.full_name.strip(),
                role=req.role, password_hash=password_hash, is_active=True, created_at=datetime.utcnow())
    db.add(user)
    db.flush()
    write_audit(db, actor, "user.created", "user", user.id, request,
                after={"email": email, "role": user.role, "is_active": True})
    db.commit()
    return {"id": user.id, "email": email, "full_name": user.full_name, "role": user.role}


@router.get("/audit")
def list_audit_logs(limit: int = 100, db: Session = Depends(get_db),
                    actor: User | None = Depends(current_user)):
    ensure_production_auth()
    require_permission(actor, "audit:read")
    if actor is None:
        return []
    return db.query(AuditLog).order_by(AuditLog.created_at.desc()).limit(min(max(limit, 1), 500)).all()


@router.get("/users")
def list_users(db: Session = Depends(get_db), actor: User | None = Depends(current_user)):
    ensure_production_auth()
    require_permission(actor, "users:manage")
    if actor is None:
        return []
    return [{"id": user.id, "email": user.email, "full_name": user.full_name,
             "role": user.role, "is_active": user.is_active, "created_at": user.created_at}
            for user in db.query(User).order_by(User.created_at.asc()).all()]


@router.patch("/users/{user_id}/status")
def update_user_status(user_id: str, req: UserStatusUpdate, request: Request,
                       db: Session = Depends(get_db), actor: User | None = Depends(current_user)):
    ensure_production_auth()
    require_permission(actor, "users:manage")
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(404, "User not found")
    if actor and actor.id == user.id and not req.is_active:
        raise HTTPException(400, "You cannot deactivate your own account")
    before = {"is_active": user.is_active}
    user.is_active = req.is_active
    write_audit(db, actor, "user.status_changed", "user", user.id, request,
                before=before, after={"is_active": user.is_active})
    db.commit()
    return {"id": user.id, "email": user.email, "is_active": user.is_active}
