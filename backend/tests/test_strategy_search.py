"""Archie cerca le strategie (D118)."""

import math
import random
from datetime import UTC, date, datetime, timedelta

import pytest

from app.forecast import strategy_search as ss
from app.forecast.history_sim import SimMatch, clustered_mean


def _sim(mid: int, season: str, price_home: float, p_open: float, p_close: float, home_goals: int, league: str = "ITA-A") -> SimMatch:
    rest = (1 - p_open) / 2, (1 - p_close) / 2
    return SimMatch(mid, season, league, date(2020, 1, 1), datetime(2020, 1, 1, tzinfo=UTC), home_goals, 0,
                    {"1X2": {"1": p_open, "X": rest[0], "2": rest[0]}}, {"1X2": {"1": p_close, "X": rest[1], "2": rest[1]}},
                    {"1X2": {"1": price_home, "X": 3.4, "2": 3.4}})  # fmt: skip


def test_season_moments():
    start = datetime(2020, 8, 1, tzinfo=UTC)
    # 4 squadre, doppio girone: 12 partite, 6 per squadra (prime 5 = tutte tranne l'ultima, ultime 6 = tutte)
    pairs = [(1, 2), (3, 4), (1, 3), (2, 4), (1, 4), (2, 3)] * 2
    fixtures = [ss.Fixture(i, "X", "2020/21", start + timedelta(days=i), h, a) for i, (h, a) in enumerate(pairs)]
    moments = ss.season_moments(fixtures)
    assert moments[0] == ss.EARLY and moments[9] == ss.EARLY
    assert moments[10] == ss.LATE  # sesta partita per le squadre 1 e 4


def test_season_moments_middle():
    start = datetime(2020, 8, 1, tzinfo=UTC)
    fixtures = [ss.Fixture(i, "X", "s", start + timedelta(days=i), 1, 2) for i in range(20)]
    moments = ss.season_moments(fixtures)
    assert [moments[i] for i in (0, 4, 5, 13, 14, 19)] == [ss.EARLY, ss.EARLY, None, None, ss.LATE, ss.LATE]


def test_bets_clv_and_value():
    [b1, bx, b2] = ss.bets([_sim(1, "2015/16", 2.2, 0.48, 0.5, 1)], {1: ss.EARLY})
    assert (b1.selection, b1.won, b1.moment) == ("1", True, ss.EARLY)
    assert b1.clv == pytest.approx(2.2 * 0.5 - 1) and b1.value == pytest.approx(2.2 * 0.48 - 1)
    assert b1.has_value  # 5,6% di valore contro una soglia di 2% × √1,2 ≈ 2,2%
    assert not bx.won and bx.profit == -1.0


def test_acc_matches_direct_mean_and_se():
    rng = random.Random(3)
    sims = [_sim(i, "2015/16", rng.uniform(1.7, 2.1), 0.5, rng.uniform(0.45, 0.55), rng.randint(0, 2)) for i in range(300)]
    items = [b for b in ss.bets(sims, {}) if b.selection == "1"]
    strategy = ss.Strategy("ITA-A", "1X2", "1", (1.6, 2.2), ss.WHOLE, ss.ALWAYS)
    acc = ss.evaluate(strategy, ss.cells(items))
    direct = clustered_mean([b.clv for b in items], [b.match_id for b in items])
    est = acc.clv_estimate()
    assert acc.n == 300 and est.mean == pytest.approx(direct.mean)
    # stesso errore standard, a meno della correzione per piccoli campioni (n/(n-1) contro g/(g-1))
    assert est.std_error == pytest.approx(direct.std_error, rel=1e-6)


def test_filters_combine_cells():
    sims = [_sim(1, "s", 2.0, 0.55, 0.52, 1), _sim(2, "s", 2.0, 0.49, 0.5, 0, league="ITA-B")]
    table = ss.cells(ss.bets(sims, {1: ss.LATE}))
    base = dict(market="1X2", selection="1", band=(1.6, 2.2))
    assert ss.evaluate(ss.Strategy(ss.ALL_LEAGUES, moment=ss.WHOLE, filter=ss.ALWAYS, **base), table).n == 2
    assert ss.evaluate(ss.Strategy(ss.ALL_LEAGUES, moment=ss.WHOLE, filter=ss.WITH_VALUE, **base), table).n == 1
    assert ss.evaluate(ss.Strategy("ITA-B", moment=ss.WHOLE, filter=ss.ALWAYS, **base), table).n == 1
    assert ss.evaluate(ss.Strategy(ss.ALL_LEAGUES, moment=ss.LATE, filter=ss.ALWAYS, **base), table).n == 1
    assert ss.evaluate(ss.Strategy(ss.ALL_LEAGUES, moment=ss.EARLY, filter=ss.ALWAYS, **base), table).n == 0


def test_search_thresholds():
    # Strategia con CLV vero +5%: candidata in taratura e confermata
    good = [_sim(i, "2015/16", 2.0, 0.5, 0.515 if i % 3 else 0.545, i % 2) for i in range(400)]
    later = [_sim(1000 + i, "2022/23", 2.0, 0.5, 0.525 + (0.01 if i % 2 else -0.01), i % 2) for i in range(300)]
    s = ss.Strategy("ITA-A", "1X2", "1", (1.6, 2.2), ss.WHOLE, ss.ALWAYS)
    [r] = ss.search([s], ss.bets(good, {}), ss.bets(later, {}))
    assert r.candidate and r.passed and r.tuning_n == 400
    # Poche giocate: mai candidata
    [r] = ss.search([s], ss.bets(good[:100], {}), ss.bets(later, {}))
    assert not r.candidate and not r.passed


def test_all_strategies_count():
    assert len(ss.all_strategies(["A", "B"])) == 3 * 5 * 5 * 3 * 2
    assert all(not math.isnan(s.band[0]) for s in ss.all_strategies(["A"]))


def test_matching_live():
    s = ss.Strategy("ITA-A", "1X2", "2", (4.0, 1000.0), ss.WHOLE, ss.WITH_VALUE)
    assert ss.matching([s], "ITA-A", "1X2", "2", 4.5, 0.08, None) == s
    assert ss.matching([s], "ITA-A", "1X2", "2", 4.5, 0.01, None) is None  # poco valore
    assert ss.matching([s], "ITA-B", "1X2", "2", 4.5, 0.08, None) is None
    late = ss.Strategy(ss.ALL_LEAGUES, "OU2.5", "under", (1.6, 2.2), ss.LATE, ss.ALWAYS)
    assert ss.matching([late], "GER-2", "OU2.5", "under", 1.9, -0.05, ss.LATE) == late
    assert ss.matching([late], "GER-2", "OU2.5", "under", 1.9, -0.05, ss.EARLY) is None
