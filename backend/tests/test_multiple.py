"""Multipla del giorno: probabilità, quota, arrivare vivi all'ultima, valore atteso e scelta delle gambe."""

from datetime import UTC, datetime, timedelta

import pytest

from app.adapters.football_data import parse_csv
from app.api.picks import horizon_end
from app.forecast.multiple import Leg, Multiple, eligible, multiple_of_the_day
from app.ingest.football_data import import_matches
from tests.test_football_api import day, match_id, seeded  # noqa: F401 (fixture condivisa)
from tests.test_radar_service import set_odds

T0 = datetime(2026, 10, 17, 12, 0, tzinfo=UTC)


def leg(match_id, p, price, hours=0, market="1X2", selection="1"):
    return Leg(match_id, T0 + timedelta(hours=hours), market, selection, p, price)


def test_multiple_numbers():
    m = Multiple((leg(1, 0.8, 1.3), leg(2, 0.75, 1.4), leg(3, 0.7, 1.5), leg(4, 0.7, 1.45)), with_value=True)
    assert m.price == pytest.approx(1.3 * 1.4 * 1.5 * 1.45)  # 3,9585
    assert m.win_probability == pytest.approx(0.8 * 0.75 * 0.7 * 0.7)  # 0,294
    assert m.alive_before_last == pytest.approx(0.8 * 0.75 * 0.7)  # viva prima dell'ultima partita
    assert m.expected_value == pytest.approx(0.294 * 3.9585 - 1)  # +16,4%
    assert m.one_in == pytest.approx(1 / 0.294)


def test_eligible_legs():
    assert eligible(leg(1, 0.70, 1.45), min_value=0.0)  # +1,5%
    assert not eligible(leg(1, 0.60, 1.80), min_value=0.0)  # probabilità sotto il 65%
    assert not eligible(leg(1, 0.70, 1.40), min_value=0.0)  # −2%: niente valore
    assert eligible(leg(1, 0.70, 1.40), min_value=-0.05)  # ma nella norma
    assert not eligible(leg(1, 0.70, 1.30), min_value=-0.05)  # −9%: paga poco
    assert not eligible(leg(1, 0.70, 1.70), min_value=0.0)  # +19%: sospetto


def test_prefers_value_then_highest_win_probability_in_price_range():
    legs = [
        leg(1, 0.80, 1.27, hours=3), leg(2, 0.78, 1.30, hours=0), leg(3, 0.75, 1.36, hours=1),
        leg(4, 0.72, 1.42, hours=2), leg(5, 0.66, 1.53, hours=4),
        leg(6, 0.90, 1.05, hours=5),  # −5,5%: paga poco, mai in multipla
    ]  # fmt: skip
    m = multiple_of_the_day(legs)
    assert m.with_value
    assert [l.match_id for l in m.legs] == [2, 3, 4, 1]  # le 4 più probabili, in ordine di calcio d'inizio
    assert 3.0 <= m.price <= 5.0


def test_one_leg_per_match_and_fallback_without_value():
    # Ogni gamba ha valore −2%: nessuna multipla "con valore", ma c'è quella nella norma
    legs = [leg(i, 0.72, 0.98 / 0.72, hours=i) for i in range(1, 5)]
    legs.append(leg(1, 0.85, 0.98 / 0.85, hours=1, market="DC", selection="1X"))  # stessa partita, altro mercato
    m = multiple_of_the_day(legs)
    assert m is not None and not m.with_value
    assert len({l.match_id for l in m.legs}) == 4
    assert m.expected_value == pytest.approx(0.98**4 - 1)  # il margine si moltiplica: −7,8%


def test_no_multiple_when_impossible():
    assert multiple_of_the_day([leg(i, 0.9, 1.1) for i in range(1, 4)]) is None  # solo 3 partite
    # 4 partite ma quota totale fuori dall'intervallo 3–5 (1,15^4 = 1,75)
    assert multiple_of_the_day([leg(i, 0.88, 1.15) for i in range(1, 5)]) is None


def test_horizon_end_is_italian_midnight():
    # 23:30 italiane del 17 ottobre (ora legale, UTC+2) → fine giornata a mezzanotte italiana = 22:00 UTC
    now = datetime(2026, 10, 17, 21, 30, tzinfo=UTC)
    assert horizon_end(now, "today") == datetime(2026, 10, 17, 22, 0, tzinfo=UTC)
    assert horizon_end(now, "week") == now + timedelta(days=7)


def test_multiple_api_per_bookmaker(logged_client, seeded, db):  # noqa: F811
    rows = "Div,Date,Time,HomeTeam,AwayTeam,AvgH,AvgD,AvgA\n" + "".join(
        f"I1,{day(2)},{h}:00,{a},{b},1.5,4,6\n" for h, a, b in [(12, "Roma", "Lazio"), (15, "Napoli", "Genoa"), (18, "Juventus", "Lecce"), (20, "Atalanta", "Cagliari")]
    )
    import_matches(db, parse_csv(rows), season="2026/27")
    for home, away in [("Roma", "Lazio"), ("Napoli", "Genoa"), ("Juventus", "Lecce"), ("Atalanta", "Cagliari")]:
        m = match_id(db, home, away)
        set_odds(db, m, "pinnacle", {"1": 1.38, "X": 5.0, "2": 9.0})  # 1 giusto ≈ 0,707
        set_odds(db, m, "sisal", {"1": 1.45, "X": 4.5, "2": 8.0})  # 0,707 × 1,45 − 1 ≈ +2,5%
    body = logged_client.get("/api/picks/multiple?horizon=week").json()
    assert body["missing"] == ["Eurobet"]  # su Eurobet niente quote: nessuna multipla
    [sisal] = body["multiples"]
    assert sisal["bookmaker"] == "Sisal" and sisal["with_value"] is True
    assert [leg["match"]["home"]["name"] for leg in sisal["legs"]] == ["Roma", "Napoli", "Juventus", "Atalanta"]
    assert sisal["price"] == pytest.approx(1.45**4)
    p = sisal["legs"][0]["probability"]
    assert sisal["win_probability"] == pytest.approx(p**4)
    assert sisal["alive_before_last"] == pytest.approx(p**3)
    assert sisal["expected_value"] == pytest.approx(p**4 * 1.45**4 - 1)
    assert logged_client.get("/api/picks/multiple?horizon=today").json()["multiples"] == []  # oggi non si gioca
