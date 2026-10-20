"""Angoli e cartellini nel radar (D94): nomi, esiti, ricerca delle occasioni, lettura dallo storico OddsPapi."""

from datetime import UTC, datetime

import pytest

from app.adapters.oddspapi import parse_history, secondary_market_map
from app.forecast.radar import scan
from app.forecast.radar_markets import is_secondary, parse_secondary, secondary_name, secondary_won, selections


def test_names_round_trip():
    assert secondary_name("angoli", "casa", 4.5) == "CORH4.5"
    assert parse_secondary("CRD3.5") == ("cartellini", "totale", 3.5)
    assert parse_secondary("CRDA1.5") == ("cartellini", "ospite", 1.5)
    assert is_secondary("COR10.5") and not is_secondary("OU2.5") and not is_secondary("COR10.0")
    assert selections("COR9.5") == ("over", "under") and selections("1X2") == ("1", "X", "2")


def test_secondary_won():
    corners, yellow, red = (6, 5), (2, 3), (0, 1)
    assert secondary_won("COR10.5", "over", corners, yellow, red)  # 11 angoli
    assert secondary_won("CORA4.5", "over", corners, yellow, red)  # ospite 5
    assert secondary_won("CRD5.5", "over", corners, yellow, red)  # 2 + 3 + 1 rosso = 6
    assert secondary_won("CRDH2.5", "under", corners, yellow, red)  # casa 2
    assert secondary_won("CRD5.5", "over", corners, (None, None), red) is None  # dati mancanti


def test_scan_finds_secondary_occasions():
    book = {
        "pinnacle": {"COR9.5": {"over": 1.95, "under": 1.95}},
        "sisal": {"COR9.5": {"over": 2.20, "under": 1.65}},
    }
    [signal] = scan(book, playable=("sisal",))
    assert (signal.market, signal.selection, signal.price) == ("COR9.5", "over", 2.20)
    assert signal.value == pytest.approx(0.5 * 2.20 - 1)


DEFS = [
    {"marketId": 10803, "marketName": "Corners - Over Under Full Time", "handicap": 9.5, "period": "fulltime",
     "outcomes": [{"outcomeId": 10803, "outcomeName": "Over"}, {"outcomeId": 10804, "outcomeName": "Under"}]},
    {"marketId": 101066, "marketName": "Bookings - Over Under Team 2", "handicap": 1.5, "period": "fulltime",
     "outcomes": [{"outcomeId": 101066, "outcomeName": "Over"}, {"outcomeId": 101067, "outcomeName": "Under"}]},
    {"marketId": 101551, "marketName": "Corners - Over Under First Half", "handicap": 4.5, "period": "p1",
     "outcomes": [{"outcomeId": 1, "outcomeName": "Over"}, {"outcomeId": 2, "outcomeName": "Under"}]},
]  # fmt: skip


def test_secondary_market_map_and_history_only_for_three_bookmakers():
    mapping = secondary_market_map(DEFS)
    assert {name for name, _ in mapping.values()} == {"COR9.5", "CRDA1.5"}  # niente primo tempo
    point = [{"createdAt": "2026-10-20T10:00:00.000Z", "price": 2.1, "active": True}]
    market = {"outcomes": {"10803": {"players": {"0": point}}, "10804": {"players": {"0": point}}}}
    body = {"bookmakers": {"sisal.it": {"markets": {"10803": market}}, "snai.it": {"markets": {"10803": market}}}}
    history = parse_history(body, mapping)
    assert "COR9.5" in history["sisal"] and "snai" not in history  # Snai: solo mercati principali
    assert history["sisal"]["COR9.5"]["over"] == [(datetime(2026, 10, 20, 10, tzinfo=UTC), 2.1)]
