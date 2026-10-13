"""Radar dal vivo: segnali salvati prima del calcio d'inizio, prima quota bloccata, CLV con la chiusura."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import delete, select

from app.forecast.radar_service import live_summary, refresh_radar, settle_radar
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
        set_odds(db, m, "pinnacle", {"1": 2.0, "X": 3.6, "2": 4.0})  # giusta sul 2: 0,2432
        set_odds(db, m, "bet365", {"1": 1.9, "X": 3.4, "2": 4.4})  # +7,0%
    now = datetime.now(UTC)
    assert refresh_radar(db, now) == 1  # Lazio-Milan è già iniziata
    [s] = signals(db)
    assert (s.match_id, s.market, s.selection, s.bookmaker, s.price, s.fair_source) == (upcoming, "1X2", "2", "bet365", 4.4, "pinnacle")
    assert s.value == pytest.approx(0.25 / (0.5 + 1 / 3.6 + 0.25) * 4.4 - 1, abs=1e-5)
    assert s.latest_price == 4.4 and s.clv is None


def test_first_detection_is_locked_latest_follows_odds(seeded, db):  # noqa: F811
    m = match_id(db, "Milan", "Inter")
    set_odds(db, m, "pinnacle", {"1": 2.0, "X": 3.6, "2": 4.0})
    set_odds(db, m, "bet365", {"1": 1.9, "X": 3.4, "2": 4.4})
    now = datetime.now(UTC)
    refresh_radar(db, now)
    set_odds(db, m, "bet365", {"1": 1.9, "X": 3.4, "2": 3.9})  # la quota scende: niente più valore
    assert refresh_radar(db, now + timedelta(hours=6)) == 0
    [s] = signals(db)
    assert s.price == 4.4  # la giocata simulata resta quella
    assert s.latest_price == 3.9 and s.latest_value < 0
    set_odds(db, m, "bet365", {"1": 1.9, "X": 3.4})  # quota del 2 sparita
    refresh_radar(db, now + timedelta(hours=12))
    assert signals(db)[0].latest_price is None


def test_settle_with_closing_reference_and_summary(seeded, db):  # noqa: F811
    m = match_id(db, "Milan", "Inter")
    set_odds(db, m, "pinnacle", {"1": 2.0, "X": 3.6, "2": 4.0})
    set_odds(db, m, "bet365", {"1": 1.9, "X": 3.4, "2": 4.4})
    refresh_radar(db, datetime.now(UTC))
    assert settle_radar(db) == 0  # partita non ancora giocata

    match = db.get(Match, m)
    match.status, match.home_goals, match.away_goals = "finished", 0, 2
    db.commit()
    assert settle_radar(db) == 0  # chiusura non ancora arrivata
    assert signals(db)[0].won is True  # l'esito invece si sa già

    set_odds(db, m, "betfair_ex", {"1": 2.2, "X": 3.6, "2": 3.6}, closing=True)  # niente Pinnacle: Betfair (D48)
    assert settle_radar(db) == 1
    s = signals(db)[0]
    fair_away = (1 / 3.6) / (1 / 2.2 + 2 / 3.6)
    assert s.closing_source == "betfair_ex"
    assert s.clv == pytest.approx(4.4 * fair_away - 1, abs=1e-5)
    summary = live_summary(db)
    assert summary.n == 1 and summary.mean_clv == pytest.approx(s.clv)
    assert summary.roi == pytest.approx(3.4)  # vinta a 4,4
    assert settle_radar(db) == 0  # già chiuso


def test_radar_api_lists_signals_and_live_progress(logged_client, seeded, db):  # noqa: F811
    m = match_id(db, "Milan", "Inter")
    set_odds(db, m, "pinnacle", {"1": 2.0, "X": 3.6, "2": 4.0})
    set_odds(db, m, "sisal", {"1": 1.9, "X": 3.4, "2": 4.4})
    refresh_radar(db, datetime.now(UTC))
    body = logged_client.get("/api/radar").json()
    [s] = body["upcoming"]
    assert (s["home"]["name"], s["selection"], s["bookmaker"], s["fair_source"]) == ("Milan", "2", "Sisal", "Pinnacle")
    assert s["latest_price"] == 4.4 and s["suspicious"] is False
    assert body["recent"] == []
    assert body["live"] == {"n": 0, "target": 300, "mean_clv": None, "clv_std_error": None,
                            "share_positive": None, "roi": None, "verdict": "in prova"}
    assert "Sisal" in body["playable"] and body["threshold"] == 0.02
