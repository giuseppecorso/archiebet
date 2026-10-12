"""Radar delle quote: probabilità giusta sharp contro la quota migliore giocabile."""

import pytest

from app.forecast.clv import ClvSummary
from app.forecast.radar import closing_value, fair_reference, live_verdict, scan, summarize_live

# Pinnacle 1X2 2,00 / 3,60 / 4,00 → implicite 0,5 + 0,2778 + 0,25 = 1,0278 → giuste 0,4865 / 0,2703 / 0,2432
PINNACLE = {"1X2": {"1": 2.0, "X": 3.6, "2": 4.0}}


def test_fair_reference_prefers_pinnacle_then_betfair():
    book = {"pinnacle": PINNACLE, "betfair_ex": {"1X2": {"1": 1.5, "X": 4.0, "2": 7.0}}}
    source, fair = fair_reference(book, "1X2")
    assert source == "pinnacle"
    assert fair["1"] == pytest.approx(0.5 / (0.5 + 1 / 3.6 + 0.25))
    assert sum(fair.values()) == pytest.approx(1.0)
    # Pinnacle incompleto (manca il pareggio) → si passa a Betfair
    book["pinnacle"] = {"1X2": {"1": 2.0, "2": 4.0}}
    assert fair_reference(book, "1X2")[0] == "betfair_ex"
    assert fair_reference({"bet365": PINNACLE}, "1X2") is None  # nessun bookmaker sharp


def test_scan_finds_value_at_best_playable_price():
    fair_away = 0.25 / (0.5 + 1 / 3.6 + 0.25)  # 0,2432
    book = {
        "pinnacle": PINNACLE,
        "bet365": {"1X2": {"1": 1.95, "X": 3.4, "2": 4.4}},  # 2: 0,2432 × 4,4 − 1 = +7,0%
        "sisal": {"1X2": {"1": 1.90, "X": 3.5, "2": 4.2}},
    }
    signals = scan(book, playable=("bet365", "sisal"))
    assert len(signals) == 1
    s = signals[0]
    assert (s.market, s.selection, s.bookmaker, s.price, s.fair_source) == ("1X2", "2", "bet365", 4.4, "pinnacle")
    assert s.value == pytest.approx(fair_away * 4.4 - 1)
    assert not s.suspicious


def test_scan_threshold_ties_and_suspicious():
    book = {"pinnacle": PINNACLE, "bet365": {"1X2": {"2": 4.2}}, "snai": {"1X2": {"2": 4.2}}}
    # 0,2432 × 4,2 − 1 = +2,2%: sopra la soglia del 2%, sotto quella del 3%
    assert [s.bookmaker for s in scan(book, playable=("snai", "bet365"))] == ["snai"]  # a parità vince il primo
    assert scan(book, threshold=0.03, playable=("snai", "bet365")) == []
    huge = scan({"pinnacle": PINNACLE, "bet365": {"1X2": {"2": 5.0}}})[0]  # +21,6%
    assert huge.suspicious


def test_scan_sorts_by_value_and_ignores_sharp_books_as_offers():
    book = {
        "pinnacle": PINNACLE | {"OU2.5": {"over": 1.9, "under": 1.9}},  # giuste 0,5 / 0,5
        "bet365": {"1X2": {"2": 4.3}, "OU2.5": {"over": 2.1, "under": 1.7}},  # 2: +4,6%, over: +5%
    }
    signals = scan(book)
    assert [(s.market, s.selection) for s in signals] == [("OU2.5", "over"), ("1X2", "2")]
    assert signals[0].value == pytest.approx(0.05)
    assert scan({"pinnacle": PINNACLE}) == []  # Pinnacle non è giocabile in Italia


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
