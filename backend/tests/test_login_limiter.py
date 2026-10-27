from datetime import UTC, datetime, timedelta

from app.auth.limiter import LoginLimiter, limiter

T0 = datetime(2026, 10, 27, 20, 0, tzinfo=UTC)


def test_five_failures_lock_for_fifteen_minutes():
    lim = LoginLimiter()
    for k in range(5):
        assert not lim.blocked("Vito", T0)
        lim.failed("vito", T0 + timedelta(seconds=k))
    assert lim.blocked("VITO ", T0 + timedelta(minutes=1))
    assert not lim.blocked("vito", T0 + timedelta(minutes=16))
    assert not lim.blocked("giuse", T0 + timedelta(minutes=1))  # gli altri non sono toccati


def test_login_endpoint_answers_429_after_too_many_errors(client, db):
    from app.auth.service import create_user

    create_user(db, "amico", "una-password-lunga")
    limiter.succeeded("amico")
    for _ in range(5):
        assert client.post("/api/auth/login", json={"username": "amico", "password": "sbagliata-123"}).status_code == 401
    r = client.post("/api/auth/login", json={"username": "amico", "password": "una-password-lunga"})
    assert r.status_code == 429  # bloccato anche con la password giusta
    limiter.succeeded("amico")
    assert client.post("/api/auth/login", json={"username": "amico", "password": "una-password-lunga"}).status_code == 200
