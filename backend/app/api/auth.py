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
from app.models.orm import AuditLog, User
from app.security import ROLES, authenticate, current_user, hash_password, issue_token, require_permission, write_audit
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


@router.post("/login")
def login(req: LoginRequest, request: Request, db: Session = Depends(get_db)):
    if get_settings().is_local_demo_mode or not get_settings().AUTH_ENABLED:
        raise HTTPException(400, "Token login is enabled only in authenticated deployments")
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
