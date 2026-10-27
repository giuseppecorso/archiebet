"""Radar dal vivo: segnali salvati prima del calcio d'inizio, prima quota bloccata, CLV con la chiusura."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import delete, select

from app.forecast.demargin import shin
from app.forecast.radar import SIMULATION_BOOKMAKERS
from app.forecast.radar_service import live_summary, refresh_radar, settle_radar, won
from app.models import Match, MatchOdds, RadarSignal
from tests.test_football_api import match_id, seeded  # noqa: F401 (fixture condivisa)


def set_odds(db, match: int, bookmaker: str, prices: dict[str, float], closing: bool = False, market: str = "1X2"):
    db.execute(delete(MatchOdds).where(MatchOdds.match_id == match, MatchOdds.bookmaker == bookmaker,
                                       MatchOdds.market == market, MatchOdds.is_closing.is_(closing)))
    for selection, price in prices.items():
        db.add(MatchOdds(match_id=match, source="test", bookmaker=bookmaker, market=market, selection=selection,
                         price=Decimal(str(price)), is_closing=closing))
    db.commit()


def signals(db) -> list[RadarSignal]:
    return list(db.scalars(select(RadarSignal).order_by(RadarSignal.id)))


def test_detects_signal_only_before_kickoff(seeded, db):  # noqa: F811
    upcoming, started = match_id(db, "Milan", "Inter"), match_id(db, "Lazio", "Milan")
    for m in (upcoming, started):
        set_odds(db, m, "pinnacle", {"1": 2.0, "X": 3.6, "2": 4.0})  # giusta sull'1 (Shin): 0,4897
        set_odds(db, m, "sisal", {"1": 2.1, "X": 3.4, "2": 3.9})  # 1: +2,8% (soglia a 2,1: 2,1%)
    now = datetime.now(UTC)
    assert refresh_radar(db, now) == 1  # Lazio-Milan è già iniziata
    [s] = signals(db)
    assert (s.match_id, s.market, s.selection, s.bookmaker, s.price, s.fair_source) == (upcoming, "1X2", "1", "sisal", 2.1, "pinnacle")
    assert s.value == pytest.approx(shin([2.0, 3.6, 4.0])[0] * 2.1 - 1, abs=1e-5)
    assert s.latest_price == 2.1 and s.clv is None


def test_first_detection_is_locked_latest_follows_odds(seeded, db):  # noqa: F811
    m = match_id(db, "Milan", "Inter")
    set_odds(db, m, "pinnacle", {"1": 2.0, "X": 3.6, "2": 4.0})
    set_odds(db, m, "sisal", {"1": 2.1, "X": 3.4, "2": 3.9})
    now = datetime.now(UTC)
    refresh_radar(db, now)
    set_odds(db, m, "sisal", {"1": 2.0, "X": 3.4, "2": 3.9})  # la quota scende: niente più valore
    assert refresh_radar(db, now + timedelta(hours=6)) == 0
    [s] = signals(db)
    assert s.price == 2.1  # la giocata simulata resta quella
    assert s.latest_price == 2.0 and s.latest_value < 0
    set_odds(db, m, "sisal", {"X": 3.4, "2": 3.9})  # quota dell'1 sparita
    refresh_radar(db, now + timedelta(hours=12))
    assert signals(db)[0].latest_price is None


def test_settle_with_closing_reference_and_summary(seeded, db):  # noqa: F811
    m = match_id(db, "Milan", "Inter")
    set_odds(db, m, "pinnacle", {"1": 2.0, "X": 3.6, "2": 4.0})
    set_odds(db, m, "sisal", {"1": 2.1, "X": 3.4, "2": 3.9})
    refresh_radar(db, datetime.now(UTC))
    assert settle_radar(db) == 0  # partita non ancora giocata

    match = db.get(Match, m)
    match.status, match.home_goals, match.away_goals = "finished", 2, 0
    match.kickoff_at = datetime.now(UTC) - timedelta(hours=3)  # una partita finita è iniziata nel passato
    db.commit()
    assert settle_radar(db) == 0  # chiusura non ancora arrivata
    assert signals(db)[0].won is True  # l'esito invece si sa già

    set_odds(db, m, "betfair_ex", {"1": 2.2, "X": 3.6, "2": 3.6}, closing=True)  # niente Pinnacle: Betfair (D48)
    assert settle_radar(db) == 1
    s = signals(db)[0]
    fair_home = shin([2.2, 3.6, 3.6])[0]
    assert s.closing_source == "betfair_ex"
    assert s.clv == pytest.approx(2.1 * fair_home - 1, abs=1e-5)
    summary = live_summary(db)
    assert summary.n == 1 and summary.mean_clv == pytest.approx(s.clv)
    assert summary.roi == pytest.approx(1.1)  # vinta a 2,1
    assert settle_radar(db) == 0  # già chiuso


def test_radar_api_lists_signals_and_live_progress(logged_client, seeded, db):  # noqa: F811
    m = match_id(db, "Milan", "Inter")
    set_odds(db, m, "pinnacle", {"1": 2.0, "X": 3.6, "2": 4.0})
    set_odds(db, m, "sisal", {"1": 2.1, "X": 3.4, "2": 3.9})
    refresh_radar(db, datetime.now(UTC))
    assert logged_client.get("/api/radar").json()["upcoming"][0]["p_study"] is None  # partita non ancora studiata
    from app.forecast.study import model_probabilities
    from app.models import MatchStudy

    db.add(MatchStudy(match_id=m, computed_at=datetime.now(UTC), data={"lam": 1.6, "mu": 1.1, "rho": -0.05, "share_home": 0.45, "share_away": 0.45, "picks": []}))
    db.commit()
    body = logged_client.get("/api/radar").json()
    [s] = body["upcoming"]
    assert s["p_study"] == pytest.approx(model_probabilities(1.6, 1.1, -0.05, 0.45, 0.45)["1X2"]["1"])  # lo studio accanto (D152)
    assert (s["home"]["name"], s["selection"], s["bookmaker"], s["fair_source"]) == ("Milan", "1", "Altri bookmakers", "Pinnacle")
    assert s["price"] == 2.1 and s["suspicious"] is False
    assert s["required_value"] == pytest.approx(0.02 * 1.1**0.5)  # soglia a quota 2,1
    assert body["recent"] == []
    assert body["live"] == {"n": 0, "target": 300, "mean_clv": None, "clv_std_error": None,
                            "share_positive": None, "roi": None, "verdict": "in prova"}
    assert body["playable"] == ["Altri bookmakers"] and body["threshold"] == 0.02  # un solo nome per i bookmaker italiani (D154)
    assert body["simulation_bookmakers"] == ["Altri bookmakers"]  # la simulazione resta su tutti, il nome è uno (D154)


def test_simulation_on_all_bookmakers_but_giuse_sees_only_his(logged_client, seeded, db):  # noqa: F811
    m = match_id(db, "Milan", "Inter")
    set_odds(db, m, "pinnacle", {"1": 2.0, "X": 3.6, "2": 4.0})
    set_odds(db, m, "goldbet", {"1": 2.1, "X": 3.4, "2": 3.9})  # valore solo su Goldbet
    set_odds(db, m, "sisal", {"1": 1.95, "X": 3.4, "2": 3.8})
    assert refresh_radar(db, datetime.now(UTC), SIMULATION_BOOKMAKERS) == 1  # la simulazione lo conta (D74)
    assert signals(db)[0].bookmaker == "goldbet"
    assert logged_client.get("/api/radar").json()["upcoming"] == []  # ma a Giuse non si mostra: non ha il conto


def test_won_for_every_market():
    assert won(2, 1, "1X2", "1") and not won(2, 1, "1X2", "X")
    assert won(1, 1, "DC", "1X") and won(1, 1, "DC", "X2") and not won(1, 1, "DC", "12")
    assert won(0, 2, "DC", "12") and not won(0, 2, "DC", "1X")
    assert won(1, 1, "GG", "yes") and won(3, 0, "GG", "no") and not won(3, 0, "GG", "yes")
    assert won(2, 1, "OU2.5", "over") and won(1, 1, "OU2.5", "under")


def test_clv_does_not_wait_for_the_result(seeded, db):  # noqa: F811
    m = match_id(db, "Milan", "Inter")
    set_odds(db, m, "pinnacle", {"1": 2.0, "X": 3.6, "2": 4.0})
    set_odds(db, m, "sisal", {"1": 2.1, "X": 3.4, "2": 3.9})
    now = datetime.now(UTC)
    refresh_radar(db, now)
    set_odds(db, m, "pinnacle", {"1": 2.1, "X": 3.6, "2": 3.6}, closing=True)
    kickoff = db.get(Match, m).kickoff_at
    assert settle_radar(db, kickoff - timedelta(minutes=1)) == 0  # prima del via: niente
    assert settle_radar(db, kickoff + timedelta(hours=3)) == 1  # iniziata, risultato non ancora arrivato
    s = signals(db)[0]
    assert s.clv is not None and s.won is None
    match = db.get(Match, m)
    match.status, match.home_goals, match.away_goals = "finished", 1, 1
    db.commit()
    assert settle_radar(db, kickoff + timedelta(days=20)) == 0  # nessun CLV nuovo, ma l'esito arriva
    assert signals(db)[0].won is False


def test_secondary_signal_is_found_settled_and_counted_apart(seeded, db):  # noqa: F811
    mid = match_id(db, "Milan", "Inter")
    m = db.get(Match, mid)
    set_odds(db, mid, "pinnacle", {"over": 1.95, "under": 1.95}, market="COR9.5")
    set_odds(db, mid, "sisal", {"over": 2.20, "under": 1.65}, market="COR9.5")
    assert refresh_radar(db, m.kickoff_at - timedelta(days=1), ("sisal",)) == 1
    set_odds(db, mid, "pinnacle", {"over": 1.80, "under": 2.10}, closing=True, market="COR9.5")
    m.status, m.home_goals, m.away_goals = "finished", 1, 1
    m.home_corners, m.away_corners, m.home_yellow, m.away_yellow, m.home_red, m.away_red = 7, 5, 1, 2, 0, 0
    db.commit()
    settle_radar(db, m.kickoff_at + timedelta(hours=3))
    [signal] = signals(db)
    assert signal.market == "COR9.5" and signal.won is True  # 12 angoli
    assert signal.clv == pytest.approx(2.20 * shin([1.80, 2.10])[0] - 1, abs=1e-4)
    assert live_summary(db) is None  # i mercati principali non contano i secondari
    assert live_summary(db, secondary=True).n == 1
