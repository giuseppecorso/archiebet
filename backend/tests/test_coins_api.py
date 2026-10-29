from datetime import UTC, datetime, timedelta
from decimal import Decimal as D

from sqlalchemy import select

from app.config import get_settings
from app.models import Bet, User


def test_coins_balance_and_redeem(logged_client, db):
    user = db.scalar(select(User))
    now = datetime.now(UTC)
    for i in range(5):  # 5 vinte a quota 20: 1.000 monete
        db.add(Bet(user_id=user.id, kind="simulated", stake=D("1"), total_odds=D("20"), status="won", payout=D("20"), placed_at=now - timedelta(minutes=i)))
    db.commit()
    body = logged_client.get("/api/coins").json()
    assert body["balance"] == 1000 and body["premium_active"] and not body["subscriptions_enabled"]
    trial_end = datetime.fromisoformat(body["premium_until"])
    after = logged_client.post("/api/coins/redeem").json()
    assert after["balance"] == 0 and after["spent"] == 1000
    assert datetime.fromisoformat(after["premium_until"]) - trial_end == timedelta(days=30)
    assert logged_client.post("/api/coins/redeem").status_code == 422  # monete finite


def test_premium_gate_only_when_subscriptions_are_on(logged_client, db, monkeypatch):
    user = db.scalar(select(User))
    user.is_admin, user.created_at = False, datetime.now(UTC) - timedelta(days=40)
    db.commit()
    assert logged_client.get("/api/study/multiple?horizon=week").status_code == 200  # abbonamenti spenti: tutto gratis
    monkeypatch.setattr(get_settings(), "subscriptions_enabled", True)
    assert logged_client.get("/api/study/multiple?horizon=week").status_code == 402  # prova finita
    assert logged_client.get("/api/coins").status_code == 200  # monete e saldo restano visibili


def test_profile_and_leaderboard(logged_client):
    body = logged_client.get("/api/profile").json()
    assert body["bets"] == 0 and len(body["badges"]) == 6 and body["specialty"] is None
    board = logged_client.get("/api/profile/leaderboard").json()
    assert board[0]["me"] and board[0]["coins"] == 0
