"""Radar delle quote: probabilità giusta sharp contro la quota migliore giocabile."""

import pytest

from app.forecast.clv import ClvSummary
from app.forecast.demargin import shin
from app.forecast.radar import closing_value, fair_reference, live_verdict, qualifies, required_value, scan, summarize_live

# Pinnacle 1X2 2,00 / 3,60 / 4,00 → giuste con Shin (D72) ≈ 0,4897 / 0,2690 / 0,2414
PINNACLE = {"1X2": {"1": 2.0, "X": 3.6, "2": 4.0}}
FAIR = shin([2.0, 3.6, 4.0])


def test_required_value_grows_with_price():
    assert required_value(1.3) == pytest.approx(0.015)  # mai sotto l'1,5%
    assert required_value(2.0) == pytest.approx(0.02)
    assert required_value(3.0) == pytest.approx(0.02 * 2**0.5)  # 2,8%
    assert required_value(4.0) == pytest.approx(0.02 * 3**0.5)  # 3,5%
    assert qualifies(2.0, 0.02) and not qualifies(2.0, 0.019)
    assert not qualifies(4.5, 0.30)  # oltre quota 4 mai, qualunque sia il valore


def test_fair_reference_prefers_pinnacle_then_betfair():
    book = {"pinnacle": PINNACLE, "betfair_ex": {"1X2": {"1": 1.5, "X": 4.0, "2": 7.0}}}
    source, fair = fair_reference(book, "1X2")
    assert source == "pinnacle"
    assert fair["1"] == pytest.approx(FAIR[0])
    assert sum(fair.values()) == pytest.approx(1.0)
    # Pinnacle incompleto (manca il pareggio) → si passa a Betfair
    book["pinnacle"] = {"1X2": {"1": 2.0, "2": 4.0}}
    assert fair_reference(book, "1X2")[0] == "betfair_ex"
    assert fair_reference({"bet365": PINNACLE}, "1X2") is None  # nessun bookmaker sharp


def test_scan_finds_value_at_best_playable_price():
    book = {
        "pinnacle": PINNACLE,
        "bet365": {"1X2": {"1": 2.10, "X": 3.4, "2": 3.9}},  # 1: 0,4897 × 2,10 − 1 = +2,8% (soglia 2,1%)
        "sisal": {"1X2": {"1": 2.05, "X": 3.5, "2": 3.8}},
    }
    signals = scan(book, playable=("bet365", "sisal"))
    assert len(signals) == 1
    s = signals[0]
    assert (s.market, s.selection, s.bookmaker, s.price, s.fair_source) == ("1X2", "1", "bet365", 2.1, "pinnacle")
    assert s.value == pytest.approx(FAIR[0] * 2.1 - 1)
    assert not s.suspicious


def test_threshold_depends_on_price_ties_cap_and_suspicious():
    # Pareggio a 3,80: +2,2% non basta a quella quota (soglia 3,35%); a 3,90: +4,9% sì
    assert scan({"pinnacle": PINNACLE, "bet365": {"1X2": {"X": 3.8}}}, playable=("bet365",)) == []
    book = {"pinnacle": PINNACLE, "bet365": {"1X2": {"X": 3.9}}, "snai": {"1X2": {"X": 3.9}}}
    assert [s.bookmaker for s in scan(book, playable=("snai", "bet365"))] == ["snai"]  # a parità vince il primo
    # Ospite a 5,00: +20,7% ma quota oltre 4 → nessuna occasione
    assert scan({"pinnacle": PINNACLE, "bet365": {"1X2": {"2": 5.0}}}, playable=("bet365",)) == []
    huge = scan({"pinnacle": PINNACLE, "bet365": {"1X2": {"1": 2.4}}}, playable=("bet365",))[0]  # +17,5%
    assert huge.suspicious


def test_scan_sorts_by_value_and_ignores_sharp_books_as_offers():
    book = {
        "pinnacle": PINNACLE | {"OU2.5": {"over": 1.9, "under": 1.9}},  # giuste 0,5 / 0,5
        "bet365": {"1X2": {"1": 2.1}, "OU2.5": {"over": 2.1, "under": 1.7}},  # 1: +2,8%, over: +5%
    }
    signals = scan(book, playable=("bet365",))
    assert [(s.market, s.selection) for s in signals] == [("OU2.5", "over"), ("1X2", "1")]
    assert signals[0].value == pytest.approx(0.05)
    assert scan({"pinnacle": PINNACLE}) == []  # Pinnacle non è giocabile in Italia
    assert len(scan(book, playable=("bet365",), all_outcomes=True)) == 3  # tutti gli esiti con una quota


def test_closing_value_and_live_summary():
    assert closing_value(2.2, 0.5) == pytest.approx(0.10)
    assert closing_value(1.9, 0.5) == pytest.approx(-0.05)
    s = summarize_live([0.10, -0.05, 0.04], [1.2, -1.0, -1.0])
    assert s.n == 3
    assert s.mean_clv == pytest.approx(0.03)
    # scarti 0,07 / −0,08 / 0,01 → varianza (0,0049 + 0,0064 + 0,0001) / 2 = 0,0057
    assert s.clv_std_error == pytest.approx((0.0057 / 3) ** 0.5)
    assert s.share_positive == pytest.approx(2 / 3)
    assert s.roi == pytest.approx(-0.8 / 3)
    assert summarize_live([], []) is None


def test_live_verdict_needs_300_bets_and_two_standard_errors():
    assert live_verdict(None) == "in prova"
    assert live_verdict(ClvSummary(299, 0.05, 0.01, 0.6, 0.0)) == "in prova"
    assert live_verdict(ClvSummary(300, 0.03, 0.01, 0.6, 0.0)) == "superato"
    assert live_verdict(ClvSummary(300, 0.02, 0.01, 0.6, 0.0)) == "non superato"  # esattamente 2 errori standard non basta
