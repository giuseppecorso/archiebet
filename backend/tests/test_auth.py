from datetime import timedelta

import pytest
from sqlalchemy import select

from app.auth.security import hash_password, hash_token, verify_password
from app.auth.service import create_user, open_session, user_from_token
from app.models import UserSession
from app.models.base import utcnow

PASSWORD = "una-password-lunga"


def test_password_hash_roundtrip():
    hashed = hash_password(PASSWORD)
    assert hashed.startswith("$argon2id$")
    assert verify_password(PASSWORD, hashed)
    assert not verify_password("sbagliata-sbagliata", hashed)


def test_short_password_rejected():
    with pytest.raises(ValueError):
        hash_password("corta")


def test_unknown_user_never_verifies():
    assert not verify_password(PASSWORD, None)


def test_duplicate_username_rejected(db):
    create_user(db, "Giuse", PASSWORD)
    with pytest.raises(ValueError):
        create_user(db, "giuse ", PASSWORD)


def test_session_token_stored_only_as_hash(db):
    user = create_user(db, "giuse", PASSWORD)
    token = open_session(db, user, days=30)
    stored = db.scalar(select(UserSession))
    assert stored.token_hash == hash_token(token)
    assert token not in stored.token_hash
    assert user_from_token(db, token).id == user.id


def test_expired_session_rejected(db):
    user = create_user(db, "giuse", PASSWORD)
    token = open_session(db, user, days=30)
    stored = db.scalar(select(UserSession))
    stored.expires_at = utcnow() - timedelta(seconds=1)
    db.commit()
    assert user_from_token(db, token) is None


def test_login_me_logout_flow(client, db):
    create_user(db, "giuse", PASSWORD)

    assert client.get("/api/auth/me").status_code == 401

    response = client.post("/api/auth/login", json={"username": "Giuse", "password": PASSWORD})
    assert response.status_code == 200
    assert response.json()["username"] == "giuse"
    cookie = response.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=lax" in cookie

    assert client.get("/api/auth/me").json()["username"] == "giuse"

    assert client.post("/api/auth/logout").status_code == 204
    assert client.get("/api/auth/me").status_code == 401
    assert db.scalar(select(UserSession)) is None


def test_wrong_password_rejected(client, db):
    create_user(db, "giuse", PASSWORD)
    response = client.post("/api/auth/login", json={"username": "giuse", "password": "sbagliata-sbagliata"})
    assert response.status_code == 401
    assert "set-cookie" not in response.headers


def test_health(client):
    assert client.get("/api/health").json()["status"] == "ok"
