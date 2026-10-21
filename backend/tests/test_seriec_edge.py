"""Prova D98: consenso dei bookmaker italiani, correzioni T1-T3, Occasioni contro il consenso (T4)."""

from datetime import UTC, datetime, timedelta

import pytest

from app.forecast.seriec_edge import (
    SPECS,
    MatchBook,
    Row,
    calibration_correction,
    consensus,
    cross_validated,
    fit,
    improvement,
    kaunitz_occasions,
    model_occasions,
    lineup_correction,
    opening_consensus,
    pool_correction,
)

KO = datetime(2026, 10, 1, 18, tzinfo=UTC)


def flat(price: float, since: timedelta = timedelta(days=3)) -> list:
    return [(KO - since, price)]


def book_1x2(**bms: tuple[float, float, float]) -> dict:
    return {bm: {"1X2": {s: flat(p) for s, p in zip(("1", "X", "2"), prices)}} for bm, prices in bms.items()}


def test_consensus_needs_two_bookmakers_and_can_exclude_one():
    book = {"sisal": {"1": 2.0, "X": 3.0, "2": 6.0}, "snai": {"1": 2.0, "X": 3.0, "2": 6.0}}
    c = consensus(book, "1X2")
    assert c == pytest.approx({"1": 0.5, "X": 1 / 3, "2": 1 / 6})  # 1/2 + 1/3 + 1/6 = 1: nessun margine
    assert consensus(book, "1X2", exclude=("sisal",)) is None


def test_snapshot_closing_and_winner():
    prices = book_1x2(sisal=(2.0, 3.2, 4.0), snai=(2.1, 3.1, 3.9))
    prices["sisal"]["1X2"]["1"].append((KO - timedelta(hours=1), None))  # quota tolta prima del fischio
    m = MatchBook(1, KO, 2, 2, prices)
    assert set(m.snapshot("1X2")) == {"sisal", "snai"}  # in chiusura vale l'ultima quota attiva
    assert set(m.snapshot("1X2", KO - timedelta(minutes=30))) == {"snai"}  # in quel momento era tolta
    assert (m.winner("1X2"), m.winner("OU2.5"), m.winner("GG")) == ("X", "over", "yes")


def test_opening_consensus_waits_for_two_bookmakers():
    prices = {"sisal": {"1X2": {s: flat(p, timedelta(days=5)) for s, p in zip("1X2", (2.0, 3.0, 6.0))}},
              "snai": {"1X2": {s: flat(p, timedelta(days=2)) for s, p in zip("1X2", (2.0, 3.0, 6.0))}}}  # fmt: skip
    assert opening_consensus(MatchBook(1, KO, 1, 0, prices)) == pytest.approx({"1": 0.5, "X": 1 / 3, "2": 1 / 6})
    del prices["snai"]
    assert opening_consensus(MatchBook(1, KO, 1, 0, prices)) is None


def row(outcome: int, extra: tuple = (0.0,), c: tuple = (0.45, 0.30, 0.25), day: int = 0) -> Row:
    return Row(day, KO + timedelta(days=day), outcome, c, extra)


def test_neutral_parameters_give_back_the_consensus():
    r = row(0, extra=(0.3,))
    assert lineup_correction(r, [0.0]) == pytest.approx(r.consensus)
    assert pool_correction(row(0, extra=(0.6, 0.2, 0.2)), [0.0]) == pytest.approx(r.consensus)
    assert calibration_correction(r, [1.0, 0.0]) == pytest.approx(r.consensus)


def test_corrections_move_probability_the_right_way():
    p = lineup_correction(row(0, extra=(0.5,)), [-1.0])  # più assenti in casa e β < 0: scende l'1, sale il 2
    assert p[0] < 0.45 and p[2] > 0.25
    assert pool_correction(row(0, extra=(0.6, 0.2, 0.2)), [1.0]) == pytest.approx((0.6, 0.2, 0.2))
    assert calibration_correction(row(0), [1.0, 0.5])[1] > 0.30


def test_fit_finds_more_draws_and_cross_validation_scores_every_match():
    # 40% di pareggi contro il 30% del consenso: δ stimato positivo, e la correzione migliora la log loss
    rows = [row(1 if i % 5 < 2 else 0 if i % 5 < 4 else 2, day=i) for i in range(100)]
    alpha, delta = fit(rows, SPECS["T3 calibrazione (pareggi, sfavoriti)"])
    assert delta > 0.1
    preds = cross_validated(rows, SPECS["T3 calibrazione (pareggi, sfavoriti)"])
    assert len(preds) == len(rows) and all(len(p) == 3 for p in preds)
    assert improvement(rows, preds).mean < 0


def test_kaunitz_occasion_against_the_other_two_bookmakers():
    # Sisal paga il 2 a 3,6 mentre Eurobet e Snai lo danno a 3,0 (prob. giusta 0,317): valore +14%
    prices = book_1x2(sisal=(2.2, 3.3, 3.6), eurobet=(2.4, 3.3, 3.0), snai=(2.4, 3.3, 3.0))
    m = MatchBook(7, KO, 0, 1, prices)
    plays = [p for p in kaunitz_occasions([m]) if p.market == "1X2"]
    assert [(p.selection, p.bookmaker, p.price) for p in plays] == [("2", "sisal", 3.6)]
    fair_others = (1 / 3.0) / (1 / 2.4 + 1 / 3.3 + 1 / 3.0)
    assert plays[0].value == pytest.approx(fair_others * 3.6 - 1)
    assert plays[0].clv == pytest.approx(plays[0].p_close * 3.6 - 1)  # chiusura: consenso di tutti e tre
    assert plays[0].won  # finita 0-1
    assert len({(p.selection, p.market) for p in plays}) == len(plays)  # una sola giocata per esito


def test_model_occasions_use_archie_probabilities():
    prices = book_1x2(sisal=(2.2, 3.3, 3.6), eurobet=(2.4, 3.3, 3.0), snai=(2.4, 3.3, 3.0))
    m = MatchBook(7, KO, 2, 0, prices)
    plays = model_occasions([m], {(7, "1X2"): {"1": 0.50, "X": 0.27, "2": 0.23}})
    assert [(p.selection, p.bookmaker, p.price) for p in plays] == [("1", "eurobet", 2.4)]  # 0,50 × 2,4 − 1 = +20%
    assert plays[0].won and plays[0].clv == pytest.approx(plays[0].p_close * 2.4 - 1)
    assert model_occasions([m], {}) == []  # senza previsione di Archie niente occasioni
