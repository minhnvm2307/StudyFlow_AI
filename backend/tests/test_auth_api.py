import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from jose import jwt

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import app.api.routes.documents as documents_route
import app.main as main_mod
from app.api.deps import create_access_token
from app.config import settings
from app.db import pg_pool, repository
from app.schemas.profile import UserProfile
from app.services import course_api_service as course_api_service


class FakePool:
    def __init__(self):
        self.executed = []

    async def execute(self, query, *args):
        self.executed.append((query, args))


@pytest.fixture()
def client(monkeypatch):
    fake_pool = FakePool()

    async def fake_init_pool():
        return None

    async def fake_close_pool():
        return None

    def fake_get_pool():
        return fake_pool

    async def fake_noop(*args, **kwargs):
        return None

    monkeypatch.setattr(main_mod, "init_pool", fake_init_pool)
    monkeypatch.setattr(main_mod, "close_pool", fake_close_pool)
    monkeypatch.setattr(main_mod, "get_pool", fake_get_pool)
    monkeypatch.setattr(main_mod.repository, "ensure_admin_user", fake_noop)
    monkeypatch.setattr(main_mod.repository, "ensure_busy_events_table", fake_noop)
    monkeypatch.setattr(main_mod.repository, "ensure_topic_mastery_evidence_columns", fake_noop)
    monkeypatch.setattr(main_mod.repository, "ensure_mastery_events_table", fake_noop)
    monkeypatch.setattr(pg_pool, "_pool", fake_pool)

    async def override_pool():
        return fake_pool

    main_mod.app.dependency_overrides[pg_pool.get_pool] = override_pool

    with TestClient(main_mod.app) as test_client:
        yield test_client, fake_pool

    main_mod.app.dependency_overrides.clear()


def _user(user_id: str, email: str, username: str) -> UserProfile:
    return UserProfile(
        id=user_id,
        email=email,
        username=username,
        onboarding_step=0,
        goal_mode=None,
        daily_goal_minutes=30,
        study_days=[],
        study_window=None,
        quiet_hours=None,
        mascot_tone="encouraging",
        notifications={},
        xp=0,
        streak=0,
        fsrs_custom_weights=None,
        fsrs_tuning={},
        plan_dirty=False,
    )


def test_register_returns_bearer_session_payload(client, monkeypatch):
    test_client, _ = client
    created_user = _user("user-alice", "alice@example.com", "alice")

    async def fake_get_user_by_email(pool, email):
        return None

    async def fake_get_user_by_username(pool, username):
        return None

    async def fake_create_user(pool, user_id, email, password_hash, username=None):
        return created_user

    monkeypatch.setattr(repository, "get_user_by_email", fake_get_user_by_email)
    monkeypatch.setattr(repository, "get_user_by_username", fake_get_user_by_username)
    monkeypatch.setattr(repository, "create_user", fake_create_user)

    response = test_client.post(
        "/api/auth/register",
        json={"email": "alice@example.com", "username": "alice", "password": "pass_123"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["user"]["id"] == "user-alice"
    assert payload["user"]["email"] == "alice@example.com"
    assert payload["tokenType"] == "bearer"
    assert isinstance(payload["accessToken"], str) and payload["accessToken"]
    assert payload["expiresIn"] > 0


def test_private_endpoint_requires_bearer_token(client):
    test_client, _ = client

    response = test_client.get("/api/dashboard")

    assert response.status_code == 401


def test_private_endpoint_uses_token_identity_instead_of_user_id_query(client, monkeypatch):
    test_client, _ = client
    signed_in_user = _user("user-alice", "alice@example.com", "alice")

    async def fake_get_user_by_identifier(pool, identifier):
        return signed_in_user

    async def fake_get_password_hash(pool, user_id):
        return None

    async def fake_get_profile(pool, user_id):
        if user_id == "user-alice":
            return signed_in_user
        return None

    async def fake_dashboard(pool, user_id, filter_value=None, sort=None):
        return {"userId": user_id, "courses": []}

    monkeypatch.setattr(repository, "get_user_by_identifier", fake_get_user_by_identifier)
    monkeypatch.setattr(repository, "get_password_hash", fake_get_password_hash)
    monkeypatch.setattr(repository, "get_profile", fake_get_profile)
    monkeypatch.setattr(course_api_service, "get_dashboard", fake_dashboard)

    login_response = test_client.post(
        "/api/auth/login",
        json={"identifier": "alice", "password": "pass_123"},
    )
    token = login_response.json()["accessToken"]

    response = test_client.get(
        "/api/dashboard?user_id=user-bob",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    assert response.json()["userId"] == "user-alice"


def test_private_endpoint_rejects_invalid_and_expired_tokens(client, monkeypatch):
    test_client, _ = client
    signed_in_user = _user("user-alice", "alice@example.com", "alice")

    async def fake_get_profile(pool, user_id):
        if user_id == "user-alice":
            return signed_in_user
        return None

    monkeypatch.setattr(repository, "get_profile", fake_get_profile)

    invalid = test_client.get(
        "/api/dashboard",
        headers={"Authorization": "Bearer not-a-real-token"},
    )
    assert invalid.status_code == 401

    expired_token = jwt.encode(
        {"sub": "user-alice", "exp": datetime.now(timezone.utc) - timedelta(minutes=5)},
        settings.JWT_SECRET,
        algorithm=settings.JWT_ALGORITHM,
    )
    expired = test_client.get(
        "/api/dashboard",
        headers={"Authorization": f"Bearer {expired_token}"},
    )
    assert expired.status_code == 401


def test_options_preflight_bypasses_auth_for_private_api(client):
    test_client, _ = client

    response = test_client.options(
        "/api/dashboard",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "authorization,content-type",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"


def test_private_multipart_endpoint_uses_bearer_identity(client, monkeypatch, tmp_path):
    test_client, _ = client
    signed_in_user = _user("user-alice", "alice@example.com", "alice")
    token, _ = create_access_token("user-alice")
    upload_path = tmp_path / "upload.txt"
    upload_path.write_text("temporary upload text", encoding="utf-8")

    async def fake_get_profile(pool, user_id):
        if user_id == "user-alice":
            return signed_in_user
        return None

    async def fake_get_subject(pool, subject_id):
        return {"id": subject_id}

    async def fake_handle_upload(pool, user_id, subject_id, filename, text):
        return {
            "userId": user_id,
            "subjectId": subject_id,
            "filename": filename,
            "textLength": len(text),
        }

    monkeypatch.setattr(repository, "get_profile", fake_get_profile)
    monkeypatch.setattr(repository, "get_subject", fake_get_subject)
    monkeypatch.setattr(documents_route, "save_uploaded_file", lambda filename, contents: str(upload_path))
    monkeypatch.setattr(documents_route, "extract_text_from_file_path", lambda path: "parsed upload text")
    monkeypatch.setattr(documents_route, "upload_file_to_s3", lambda contents, key: f"s3://bucket/{key}")
    monkeypatch.setattr(documents_route, "handle_upload", fake_handle_upload)

    response = test_client.post(
        "/api/documents/upload?subject_id=subject-1&user_id=user-bob",
        headers={"Authorization": f"Bearer {token}"},
        files={"file": ("notes.txt", b"hello world", "text/plain")},
        data={"user_id": "user-bob"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["userId"] == "user-alice"
    assert payload["subjectId"] == "subject-1"
