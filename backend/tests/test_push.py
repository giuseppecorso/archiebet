from types import SimpleNamespace

import pytest
from pywebpush import WebPushException
from sqlalchemy import select

from app.auth.service import create_user
from app.forecast.daily import announcement
from app.models import PushSubscription
from app.notify import push

ENDPOINT = "https://push.example.com/abc"
SUB = {"endpoint": ENDPOINT, "keys": {"p256dh": "BPk", "auth": "xyz"}}


@pytest.fixture(autouse=True)
def keys_in_tmp(tmp_path, monkeypatch):
    monkeypatch.setattr(push, "_key_path", lambda: tmp_path / "vapid.pem")


def test_announcement_texts():
    assert announcement([]) is None
    assert announcement(["giorno"]) == ("Nuova schedina in bacheca", "La schedina del giorno: guardala su ArchieBet.")
    title, body = announcement(["clv", "giorno", "sistema"])
    assert title == "3 nuove schedine in bacheca" and body.startswith("La schedina del giorno, La schedina del CLV e il sistemone")


def test_send_and_drop_gone_devices(db):
    user = create_user(db, "giuse", "una-password-lunga")
    db.add_all([PushSubscription(user_id=user.id, endpoint=ENDPOINT, p256dh="a", auth="b"),
                PushSubscription(user_id=user.id, endpoint="https://push.example.com/old", p256dh="a", auth="b")])  # fmt: skip
    db.commit()
    calls = []

    def fake(subscription_info, **kw):
        calls.append((subscription_info["endpoint"], kw["data"]))
        if subscription_info["endpoint"].endswith("old"):
            raise WebPushException("gone", response=SimpleNamespace(status_code=410))

    assert push.send(db, "Titolo", "Testo", "/pronostici", sender=fake) == 1
    assert len(calls) == 2 and '"url": "/pronostici"' in calls[0][1]
    assert [s.endpoint for s in db.scalars(select(PushSubscription))] == [ENDPOINT]  # il dispositivo sparito si toglie
    assert push.send(db, "x", "y", user_ids=[999], sender=fake) == 0


def test_push_api_subscribe_status_unsubscribe(logged_client):
    assert len(logged_client.get("/api/push/key").json()["key"]) == 87
    assert logged_client.post("/api/push/subscribe", json=SUB).status_code == 204
    assert logged_client.post("/api/push/subscribe", json=SUB).status_code == 204  # due volte: resta uno
    assert logged_client.post("/api/push/status", json={"endpoint": ENDPOINT}).json() == {"active": True}
    assert logged_client.post("/api/push/unsubscribe", json={"endpoint": ENDPOINT}).status_code == 204
    assert logged_client.post("/api/push/status", json={"endpoint": ENDPOINT}).json() == {"active": False}
    assert logged_client.post("/api/push/subscribe", json=SUB | {"endpoint": "http://insicuro"}).status_code == 422
