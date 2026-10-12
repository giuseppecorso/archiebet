"""Giocate di valore e CLV nel backtest; quote senza margine. Valori calcolati a mano."""

from dataclasses import replace

import pytest

from app.forecast.backtest import Prediction
from app.forecast.clv import summarize, value_bets
from app.forecast.data import fair_odds_probabilities, reference_1x2

# Partita 1: finisce 2-1 (vince la casa, over). Il modello dà 1 al 50%, over al 60%.
PRED = Prediction(1, 7, "2023/24", 0, 3, True, (0.5, 0.3, 0.2), 0.6, 0.55)
OFFERED = {1: {"1X2": {"1": 2.2, "X": 3.2, "2": 4.0}, "OU2.5": {"over": 1.6, "under": 2.3}}}
CLOSING_FAIR = {1: {"1X2": {"1": 0.48, "X": 0.30, "2": 0.22}, "OU2.5": {"over": 0.58, "under": 0.42}}}


def test_value_bets_by_hand():
    bets = value_bets([PRED], OFFERED, CLOSING_FAIR, threshold=0.05)
    # Valori: 1 → 0,5·2,2−1 = +10%; X → 0,3·3,2−1 = −4%; 2 → 0,2·4,0−1 = −20%; over → 0,6·1,6−1 = −4%; under → 0,4·2,3−1 = −8%
    assert [(b.market, b.selection) for b in bets] == [("1X2", "1")]
    b = bets[0]
    assert b.value == pytest.approx(0.10)
    assert b.clv == pytest.approx(2.2 * 0.48 - 1)  # +5,6%: la quota presa batte la chiusura
    assert b.won


def test_threshold_and_missing_closing():
    assert len(value_bets([PRED], OFFERED, CLOSING_FAIR, threshold=0.11)) == 0
    assert value_bets([PRED], OFFERED, {}, threshold=0.05) == []  # senza chiusura niente CLV, niente giocata


def test_summary_by_hand():
    bets = value_bets([PRED], OFFERED, CLOSING_FAIR) * 2
    lost = value_bets([replace(PRED, outcome=2)], OFFERED, CLOSING_FAIR)  # stessa giocata, ma vince l'ospite
    s = summarize(bets + lost)
    assert s.n == 3
    assert s.mean_clv == pytest.approx(0.056)
    assert s.share_positive == pytest.approx(1.0)
    assert s.roi == pytest.approx((1.2 + 1.2 - 1) / 3)
    assert summarize([]) is None


def test_fair_odds_probabilities():
    fair = fair_odds_probabilities({5: {"1X2": {"1": 1.9, "X": 3.8, "2": 3.8}, "OU2.5": {"over": 1.9, "under": 1.9}}})
    assert fair[5]["1X2"] == pytest.approx({"1": 0.5, "X": 0.25, "2": 0.25})
    assert fair[5]["OU2.5"] == pytest.approx({"over": 0.5, "under": 0.5})
    assert reference_1x2(fair) == {5: pytest.approx((0.5, 0.25, 0.25))}
