from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.adapters.football_data import parse_csv
from app.ingest.football_data import import_matches
from app.models import Match

HEADER = "Div,Date,Time,HomeTeam,AwayTeam,FTHG,FTAG,HS,AS,AvgH,AvgD,AvgA,AvgCH,AvgCD,AvgCA\n"


def day(offset_days: int) -> str:
    return (datetime.now(UTC) + timedelta(days=offset_days)).strftime("%d/%m/%Y")


@pytest.fixture
def seeded(db):
    """Tre giornate giocate, una partita senza risultato da giorni, due in programma."""
    played = (
        HEADER
        + f"I1,{day(-21)},14:00,Inter,Milan,2,0,15,5,1.9,3.5,4.2,1.8,3.6,4.5\n"
        + f"I1,{day(-21)},14:00,Roma,Lazio,1,1,10,9,2.3,3.2,3.1,2.4,3.2,3.0\n"
        + f"I1,{day(-14)},14:00,Milan,Roma,0,1,8,12,2.1,3.3,3.5,,,\n"
        + f"I1,{day(-14)},14:00,Lazio,Inter,1,3,7,14,3.4,3.4,2.1,3.5,3.4,2.0\n"
        + f"I1,{day(-7)},14:00,Inter,Roma,1,1,11,8,1.7,3.8,4.8,1.75,3.7,4.6\n"
    )
    import_matches(db, parse_csv(played), season="2026/27")
    fixtures = (
        "Div,Date,Time,HomeTeam,AwayTeam,AvgH,AvgD,AvgA\n"
        + f"I1,{day(-3)},14:00,Lazio,Milan,2.5,3.2,2.9\n"  # risultato non ancora arrivato
        + f"I1,{day(3)},14:00,Milan,Inter,3.1,3.4,2.3\n"
        + f"I2,{day(4)},14:00,Palermo,Bari,2.1,3.1,3.7\n"
    )
    import_matches(db, parse_csv(fixtures), season="2026/27")
    return db


def match_id(db, home: str, away: str) -> int:
    for m in db.scalars(select(Match)):
        if (m.home_team.name, m.away_team.name) == (home, away):
            return m.id
    raise LookupError


def test_requires_login(client):
    assert client.get("/api/matches").status_code == 401
    assert client.get("/api/competitions").status_code == 401


def test_competitions(logged_client, seeded):
    codes = [c["code"] for c in logged_client.get("/api/competitions").json()]
    assert codes == ["ITA-A", "ITA-B", "ITA-C-A", "ITA-C-B", "ITA-C-C", "ENG-1", "ESP-1", "GER-1", "FRA-1"]  # Italia in testa


def test_upcoming_grouped_by_competition(logged_client, seeded):
    groups = logged_client.get("/api/matches?view=upcoming").json()
    assert [g["competition"]["code"] for g in groups] == ["ITA-A", "ITA-B"]
    [milan_inter] = groups[0]["matches"]
    assert (milan_inter["home"]["name"], milan_inter["away"]["name"], milan_inter["status"]) == ("Milan", "Inter", "scheduled")
    assert milan_inter["odds_1x2"] == {"1": 3.1, "X": 3.4, "2": 2.3}

    only_b = logged_client.get("/api/matches?view=upcoming&competitions=ITA-B").json()
    assert [g["competition"]["code"] for g in only_b] == ["ITA-B"]


def test_results_newest_first_with_closing_odds_and_awaiting(logged_client, seeded):
    [group] = logged_client.get("/api/matches?view=results").json()
    matches = group["matches"]
    assert matches[0]["status"] == "awaiting_result"  # Lazio-Milan, iniziata 3 giorni fa
    assert (matches[1]["home"]["name"], matches[1]["home_goals"], matches[1]["away_goals"]) == ("Inter", 1, 1)
    assert matches[1]["odds_1x2"] == {"1": 1.75, "X": 3.7, "2": 4.6}  # chiusura
    milan_roma = next(m for m in matches if m["home"]["name"] == "Milan")
    assert milan_roma["odds_1x2"] == {"1": 2.1, "X": 3.3, "2": 3.5}  # senza chiusura: apertura


def test_match_detail_uses_only_past_data(logged_client, seeded, db):
    detail = logged_client.get(f"/api/matches/{match_id(db, 'Milan', 'Inter')}").json()

    # Inter: V (Inter-Milan 2-0), V (Lazio-Inter 1-3), N (Inter-Roma 1-1) → dalla più recente
    assert [f["outcome"] for f in detail["away"]["form"]] == ["N", "V", "V"]
    assert detail["away"]["form"][1] == {**detail["away"]["form"][1], "opponent": "Lazio", "venue": "T", "score": "3-1"}
    assert detail["away"]["season"]["played"] == 3
    assert detail["away"]["season"]["points_per_game"] == 2.33
    assert detail["away"]["venue"]["played"] == 1  # Inter in trasferta: solo Lazio-Inter

    # Classifica prima della partita: Inter 7, Roma 5, Lazio 1, Milan 0
    table = [(row["team"]["name"], row["points"]) for row in detail["standings"]]
    assert table == [("Inter", 7), ("Roma", 5), ("Lazio", 1), ("Milan", 0)]

    assert [(h["home"]["name"], h["home_goals"]) for h in detail["head_to_head"]] == [("Inter", 2)]
    assert detail["match_stats"] is None
    assert detail["missing_results"] == 1  # Lazio-Milan, giocata 3 giorni fa, senza risultato
    avg = next(o for o in detail["odds"] if o["bookmaker"] == "market_avg" and o["market"] == "1X2")
    assert avg["opening"] == {"1": 3.1, "X": 3.4, "2": 2.3} and avg["closing"] == {}


def test_finished_match_has_stats_and_pre_match_table(logged_client, seeded, db):
    detail = logged_client.get(f"/api/matches/{match_id(db, 'Lazio', 'Inter')}").json()
    assert detail["match_stats"]["goals"] == [1, 3]
    assert detail["match_stats"]["shots"] == [7, 14]
    # La classifica è quella PRIMA della partita: dopo una sola giornata
    assert [row["played"] for row in detail["standings"]] == [1, 1, 1, 1]
    assert detail["missing_results"] == 0  # Lazio-Milan è successiva a questa partita


def test_unknown_match(logged_client, seeded):
    assert logged_client.get("/api/matches/99999").status_code == 404
