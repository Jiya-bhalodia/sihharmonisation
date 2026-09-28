"""Small, dependency-free bearer authentication and role policy for the API."""
import base64
import hashlib
import hmac
import json
import secrets
import time
from datetime import datetime
from types import SimpleNamespace

from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.models.orm import AuditLog, User
from app.utils.ids import new_id

ROLES = {"survey_officer", "revenue_officer", "municipal_officer", "reviewer", "evaluator", "administrator"}
ROLE_PERMISSIONS = {
    "survey_officer": {"upload:cadastral", "upload:gnss", "upload:ground_truth", "upload:orthoimagery", "upload:dsm", "upload:dtm", "view:records"},
    "revenue_officer": {"upload:revenue", "view:owner_data", "export"},
    "municipal_officer": {"upload:municipal", "upload:utility", "upload:drone", "upload:land_use", "view:records"},
    "reviewer": {"review", "view:records", "view:owner_data", "export"},
    # Public evaluation access is owner-redacted, with only bounded hosted harmonization added.
    "evaluator": {"view:records", "harmonize:free_demo"},
    "administrator": {"*"},
}
FREE_DEMO_USER_ID = "US_FREE_DEMO_EVALUATOR"
FREE_DEMO_USER_EMAIL = "demo@bhumi-x.local"
FREE_DEMO_USER_NAME = "BHUMI-X Demo Evaluator"
bearer = HTTPBearer(auto_error=False)


def free_demo_user():
    """Return the fixed, non-persisted evaluator identity for FREE_DEMO_MODE."""
    return SimpleNamespace(
        id=FREE_DEMO_USER_ID,
        email=FREE_DEMO_USER_EMAIL,
        full_name=FREE_DEMO_USER_NAME,
        role="evaluator",
        is_active=True,
    )


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def hash_password(password: str) -> str:
    if len(password) < 12:
        raise ValueError("Passwords must contain at least 12 characters")
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 310_000)
    return f"pbkdf2_sha256$310000${_b64(salt)}${_b64(digest)}"


def verify_password(password: str, stored: str) -> bool:
    try:
        _scheme, rounds, salt, expected = stored.split("$")
        actual = _b64(hashlib.pbkdf2_hmac("sha256", password.encode(), base64.urlsafe_b64decode(salt + "=="), int(rounds)))
        return hmac.compare_digest(actual, expected)
    except (ValueError, TypeError):
        return False


def issue_token(user: User) -> str:
    settings = get_settings()
    now = int(time.time())
    header = _b64(b'{"alg":"HS256","typ":"JWT"}')
    payload = _b64(json.dumps({"sub": user.id, "role": user.role, "iat": now,
                              "exp": now + settings.AUTH_TOKEN_TTL_MINUTES * 60}, separators=(",", ":")).encode())
    body = f"{header}.{payload}"
    signature = _b64(hmac.new(settings.AUTH_SECRET_KEY.encode(), body.encode(), hashlib.sha256).digest())
    return f"{body}.{signature}"


def _token_claims(token: str) -> dict:
    settings = get_settings()
    if len(settings.AUTH_SECRET_KEY) < 32:
        raise HTTPException(503, "Authentication secret is not configured")
    try:
        header, payload, signature = token.split(".")
        body = f"{header}.{payload}"
        expected = _b64(hmac.new(settings.AUTH_SECRET_KEY.encode(), body.encode(), hashlib.sha256).digest())
        if not hmac.compare_digest(signature, expected):
            raise ValueError()
        claims = json.loads(base64.urlsafe_b64decode(payload + "=="))
        if int(claims["exp"]) <= int(time.time()):
            raise ValueError()
        return claims
    except Exception:
        raise HTTPException(401, "Invalid or expired access token")


def current_user(request: Request, credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
                 db: Session = Depends(get_db)) -> User | None:
    settings = get_settings()
    if settings.is_local_demo_mode or not settings.AUTH_ENABLED:
        return None
    if credentials is None:
        raise HTTPException(401, "Authentication required", headers={"WWW-Authenticate": "Bearer"})
    claims = _token_claims(credentials.credentials)
    if settings.FREE_DEMO_MODE and claims.get("sub") == FREE_DEMO_USER_ID:
        return free_demo_user()
    user = db.query(User).filter(User.id == claims.get("sub"), User.is_active.is_(True)).first()
    if not user:
        raise HTTPException(401, "User is inactive or no longer exists")
    return user


def require_permission(user: User | None, permission: str) -> None:
    if user is None:
        return
    allowed = ROLE_PERMISSIONS.get(user.role, set())
    if "*" not in allowed and permission not in allowed:
        raise HTTPException(403, "Your role does not have permission for this action")


def write_audit(db: Session, user: User | None, action: str, resource_type: str,
                resource_id: str | None, request: Request, before=None, after=None) -> None:
    if user is None:
        return
    db.add(AuditLog(id=new_id("AU"), actor_user_id=user.id, actor_email=user.email,
                    action=action, resource_type=resource_type, resource_id=resource_id,
                    before_state=before, after_state=after,
                    ip_address=request.client.host if request.client else None,
                    created_at=datetime.utcnow()))


def authenticate(db: Session, email: str, password: str) -> User:
    user = db.query(User).filter(User.email == email.lower().strip()).first()
    if not user or not user.is_active or not verify_password(password, user.password_hash):
        raise HTTPException(401, "Invalid email or password")
    return user
