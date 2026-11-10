from app.auth.service import DEMO_PASSWORD, DEMO_USERNAME, MAX_USERS, create_user, ensure_demo_user, set_password

PASSWORD = "una-password-lunga"


def test_demo_user_is_created_once_and_keeps_the_known_password(db):
    first = ensure_demo_user(db)
    set_password(db, DEMO_USERNAME, "cambiata-da-qualcuno")
    again = ensure_demo_user(db)
    assert again.id == first.id
    assert not again.is_admin
    assert again.premium_paid_until is not None


def test_demo_does_not_take_a_friend_slot(db):
    ensure_demo_user(db)
    for i in range(MAX_USERS):
        create_user(db, f"amico{i}", PASSWORD)


def test_demo_can_read_but_not_write(client, db):
    ensure_demo_user(db)
    assert client.post("/api/auth/login", json={"username": DEMO_USERNAME, "password": DEMO_PASSWORD}).status_code == 200
    assert client.get("/api/auth/me").status_code == 200
    blocked = client.post("/api/auth/password", json={"old": DEMO_PASSWORD, "new": "un-altra-password"})
    assert blocked.status_code == 403
    assert client.put("/api/auth/account", json={"display_name": "x"}).status_code == 403
    assert client.post("/api/auth/logout").status_code == 204  # uscire si può sempre


def test_other_users_can_still_write(logged_client):
    assert logged_client.put("/api/auth/account", json={"display_name": "Giuse"}).status_code != 403
