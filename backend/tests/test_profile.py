from datetime import UTC, datetime, timedelta
from decimal import Decimal as D
from types import SimpleNamespace as N

from app.betting.profile import badges, by_month, family, specialty, team_record

T = datetime(2026, 10, 10, 12, tzinfo=UTC)


def sel(market, status, home=1, away=2):
    return N(market=market, status=status, match=N(home_team_id=home, away_team_id=away))


def bet(i, status, odds="2", sels=(), day=0):
    return N(id=i, placed_at=T + timedelta(days=day), status=status, total_odds=D(odds), stake=D("5"), payout=None, system=None, selections=list(sels))


def test_family_and_specialty():
    assert family("OU2.5") == "Under / Over" and family("1T_OU0.5") == "Primo e secondo tempo" and family("TGH0.5") == "Gol delle squadre"
    bets = [bet(i, "won", sels=[sel("OU2.5", "won" if i < 4 else "lost")]) for i in range(5)]
    bets += [bet(10 + i, "lost", sels=[sel("1X2", "lost")]) for i in range(5)]
    assert specialty(bets).name == "Under / Over" and specialty(bets).won == 4
    assert specialty(bets[:3]) is None  # troppo pochi


def test_badges_streak_and_big_win():
    bets = [bet(i, "won", day=i) for i in range(5)] + [bet(9, "won", odds="12", day=9)]
    got = {b.key for b in badges(bets) if b.got}
    assert {"prima", "serie", "colpo", "cento"} <= got and "mille" not in got


def test_months_and_team():
    bets = [bet(1, "won", day=0), bet(2, "lost", day=30, sels=[sel("1X2", "lost", home=7)])]
    assert [(m.month, m.bets, m.won, m.coins) for m in by_month(bets)] == [("2026-10", 1, 1, 20), ("2026-11", 1, 0, 0)]
    assert team_record(bets, 7).picks == 1 and team_record(bets, 7).lost == 1
