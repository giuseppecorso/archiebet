from datetime import UTC, datetime
from decimal import Decimal

import pytest

from app.ai.gateway import AIGateway, BudgetExceeded, budget_status, month_start
from app.auth.service import create_user
from app.config import Settings
from app.models import UsageEvent

NOW = datetime(2026, 10, 11, 12, 0, tzinfo=UTC)


def settings(budget: float = 15, quota: float = 10) -> Settings:
    return Settings(ai_monthly_budget_eur=budget, ai_user_monthly_quota_eur=quota, ai_budget_warning_ratio=0.8)


def spend(db, euros: str, user_id=None, source="ai:haiku", when=NOW):
    db.add(UsageEvent(source=source, cost_eur=Decimal(euros), user_id=user_id, created_at=when))
    db.commit()


def test_budget_status_thresholds():
    limit, ratio = Decimal(10), Decimal("0.8")
    assert not budget_status(Decimal("7.99"), limit, ratio).warning
    assert budget_status(Decimal(8), limit, ratio).warning
    assert not budget_status(Decimal("9.99"), limit, ratio).exceeded
    assert budget_status(Decimal(10), limit, ratio).exceeded


def test_month_start():
    assert month_start(NOW) == datetime(2026, 10, 1, tzinfo=UTC)


def test_only_ai_costs_of_current_month_count(db):
    spend(db, "4.50")
    spend(db, "3.00", source="api-football")  # non è AI
    spend(db, "9.00", when=datetime(2026, 9, 30, 23, 0, tzinfo=UTC))  # mese scorso
    assert AIGateway(db, settings()).global_status(NOW).spent_eur == Decimal("4.50")


def test_global_cap_blocks_everyone(db):
    spend(db, "15.00")
    with pytest.raises(BudgetExceeded):
        AIGateway(db, settings()).ensure_can_spend(user_id=None, now=NOW)


def test_user_quota_blocks_only_that_user(db):
    giuse = create_user(db, "giuse", "una-password-lunga", is_admin=True)
    amico = create_user(db, "amico", "una-password-lunga", is_admin=True)
    spend(db, "10.00", user_id=giuse.id)
    gateway = AIGateway(db, settings(budget=100))
    with pytest.raises(BudgetExceeded):
        gateway.ensure_can_spend(giuse.id, now=NOW)
    gateway.ensure_can_spend(amico.id, now=NOW)


def test_friends_have_a_small_quota_inside_the_same_cap(db):
    giuse = create_user(db, "giuse", "una-password-lunga", is_admin=True)
    amico = create_user(db, "amico", "una-password-lunga")
    spend(db, "1.00", user_id=amico.id)
    spend(db, "1.00", user_id=giuse.id)
    gateway = AIGateway(db, Settings(ai_monthly_budget_eur=10, ai_user_monthly_quota_eur=10, ai_friend_monthly_quota_eur=1.0, ai_budget_warning_ratio=0.8))
    with pytest.raises(BudgetExceeded):
        gateway.ensure_can_spend(amico.id, now=NOW)
    gateway.ensure_can_spend(giuse.id, now=NOW)


def test_friends_never_spend_by_default(db):
    create_user(db, "giuse", "una-password-lunga", is_admin=True)
    amico = create_user(db, "amico", "una-password-lunga")
    with pytest.raises(BudgetExceeded, match="riservate"):
        AIGateway(db, Settings()).ensure_can_spend(amico.id, now=NOW)


def test_at_most_five_friends(db):
    create_user(db, "giuse", "una-password-lunga", is_admin=True)
    for k in range(5):
        create_user(db, f"amico{k}", "una-password-lunga")
    with pytest.raises(ValueError, match="5 amici"):
        create_user(db, "amico5", "una-password-lunga")
