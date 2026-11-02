"""Andamenti per i grafici (D170): schedine costruite a mano, valori calcolati a mano."""

from datetime import UTC, date, datetime
from decimal import Decimal as D

from app.betting.trends import daily_balance, monthly_results, odds_bands, trends, weekly_clv
from app.models import Bet, BetSelection


def sel(odds: str, status: str, clv: str | None = None) -> BetSelection:
    return BetSelection(market="1X2", pick="1", odds=D(odds), status=status, clv=D(clv) if clv else None)


def bet(stake: str, status: str, payout: str | None, placed: datetime, settled: datetime | None, *sels: BetSelection) -> Bet:
    return Bet(stake=D(stake), total_odds=D("2"), status=status, payout=D(payout) if payout else None,
               placed_at=placed, settled_at=settled, selections=list(sels))  # fmt: skip


MON = datetime(2026, 10, 26, 12, tzinfo=UTC)  # lunedì
TUE = datetime(2026, 10, 27, 12, tzinfo=UTC)
LATE_NIGHT = datetime(2026, 10, 31, 23, 30, tzinfo=UTC)  # in Italia è già il 1° novembre
NEXT_MON = datetime(2026, 11, 2, 12, tzinfo=UTC)

BETS = [
    bet("10", "won", "20", MON, TUE, sel("2.00", "won", "0.05")),  # +10 il 27/10
    bet("10", "lost", "0", MON, TUE, sel("1.40", "lost", "-0.01")),  # -10 il 27/10
    bet("5", "lost", "0", TUE, LATE_NIGHT, sel("1.60", "won", "0.02"), sel("3.50", "lost")),  # -5 il 1/11
    bet("4", "won", "12", NEXT_MON, NEXT_MON, sel("3.00", "won", "0.10")),  # +8 il 2/11
    bet("6", "open", None, NEXT_MON, None, sel("1.90", "open")),  # aperta: niente saldo
    bet("3", "void", "3", NEXT_MON, NEXT_MON, sel("2.10", "void")),  # rimborsata: fuori da tutto
]


def test_daily_balance_is_cumulative_and_uses_the_italian_day():
    days = daily_balance(BETS)
    assert [d.day for d in days] == [date(2026, 10, 27), date(2026, 11, 1), date(2026, 11, 2)]
    assert [d.profit for d in days] == [D(0), D(-5), D(8)]
    assert [d.cum_profit for d in days] == [D(0), D(-5), D(3)]
    assert (days[0].bets, days[0].won) == (2, 1)


def test_monthly_results_count_won_and_lost_bets():
    months = monthly_results(BETS)
    assert [(m.month, m.won, m.lost) for m in months] == [("2026-10", 1, 1), ("2026-11", 1, 1)]


def test_weekly_clv_averages_the_selections_of_each_week():
    weeks = weekly_clv(BETS)
    assert [w.week for w in weeks] == [date(2026, 10, 26), date(2026, 11, 2)]
    # settimana del 26/10: 0,05, -0,01, 0,02 → media 0,02
    assert (weeks[0].avg_clv, weeks[0].count) == (0.02, 3)
    assert (weeks[1].avg_clv, weeks[1].count) == (0.1, 1)


def test_odds_bands_compare_hits_with_what_the_odds_promise():
    bands = {b.label: b for b in odds_bands(BETS)}
    low = bands["fino a 1,50"]  # 1,40 persa
    assert (low.selections, low.won, low.hit_rate) == (1, 0, 0.0)
    assert low.expected_rate == round(1 / 1.4, 4)
    mid = bands["1,50 – 2,00"]  # 1,60 vinta (la 1,90 è aperta e non conta)
    assert (mid.selections, mid.won) == (1, 1)
    high = bands["3,00 – 5,00"]  # 3,50 persa, 3,00 vinta
    assert (high.selections, high.won, high.hit_rate) == (2, 1, 0.5)
    assert high.expected_rate == round((1 / 3.5 + 1 / 3.0) / 2, 4)
    assert bands["oltre 5,00"].hit_rate is None


def test_trends_leave_out_void_bets():
    t = trends(BETS)
    assert sum(w.count for w in t.clv_weeks) == 4
    assert all(b.label != "2,10" for b in t.odds_bands)
    assert t.days[-1].cum_profit == D(3)
