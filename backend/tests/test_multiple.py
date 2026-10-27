"""Multipla del giorno: probabilità, quota, arrivare vivi all'ultima, valore atteso e scelta delle gambe."""

from datetime import UTC, date, datetime, timedelta

import pytest

from app.adapters.football_data import parse_csv
from app.api.picks import horizon_end, horizon_window
from app.forecast.multiple import PROFILES, Leg, Multiple, build_multiple, eligible, multiple_of_the_day
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
        f"I1,{day(2)},{h}:00,{a},{b},1.5,4,6\n" for h, a, b in [(12, "Torino", "Monza"), (15, "Napoli", "Genoa"), (18, "Juventus", "Lecce"), (20, "Atalanta", "Cagliari")]
    )
    import_matches(db, parse_csv(rows), season="2026/27")
    for home, away in [("Torino", "Monza"), ("Napoli", "Genoa"), ("Juventus", "Lecce"), ("Atalanta", "Cagliari")]:
        m = match_id(db, home, away)
        set_odds(db, m, "pinnacle", {"1": 1.38, "X": 5.0, "2": 9.0})  # 1 giusto ≈ 0,707
        set_odds(db, m, "sisal", {"1": 1.45, "X": 4.5, "2": 8.0})  # 0,707 × 1,45 − 1 ≈ +2,5%
    body = logged_client.get("/api/picks/multiple?horizon=week").json()
    assert body["missing"] == ["Altri bookmakers"]  # su Eurobet niente quote: nessuna multipla (nome nascosto, D154)
    [sisal] = body["multiples"]
    assert sisal["bookmaker"] == "Altri bookmakers" and sisal["with_value"] is True
    assert [leg["match"]["home"]["name"] for leg in sisal["legs"]] == ["Torino", "Napoli", "Juventus", "Atalanta"]
    assert sisal["price"] == pytest.approx(1.45**4)
    p = sisal["legs"][0]["probability"]
    assert sisal["win_probability"] == pytest.approx(p**4)
    assert sisal["alive_before_last"] == pytest.approx(p**3)
    assert sisal["expected_value"] == pytest.approx(p**4 * 1.45**4 - 1)
    assert logged_client.get("/api/picks/multiple?horizon=today").json()["multiples"] == []  # oggi non si gioca



def test_profiles_change_the_choice():
    legs = [
        leg(1, 0.85, 1.24, hours=1), leg(2, 0.82, 1.28, hours=2), leg(3, 0.80, 1.30, hours=3),  # sicure, +4/+5%
        leg(4, 0.50, 2.10, hours=4), leg(5, 0.48, 2.25, hours=5),  # rischiose, +5% e +8%
    ]  # fmt: skip
    calm = build_multiple(legs, n=3, profile=PROFILES["tranquilla"])
    assert [l.match_id for l in calm.legs] == [1, 2, 3] and calm.price == pytest.approx(1.24 * 1.28 * 1.30)  # 2,06
    assert build_multiple(legs, n=3, profile=PROFILES["equilibrata"]) is None  # al 65% la quota non arriva a 3
    bold = build_multiple(legs, n=3, profile=PROFILES["coraggiosa"])
    assert [l.match_id for l in bold.legs] == [1, 4, 5]  # valore atteso più alto con quota tra 5 e 15
    assert bold.expected_value == pytest.approx(0.85 * 0.5 * 0.48 * 1.24 * 2.10 * 2.25 - 1)  # +19,5%


def test_search_stays_fast_with_six_legs():
    import random
    import time

    random.seed(3)
    legs = [leg(m, p, (1 / p) * random.uniform(0.96, 1.04), hours=m, selection=str(k))
            for m in range(60) for k, p in enumerate(random.uniform(0.45, 0.9) for _ in range(6))]  # fmt: skip
    start = time.perf_counter()
    for name in PROFILES:
        build_multiple(legs, n=6, profile=PROFILES[name])
    assert time.perf_counter() - start < 5  # tre profili, 6 partite, 60 partite candidate


def test_generator_filters(logged_client, seeded, db):  # noqa: F811
    rows = "Div,Date,Time,HomeTeam,AwayTeam,AvgH,AvgD,AvgA\n" + "".join(
        f"I1,{day(2)},{h}:00,{a},{b},1.5,4,6\n" for h, a, b in [(12, "Torino", "Monza"), (15, "Napoli", "Genoa"), (18, "Juventus", "Lecce")]
    )
    import_matches(db, parse_csv(rows), season="2026/27")
    for home, away in [("Torino", "Monza"), ("Napoli", "Genoa"), ("Juventus", "Lecce")]:
        m = match_id(db, home, away)
        set_odds(db, m, "pinnacle", {"1": 1.35, "X": 5.0, "2": 9.0})  # 1 giusto ≈ 0,704
        set_odds(db, m, "sisal", {"1": 1.45, "X": 4.5, "2": 8.0})
    base = "/api/picks/multiple?horizon=week&profile=tranquilla&legs=3"
    [sisal] = logged_client.get(base).json()["multiples"]
    assert len(sisal["legs"]) == 3 and 2.0 <= sisal["price"] <= 3.5
    assert logged_client.get(base + "&markets=OU2.5").json()["multiples"] == []  # nessuna quota Under/Over
    assert logged_client.get(base + "&competitions=ITA-B").json()["multiples"] == []  # partite tutte di Serie A
    assert logged_client.get(base + "&competitions=ITA-A&markets=1X2").json()["multiples"][0]["legs"]
    assert logged_client.get("/api/picks/multiple?legs=9").status_code == 422  # massimo 6 partite


def test_horizon_windows_follow_italian_days():
    now = datetime(2026, 10, 17, 10, 0, tzinfo=UTC)  # sabato, mezzogiorno in Italia
    midnight = lambda d: datetime(2026, 10, d, 22, 0, tzinfo=UTC)  # mezzanotte italiana (ora legale) del giorno d+1
    assert horizon_window(now, "tomorrow") == (midnight(17), midnight(18))
    assert horizon_window(now, "2days") == (now, midnight(18))
    assert horizon_window(now, "3days") == (now, midnight(19))
    # dal giorno al giorno: mai prima di adesso, mai oltre 7 giorni
    assert horizon_window(now, "range", date(2026, 10, 17), date(2026, 10, 18)) == (now, midnight(18))
    assert horizon_window(now, "range", date(2026, 10, 19), date(2026, 10, 30)) == (midnight(18), now + timedelta(days=7))
    with pytest.raises(ValueError):
        horizon_window(now, "range", date(2026, 10, 19), None)


def test_multiple_range_needs_both_dates(logged_client):
    assert logged_client.get("/api/picks/multiple?horizon=range&date_from=2026-10-19").status_code == 422


def test_custom_profile_and_quality_tiers():
    from app.forecast.multiple import NORMAL, PAYS_LITTLE, VALUE, custom_profile

    p = custom_profile(0.05, 500, 1.0, by_value=True)  # valori fuori scala: riportati nei limiti
    assert (p.min_probability, p.min_total, p.max_total, p.by_value) == (0.20, 1.2, 200.0, True)
    good = [leg(i, 0.75, 1.40) for i in range(4)]  # valore +5% ciascuna
    assert build_multiple(good, 4, custom_profile(0.7, 2.0, 5.0, False)).quality == VALUE
    normal = [leg(i, 0.70, 1.40) for i in range(4)]  # −2%: nella norma
    assert build_multiple(normal, 4, custom_profile(0.6, 2.0, 5.0, False)).quality == NORMAL
    # Serie C: consenso italiano, quote con tutto il margine (−7%): solo nella fascia "paga poco", dichiarata
    serie_c = [Leg(i, datetime(2026, 10, 25, tzinfo=UTC), "1X2", "1", 0.70, 1.33, "consenso") for i in range(4)]
    m = build_multiple(serie_c, 4, custom_profile(0.6, 2.0, 5.0, False))
    assert m is not None and m.quality == PAYS_LITTLE and not m.with_value and m.legs[0].source == "consenso"
    assert set(PROFILES) == {"molto tranquilla", "tranquilla", "equilibrata", "coraggiosa", "spericolata", "caccia al clv"}


def test_clv_hunt_only_occasions_and_shorter_if_needed():
    """Caccia al CLV (D134): solo gambe che passano la regola delle Occasioni, per CLV atteso; più corta se mancano."""
    when = datetime(2026, 10, 25, tzinfo=UTC)
    legs = [
        Leg(1, when, "1X2", "1", 0.50, 2.10),  # valore +5%: occasione (soglia ~2% a quota 2,1)
        Leg(2, when, "OU2.5", "over", 0.55, 1.90),  # +4,5%: occasione
        Leg(3, when, "1X2", "X", 0.30, 3.40),  # +2%: sotto la soglia (~3,1% a quota 3,4)
        Leg(4, when, "DC", "1X", 0.80, 1.30),  # +4%, ma la doppia chance non è un mercato provato
        Leg(5, when, "1X2", "1", 0.60, 1.80, "consenso"),  # +8%, ma senza riferimento sharp
        Leg(6, when, "COR9.5", "over", 0.55, 1.95),  # angoli: non nella regola D72
    ]
    m = build_multiple(legs, 4, PROFILES["caccia al clv"])
    assert m is not None and {l.match_id for l in m.legs} == {1, 2}  # 4 richieste, solo 2 occasioni: multipla da 2
    assert build_multiple(legs[2:], 4, PROFILES["caccia al clv"]) is None  # nessuna occasione: nessuna multipla


def test_why_no_multiple_is_explained():
    from app.forecast.multiple import why_none

    when = datetime(2026, 10, 25, tzinfo=UTC)
    corners = [Leg(i, when, "COR9.5", "over", 0.55, 1.70) for i in range(3)]
    text = why_none(corners, 4, PROFILES["equilibrata"])
    assert "Solo 0 partite" in text and "65%" in text and "giorno prima" in text
    assert "Nessuna quota" in why_none([], 4, PROFILES["equilibrata"])
    assert "Occasioni" in why_none(corners, 4, PROFILES["caccia al clv"])
    easy = [leg(i, 0.9, 1.05) for i in range(1, 6)]  # partite valide, ma quota totale troppo bassa
    assert "quota totale 3–5" in why_none(easy, 4, PROFILES["equilibrata"])
