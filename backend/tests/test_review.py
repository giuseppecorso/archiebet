"""Pagella settimanale di Archie e correzioni automatiche (D132)."""

import random
from datetime import UTC, date, datetime, timedelta

import pytest

from app.forecast import review as rv
from app.forecast.picks import MarketPick, Offer
from app.forecast.review_service import apply_learning, winners_of

MONDAY = datetime(2026, 4, 6, 18, 0, tzinfo=UTC)  # lunedì 6 aprile, 20:00 in Italia


def test_snapshot_at_ten_or_one_hour_before():
    assert rv.snapshot_time(MONDAY) == datetime(2026, 4, 6, 8, 0, tzinfo=UTC)  # 10:00 italiane (ora legale)
    early = datetime(2026, 4, 6, 8, 30, tzinfo=UTC)  # 10:30 italiane: un'ora prima
    assert rv.snapshot_time(early) == datetime(2026, 4, 6, 7, 30, tzinfo=UTC)
    assert rv.week_of(date(2026, 4, 12)) == date(2026, 4, 6)


def _rows(weeks: int, per_week: int, truth, seed: int = 1, market: str = "COR9.5", source: str = "pinnacle", priced=("over", "under")):
    """Mercati Over/Under con probabilità dichiarata p e vera truth(p)."""
    rnd = random.Random(seed)
    rows, mid = [], 0
    for w in range(weeks):
        for _ in range(per_week):
            mid += 1
            p = rnd.uniform(0.2, 0.8)
            hit = rnd.random() < truth(p)
            rows.append(rv.Row(mid, MONDAY + timedelta(weeks=w), "ITA-A", market, source, {"over": p, "under": 1 - p},
                               frozenset({"over" if hit else "under"}), {"over": p, "under": 1 - p},
                               {"sisal": {s: 0.97 / q for s, q in (("over", p), ("under", 1 - p)) if s in priced}}))  # fmt: skip
    return rows


def test_fit_recovers_overconfidence():
    # Archie esagera: la verità è più vicina al 50% (b = 0,5 in scala logit)
    rows = _rows(1, 20000, lambda p: 1 / (1 + ((1 - p) / p) ** 0.5))
    a, b = rv.fit_recalibration(rows)
    assert a == pytest.approx(0, abs=0.05) and b == pytest.approx(0.5, abs=0.05)
    assert rv.recalibrate({"over": 0.8, "under": 0.2}, 0, 0.5)["over"] == pytest.approx(2 / 3)


def test_correction_passes_only_when_it_helps_out_of_sample():
    biased = _rows(10, 200, lambda p: 1 / (1 + ((1 - p) / p) ** 0.5))
    test = rv.correction_test(rv.GroupData(biased, "angoli · pinnacle"), date(2026, 7, 1))
    assert test.passed and test.eval_weeks >= rv.MIN_EVAL_WEEKS and test.params[1] < 0.8
    honest = _rows(10, 200, lambda p: p, seed=2)
    assert not rv.correction_test(rv.GroupData(honest, "angoli · pinnacle"), date(2026, 7, 1)).passed


def test_correction_uses_only_past_weeks():
    biased = _rows(10, 200, lambda p: 1 / (1 + ((1 - p) / p) ** 0.5))
    data = rv.GroupData(biased, "angoli · pinnacle")
    assert rv.correction_test(data, date(2026, 4, 20)).eval_weeks == 0  # 400 mercati: ancora nessuna settimana di prova
    early = rv.correction_test(data, date(2026, 5, 4)).eval_weeks
    assert 0 < early < rv.correction_test(data, date(2026, 7, 1)).eval_weeks


def test_bench_when_legs_win_less_than_promised():
    rows = _rows(6, 100, lambda p: p - 0.15, priced=("over",))  # Archie sopravvaluta gli Over, giocabili solo quelli
    bench = rv.bench_test(rows, "angoli · pinnacle", date(2026, 6, 1), ("sisal",))
    assert bench.benched and bench.estimate.mean < -0.1
    fine = rv.bench_test(_rows(6, 100, lambda p: p, seed=3), "angoli · pinnacle", date(2026, 6, 1), ("sisal",))
    assert not fine.benched


def test_state_corrects_first_then_benches():
    biased = _rows(10, 200, lambda p: 1 / (1 + ((1 - p) / p) ** 0.5))
    state, tests, benches = rv.state_before(biased, date(2026, 7, 1), ("sisal",))
    assert "angoli · pinnacle" in state.corrections and not state.bench
    assert benches == []  # gruppo già corretto: niente prova di panchina


def test_apply_state_double_chance_follows_corrected_1x2():
    one = rv.Row(1, MONDAY, "ITA-A", "1X2", "pinnacle", {"1": 0.6, "X": 0.25, "2": 0.15}, frozenset({"1"}))
    dc = rv.Row(1, MONDAY, "ITA-A", "DC", "pinnacle", {"1X": 0.85, "X2": 0.4, "12": 0.75}, frozenset({"1X", "12"}))
    out = rv.apply_state([one, dc], rv.State({"esito · pinnacle": (0.0, 0.5)}, frozenset()))
    fixed = out[0].probabilities
    assert sum(fixed.values()) == pytest.approx(1) and fixed["1"] < 0.6
    assert out[1].probabilities["1X"] == pytest.approx(fixed["1"] + fixed["X"])


def test_weekly_report_counts_multiples_and_families():
    rows = _rows(2, 30, lambda p: p, seed=4)

    def build(day_rows, bm, profile, bench):
        legs = sorted(rv.legs_of(day_rows, bm, bench), key=lambda leg: -leg.probability)[:2]
        return rv.Multiple(tuple(legs), with_value=False) if len(legs) == 2 else None

    report = rv.weekly_report(rows, ("sisal",), build=build, profiles=("equilibrata",))
    assert [w["week"] for w in report["weeks"]] == ["2026-04-06", "2026-04-13"]
    week = report["weeks"][0]
    assert week["matches"] == 30 and week["families"][0]["family"] == "angoli"
    played = week["multiples"]["base"]["equilibrata"]
    assert played["played"] == 1 and 0 < played["expected"] < 1
    assert report["totals"]["base"]["equilibrata"]["played"] == 2
    assert report["weeks"][0]["multiples"]["impara"] == report["weeks"][0]["multiples"]["base"]  # nessuna correzione


def test_settle_multiple_unknown_when_stats_missing():
    a = rv.Row(1, MONDAY, "ITA-A", "COR9.5", "pinnacle", {"over": 0.6, "under": 0.4}, None)
    b = rv.Row(2, MONDAY, "ITA-A", "OU2.5", "pinnacle", {"over": 0.5, "under": 0.5}, frozenset({"under"}), {"over": 0.52, "under": 0.48})
    legs = (rv.Leg(1, MONDAY, "COR9.5", "over", 0.6, 1.7), rv.Leg(2, MONDAY, "OU2.5", "over", 0.5, 2.0))
    played = rv.settle(rv.Multiple(legs, with_value=False), {(1, "COR9.5"): a, (2, "OU2.5"): b})
    assert played.won is False  # una gamba persa basta
    assert played.clv == pytest.approx(2.0 * 0.52 - 1)
    only_unknown = rv.settle(rv.Multiple(legs[:1], with_value=False), {(1, "COR9.5"): a})
    assert only_unknown.won is None


def test_apply_learning_recomputes_values():
    mp = MarketPick("OU2.5", "pinnacle", {"over": 0.7, "under": 0.3}, {"over": [Offer("sisal", 1.5, 0.05, "valore")]})
    out = apply_learning([mp], rv.State({"gol · pinnacle": (0.0, 0.5)}, frozenset()))[0]
    assert out.corrected and out.probabilities["over"] < 0.7
    assert out.offers["over"][0].value == pytest.approx(out.probabilities["over"] * 1.5 - 1)
    assert apply_learning([mp], rv.State({}, frozenset()))[0] is mp


class _Match:
    home_goals, away_goals = 2, 1
    home_corners, away_corners = None, None
    home_yellow = away_yellow = home_red = away_red = None


def test_winners_of():
    assert winners_of("DC", ["1X", "X2", "12"], _Match()) == frozenset({"1X", "12"})
    assert winners_of("OU2.5", ["over", "under"], _Match()) == frozenset({"over"})
    assert winners_of("COR9.5", ["over", "under"], _Match()) is None
