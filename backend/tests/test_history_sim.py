"""Simulazione storica (D86): esiti, errori standard per partita, regole delle Occasioni, calibrazione, multiple."""

import math
from datetime import UTC, date, datetime

import pytest

from app.forecast.history_sim import (
    Rule,
    SimMatch,
    calibration,
    clustered_mean,
    daily_multiples,
    favorite_hits,
    occasions,
    summarize_multiples,
    summarize_plays,
    won,
)
from app.forecast.multiple import PROFILES


def sim(mid, hg, ag, fair1x2=(0.5, 0.3, 0.2), close1x2=None, book1x2=(2.2, 3.3, 5.0), day=date(2025, 1, 4), season="2024/25"):
    keys = ("1", "X", "2")
    return SimMatch(
        mid, season, "ITA-A", day, datetime(day.year, day.month, day.day, 15, tzinfo=UTC), hg, ag,
        fair_open={"1X2": dict(zip(keys, fair1x2)), "OU2.5": {"over": 0.5, "under": 0.5}},
        fair_close={"1X2": dict(zip(keys, close1x2 or fair1x2)), "OU2.5": {"over": 0.5, "under": 0.5}},
        book={"1X2": dict(zip(keys, book1x2)), "OU2.5": {"over": 1.9, "under": 1.9}},
    )


def test_won_for_each_market():
    m = sim(1, 2, 1)
    assert won(m, "1X2", "1") and not won(m, "1X2", "X")
    assert won(m, "OU2.5", "over") and not won(m, "OU2.5", "under")
    assert won(sim(2, 1, 1), "1X2", "X") and won(sim(3, 0, 0), "OU2.5", "under")


def test_clustered_mean_counts_matches_not_bets():
    # due giocate identiche della stessa partita non dimezzano l'incertezza
    single = clustered_mean([1.0, -1.0, 0.5], [1, 2, 3])
    doubled = clustered_mean([1.0, 1.0, -1.0, -1.0, 0.5, 0.5], [1, 1, 2, 2, 3, 3])
    assert doubled.mean == pytest.approx(single.mean)
    assert doubled.std_error == pytest.approx(single.std_error)
    assert doubled.clusters == 3 and doubled.n == 6


def test_rules():
    d72 = Rule("D72")
    assert d72.required(2.0) == pytest.approx(0.02)
    assert d72.required(1.2) == pytest.approx(0.015)  # pavimento
    assert not d72.qualifies(4.5, 0.2)  # oltre il tetto
    old = Rule("fissa", cap=None, flat=0.02)
    assert old.qualifies(6.0, 0.021) and old.required(1.2) == 0.02


def test_occasions_value_clv_and_profit():
    # 1 al 50%, bet365 2,20 → valore +10%; chiude al 52% → CLV 0,52 × 2,2 − 1 = +14,4%; finisce 2-0
    m = sim(1, 2, 0, close1x2=(0.52, 0.29, 0.19))
    plays = occasions([m], Rule("D72"))
    assert [(p.market, p.selection) for p in plays] == [("1X2", "1")]  # X: 0,3 × 3,3 − 1 = −1%; 2: 0
    p = plays[0]
    assert p.value == pytest.approx(0.10) and p.clv == pytest.approx(0.144) and p.profit == pytest.approx(1.2)
    s = summarize_plays(plays)
    assert s.clv.mean == pytest.approx(0.144) and s.roi.mean == pytest.approx(1.2)


def test_calibration_and_favorite():
    matches = [sim(i, 1, 0) for i in range(6)] + [sim(i + 10, 0, 1) for i in range(4)]  # l'1 al 50% esce 6 volte su 10
    bins = {round(b.low, 1): b for b in calibration(matches, "1X2")}
    assert bins[0.5].n == 10 and bins[0.5].predicted == pytest.approx(0.5) and bins[0.5].observed == pytest.approx(0.6)
    assert bins[0.5].std_error == pytest.approx(math.sqrt(10 * 0.25) / 10)
    fav = favorite_hits(matches, "1X2")
    assert (fav.n, fav.observed) == (10, 6) and fav.expected == pytest.approx(5.0)


def test_daily_multiples_and_summary():
    day = date(2025, 1, 4)
    # quattro favorite al 70% pagate 1,48 (valore +3,6%): multipla equilibrata da 4 a quota 4,80 (il profilo arriva a 5)
    matches = [sim(i, 1, 0, fair1x2=(0.7, 0.2, 0.1), book1x2=(1.48, 4.5, 8.0), day=day) for i in range(4)]
    ms = daily_multiples(matches, PROFILES["equilibrata"], 4)
    assert len(ms) == 1 and ms[0].won and ms[0].price == pytest.approx(1.48**4)
    assert ms[0].probability == pytest.approx(0.7**4)
    s = summarize_multiples(ms)
    assert s.wins == 1 and s.expected_wins == pytest.approx(0.2401) and s.roi == pytest.approx(1.48**4 - 1)
