"""Quando giocare (D119)."""

from datetime import UTC, datetime, timedelta

import pytest

from app.forecast import timing as tm

KO = datetime(2026, 5, 1, 18, tzinfo=UTC)


def _series(*points: tuple[float, float]) -> list:
    """(ore prima del calcio d'inizio, quota)"""
    return [(KO - timedelta(hours=h), p) for h, p in points]


def _book(fid: str, sisal_home: list, pinnacle_home: float = 2.0, kickoff: datetime = KO) -> tm.Book:
    shift = kickoff - KO

    def moved(series):
        return [(t + shift, p) for t, p in series]

    pin = {"1": moved(_series((100, pinnacle_home))), "X": moved(_series((100, 3.6))), "2": moved(_series((100, 4.2)))}
    sisal = {"1": moved(sisal_home), "X": moved(_series((100, 3.3))), "2": moved(_series((100, 3.8)))}
    return tm.Book(fid, "Serie A e B", kickoff, {"pinnacle": {"1X2": pin}, "sisal": {"1X2": sisal}})


def test_book_prices_and_fair():
    b = _book("a", _series((80, 2.1), (10, 1.95)))
    assert b.price("sisal", "1X2", "1", KO - timedelta(hours=48)) == 2.1
    assert b.price("sisal", "1X2", "1", None) == 1.95
    assert b.first_time() == KO - timedelta(hours=100)
    fair = b.fair("1X2", None, "pinnacle")
    assert sum(fair.values()) == pytest.approx(1.0) and fair["1"] > 0.45


def test_italian_consensus_needs_two_bookmakers():
    b = _book("a", _series((80, 2.1)))
    assert b.fair("1X2", None, "consensus") is not None  # Pinnacle e Sisal: due bookmaker con il mercato completo
    lone = tm.Book("b", "Serie C", KO, {"sisal": b.prices["sisal"]})
    assert lone.fair("1X2", None, "consensus") is None


def test_observations_clv_by_horizon():
    b = _book("a", _series((80, 2.2), (5, 2.0)))
    obs = [o for o in tm.observations([b], lambda _: "pinnacle") if o.price["30 minuti prima"] == 2.0]
    [o] = obs
    p_close = b.fair("1X2", None, "pinnacle")["1"]
    assert o.clv["48 ore prima"] == pytest.approx(2.2 * p_close - 1)
    assert o.clv["30 minuti prima"] == pytest.approx(2.0 * p_close - 1)
    assert o.clv["72 ore prima"] == pytest.approx(o.clv["48 ore prima"])
    assert o.clv[tm.FIRST] is None  # alla prima quota (100 ore prima, su X e 2) Sisal non quotava ancora l'1


def test_advise_play_early_when_prices_drop_in_both_halves():
    books = [_book(str(i), _series((80, 2.25 + 0.01 * (i % 3)), (3, 1.95)), kickoff=KO + timedelta(days=i)) for i in range(40)]
    obs = tm.observations(books, lambda _: "pinnacle")
    advice = tm.advise(obs)
    assert advice.verdict == tm.PLAY_EARLY and advice.best in ("72 ore prima", "48 ore prima", "24 ore prima", "12 ore prima", "6 ore prima")


def test_advise_indifferent_when_flat():
    books = [_book(str(i), _series((80, 2.0 + 0.02 * (i % 2 * 2 - 1)), (3, 2.0)), kickoff=KO + timedelta(days=i)) for i in range(40)]
    assert tm.advise(tm.observations(books, lambda _: "pinnacle")).verdict == tm.INDIFFERENT


def test_occasion_timing():
    # Sisal paga 2,30 a 48 ore (valore contro Pinnacle 2,0) e scende a 2,0 vicino al fischio: giocala subito
    books = [_book(str(i), _series((80, 2.3 - 0.01 * (i % 2)), (3, 2.0)), kickoff=KO + timedelta(days=i)) for i in range(30)]
    t = tm.occasion_timing(tm.observations(books, lambda _: "pinnacle"), "48 ore prima")
    assert t is not None and t.n == 30 and t.play_now and t.still_value == 0.0
    assert t.gain.mean > 0.1
