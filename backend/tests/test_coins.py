from datetime import UTC, datetime, timedelta
from decimal import Decimal as D
from types import SimpleNamespace

from app.betting.coins import coins_for, earned, extend, premium_until

T = datetime(2026, 10, 28, 9, 0, tzinfo=UTC)


def bet(i, status="won", odds="2.50", stake="10", payout=None, system=None, minutes=0):
    return SimpleNamespace(id=i, placed_at=T + timedelta(minutes=minutes), status=status, total_odds=D(odds), stake=D(stake), payout=payout, system=system)


def test_coins_do_not_depend_on_the_stake():
    assert coins_for("won", D("2.50"), D("10"), None, None) == 25
    assert coins_for("won", D("2.50"), D("500"), None, None) == 25  # puntare di più non dà più monete
    assert coins_for("lost", D("2.50"), D("10"), None, None) == 0
    assert coins_for("won", D("8.67"), D("9"), D("18"), 2) == 20  # sistema: 10 × 18/9


def test_only_ten_bets_a_day_count():
    rows = earned([bet(i, minutes=i) for i in range(12)])
    assert sum(r.coins for r in rows) == 250 and [r.counted for r in rows][-2:] == [False, False]
    assert sum(r.coins for r in earned([bet(1), bet(2, minutes=24 * 60)])) == 50  # giorno nuovo, conta di nuovo


def test_trial_and_extension():
    created = T
    assert premium_until(created, None) == T + timedelta(days=15)
    assert premium_until(created, T + timedelta(days=40)) == T + timedelta(days=40)
    assert extend(T + timedelta(days=15), T) == T + timedelta(days=45)  # ancora in prova: si allunga dalla fine
    assert extend(T, T + timedelta(days=100)) == T + timedelta(days=130)  # scaduto: un mese da oggi
