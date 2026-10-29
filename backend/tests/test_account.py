def test_account_update_and_password_change(logged_client):
    acc = logged_client.get("/api/auth/account").json()
    assert acc["display_name"] is None
    out = logged_client.put("/api/auth/account", json={"display_name": " Giuse ", "email": "Giuse@Example.com"}).json()
    assert out["display_name"] == "Giuse" and out["email"] == "giuse@example.com"
    assert logged_client.put("/api/auth/account", json={"email": "non-una-mail"}).status_code == 422
    assert logged_client.post("/api/auth/password", json={"old": "sbagliata", "new": "una-nuova-lunga"}).status_code == 422
    assert logged_client.post("/api/auth/password", json={"old": "x", "new": "corta"}).status_code == 422
