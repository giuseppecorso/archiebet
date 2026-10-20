"""Prova D82 (angoli e cartellini): linee, regole di conteggio, precisione in chiusura, occasioni."""

import math
from datetime import UTC, datetime, timedelta

import pytest

from app.forecast.demargin import shin
from app.forecast.secondary_test import Line, MarketHistory, Result, at, closing, closing_log_loss, line_of, occasions, over_won

KO = datetime(2026, 5, 10, 15, tzinfo=UTC)


def test_line_of_recognises_only_full_time_half_lines():
    assert line_of({"marketName": "Corners - Over Under Full Time", "handicap": 9.5, "period": "fulltime"}) == Line("angoli", "totale", 9.5)
    assert line_of({"marketName": "Bookings - Over Under Team 2", "handicap": 1.5, "period": "fulltime"}) == Line("cartellini", "ospite", 1.5)
    assert line_of({"marketName": "Corners - Over Under Full Time", "handicap": 10.0, "period": "fulltime"}) is None  # rimborso possibile
    assert line_of({"marketName": "Corners - Over Under First Half", "handicap": 4.5, "period": "p1"}) is None


def test_card_counting_rules():
    r = Result(6, 4, 2, 3, 0, 1)
    assert r.count("angoli", "totale") == 10 and r.count("angoli", "casa") == 6
    assert r.count("cartellini", "totale") == 6  # 2 + 3 gialli + 1 rosso
    assert r.count("cartellini", "totale", "punti") == 7  # il rosso vale 2
    assert over_won(r, Line("cartellini", "totale", 6.5), "punti") and not over_won(r, Line("cartellini", "totale", 6.5))


def test_at_takes_the_last_price_before():
    s = [(KO - timedelta(days=2), 1.9), (KO - timedelta(hours=3), 2.0), (KO - timedelta(hours=1), None)]
    assert at(s, KO - timedelta(days=1)) == 1.9
    assert at(s, KO - timedelta(hours=2)) == 2.0
    assert at(s, KO) is None  # quota tolta
    assert at(s, KO - timedelta(days=3)) is None
    assert closing(s, KO) == 2.0  # chiusura = ultima quota attiva prima del calcio d'inizio


def history(over_pin, under_pin, over_sisal, under_sisal, mid=1, line=Line("angoli", "totale", 9.5)):
    t0 = KO - timedelta(days=2)
    return MarketHistory(mid, KO, line, {
        "pinnacle": {"over": [(t0, over_pin)], "under": [(t0, under_pin)]},
        "sisal": {"over": [(t0, over_sisal)], "under": [(t0, under_sisal)]},
    })  # fmt: skip


def test_closing_log_loss_on_same_events():
    h = history(1.95, 1.95, 1.80, 1.80)
    res = {1: Result(6, 5, 0, 0, 0, 0)}  # 11 angoli: Over
    acc = {a.bookmaker: a for a in closing_log_loss([h], res, ["pinnacle", "sisal"], "angoli", "cartellini")}
    assert acc["pinnacle"].log_loss == pytest.approx(-math.log(0.5))
    assert acc["sisal"].n == 1


def test_occasions_take_the_first_detection_with_clv():
    h = history(2.0, 1.9, 2.25, 1.70)  # Sisal paga l'Over 2,25 contro un giusto di ~2,05
    plays = occasions([h], {1: Result(6, 5, 0, 0, 0, 0)}, ["sisal"])
    assert len(plays) == 1
    p = plays[0]
    fair_over = shin([2.0, 1.9])[0]
    assert (p.selection, p.price) == ("over", 2.25)
    assert p.value == pytest.approx(fair_over * 2.25 - 1)
    assert p.clv == pytest.approx(fair_over * 2.25 - 1)  # la quota di Pinnacle non si è mossa
    assert p.won
