import hashlib, re, secrets
from fastapi import APIRouter, Depends, Request, Query, HTTPException
from app.api.deps import create_access_token, current_user_id
from app.db import repository
from app.db.pg_pool import get_pool
from pydantic import BaseModel
import asyncpg

router = APIRouter()


class AuthBody(BaseModel):
    email: str | None = None
    username: str | None = None
    identifier: str | None = None
    password: str


class OnboardingBody(BaseModel):
    goalMode: str | None = None
    dailyGoalMinutes: int | None = None
    studyDays: list[str] | None = None
    mascotTone: str | None = None


def _hash(password: str) -> str:
    salt = secrets.token_hex(16)
    h = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 100000).hex()
    return f"{salt}${h}"


def _verify(password: str, hashed: str) -> bool:
    if not hashed or "$" not in hashed:
        return False
    salt, h = hashed.split("$", 1)
    return secrets.compare_digest(
        hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 100000).hex(), h
    )


def _uid(email: str) -> str:
    return "user-" + "".join(c if c.isalnum() else "-" for c in email.lower())

_SAFE_TOKEN_RE = re.compile(r"^[A-Za-z0-9_.-]{3,}$")
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

def _normalize_username(username: str | None) -> str:
    value = (username or "").strip().lower()
    if not _SAFE_TOKEN_RE.fullmatch(value):
        raise HTTPException(400, "Username must be at least 3 characters and use only letters, numbers, _, ., -")
    return value

def _normalize_password(password: str | None) -> str:
    value = password or ""
    if not _SAFE_TOKEN_RE.fullmatch(value):
        raise HTTPException(400, "Password must be at least 3 characters and use only letters, numbers, _, ., -")
    return value

def _normalize_email(email: str | None) -> str:
    value = (email or "").strip().lower()
    if not _EMAIL_RE.fullmatch(value):
        raise HTTPException(400, "A valid email is required")
    return value

def _uid_from_username(username: str) -> str:
    return f"user-{username}"


def _auth_payload(profile) -> dict:
    token, expires_in = create_access_token(profile.id)
    return {
        "user": profile.model_dump(exclude={"plan_dirty"}),
        "accessToken": token,
        "tokenType": "bearer",
        "expiresIn": expires_in,
    }


@router.post("/api/auth/register")
async def register(body: AuthBody, pool: asyncpg.Pool = Depends(get_pool)):
    email = _normalize_email(body.email)
    username = _normalize_username(body.username)
    password = _normalize_password(body.password)

    if await repository.get_user_by_email(pool, email):
        raise HTTPException(400, "Email already registered")
    if await repository.get_user_by_username(pool, username):
        raise HTTPException(400, "Username already registered")

    profile = await repository.create_user(pool, _uid_from_username(username), email, _hash(password), username)
    return _auth_payload(profile)


@router.post("/api/auth/login")
async def login(body: AuthBody, pool: asyncpg.Pool = Depends(get_pool)):
    identifier = (body.identifier or body.email or body.username or "").strip().lower()
    password = _normalize_password(body.password)
    if not identifier:
        raise HTTPException(400, "Username or email is required")

    profile = await repository.get_user_by_identifier(pool, identifier)
    if not profile:
        raise HTTPException(401, "Invalid username/email or password")

    uid = profile.id
    ph = await repository.get_password_hash(pool, uid)
    if not ph:
        # legacy passwordless or NULL password — accept and set password
        await pool.execute("UPDATE users SET password_hash=$2 WHERE id=$1", uid, _hash(password))
    elif not _verify(password, ph):
        raise HTTPException(401, "Invalid username/email or password")

    profile = await repository.get_profile(pool, uid)
    if not profile:
        raise HTTPException(401, "Invalid username/email or password")
    return _auth_payload(profile)


@router.post("/api/auth/mock")
async def auth_mock(
    request: Request,
    user_id: str | None = Query(None),
    pool: asyncpg.Pool = Depends(get_pool),
):
    data = await request.json()
    email = data.get("email", "")
    uid = user_id or (_uid(email) if email else "user-demo")
    is_signup = data.get("mode") == "signup"

    # Check if user exists
    existing = await repository.get_profile(pool, uid)
    if existing:
        updates = {}
        if email:
            updates["email"] = email
        updates["onboarding_step"] = 1 if is_signup else 2
        profile = await repository.update_profile(pool, uid, **updates)
    else:
        profile = await repository.create_user(
            pool, uid, email or f"{uid}@mock.dev", _hash("mock")
        )
        if not is_signup:
            profile = await repository.update_profile(pool, uid, onboarding_step=2)

    return profile.model_dump(exclude={"plan_dirty"})


@router.post("/api/onboarding")
async def onboarding(
    body: OnboardingBody,
    user_id: str | None = Query(None),
    pool: asyncpg.Pool = Depends(get_pool),
):
    del user_id
    uid = current_user_id()
    updates = {}
    if body.goalMode is not None:
        updates["goal_mode"] = body.goalMode
    if body.dailyGoalMinutes is not None:
        updates["daily_goal_minutes"] = body.dailyGoalMinutes
    if body.studyDays is not None:
        updates["study_days"] = body.studyDays
    if body.mascotTone is not None:
        updates["mascot_tone"] = body.mascotTone

    profile = await repository.get_profile(pool, uid)
    if not profile:
        raise HTTPException(404, "User not found")
    updates["onboarding_step"] = min(3, profile.onboarding_step + 1)
    profile = await repository.update_profile(pool, uid, **updates)
    return profile.model_dump(exclude={"plan_dirty"})
