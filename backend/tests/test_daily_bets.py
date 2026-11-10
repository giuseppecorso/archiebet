"""D192: ogni schedina del Daily risulta giocata da ogni utente e finisce nelle statistiche."""

from datetime import UTC, datetime
from decimal import Decimal as D

import pytest
from sqlalchemy import select

from app.adapters.football_data import parse_csv
from app.auth.service import create_user
from app.betting.service import settle_open_bets
from app.forecast.daily_service import DAILY_STAKE, play_daily
from app.ingest.football_data import import_matches
from app.models import Bet, DailySlip, Match, MatchStatus

PUBLISHED = datetime(2026, 10, 17, 8, 0, tzinfo=UTC)


@pytest.fixture
def world(db):
    users = [create_user(db, "anna", "una-password-lunga"), create_user(db, "amico", "una-password-lunga")]
    csv = "Div,Date,Time,HomeTeam,AwayTeam\nI1,17/10/2026,14:00,Inter,Roma\nI1,17/10/2026,17:00,Milan,Lazio\nI1,17/10/2026,19:45,Napoli,Torino\n"
    import_matches(db, parse_csv(csv), season="2026/27")
    return users, {m.home_team.name: m for m in db.scalars(select(Match))}


def leg(m, market, sel, price):
    return {"match_id": m.id, "market": market, "selection": sel, "price": price, "p": 0.6, "status": "open"}


def slip(db, kind, legs):
    s = DailySlip(kind=kind, period=f"2026-10-17-{kind}", published_at=PUBLISHED, legs=legs, total_odds=1.0, win_probability=0.5, status="open")
    db.add(s)
    db.commit()
    return s


def test_every_user_plays_every_slip_once(db, world):
    users, m = world
    s = slip(db, "giorno", [leg(m["Inter"], "1X2", "1", 1.8), leg(m["Milan"], "OU2.5", "over", 1.7)])
    assert play_daily(db) == 2  # una multipla per ciascuno dei due utenti
    assert play_daily(db) == 0  # mai due volte
    bets = list(db.scalars(select(Bet)))
    assert {b.user_id for b in bets} == {u.id for u in users}
    b = bets[0]
    assert b.daily_slip_id == s.id and b.stake == DAILY_STAKE and b.total_odds == D("3.0600")
    assert b.placed_at.replace(tzinfo=UTC) == PUBLISHED and b.note == "Daily: La schedina del giorno"


def test_singles_become_one_bet_per_pick(db, world):
    _, m = world
    slip(db, "clv", [leg(m["Inter"], "1X2", "1", 2.1), leg(m["Milan"], "1X2", "2", 3.0)])
    play_daily(db)
    assert len(list(db.scalars(select(Bet)))) == 4  # 2 pronostici × 2 utenti


def test_system_slip_keeps_its_system(db, world):
    _, m = world
    teams = ["Inter", "Milan", "Napoli"]
    s = slip(db, "sistema", [leg(m[t], "1X2", "1", 2.0) for t in teams])  # 3 partite: per il "4 su 6" non bastano
    assert play_daily(db) == 0
    s.legs = [leg(m[t], "1X2", "1", 2.0) for t in teams] + [leg(m[t], "OU2.5", "over", 1.5) for t in teams]
    db.commit()  # stesse partite in due mercati: non succede davvero, serve solo a avere 6 pronostici
    played = play_daily(db)
    assert played == 2 and all(b.system == 4 for b in db.scalars(select(Bet)))


def test_played_slips_settle_with_the_results(db, world):
    _, m = world
    slip(db, "giorno", [leg(m["Inter"], "1X2", "1", 2.0)])
    play_daily(db)
    inter = m["Inter"]
    inter.status, inter.home_goals, inter.away_goals = MatchStatus.FINISHED, 2, 0
    db.commit()
    settle_open_bets(db)
    assert {(b.status, b.payout) for b in db.scalars(select(Bet))} == {("won", D("2.00"))}


def test_daily_bets_give_no_coins(logged_client, db, world):
    _, m = world
    slip(db, "giorno", [leg(m["Inter"], "1X2", "1", 2.0)])
    play_daily(db)
    inter = m["Inter"]
    inter.status, inter.home_goals, inter.away_goals = MatchStatus.FINISHED, 1, 0
    db.commit()
    settle_open_bets(db)
    assert logged_client.get("/api/coins").json()["balance"] == 0  # previsione di Archie, non dell'utente
