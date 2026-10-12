import pytest

from app.adapters.football_data import parse_csv
from app.ingest.football_data import import_matches

HEADER = "Div,Date,HomeTeam,AwayTeam,FTHG,FTAG\n"


@pytest.fixture
def seeded(db):
    """Due stagioni: la Lazio in A nel 2023/24, in B nel 2024/25 (per vedere la storia su più categorie)."""
    import_matches(db, parse_csv(HEADER + "I1,01/09/23,Inter,Lazio,2,0\nI1,08/09/23,Lazio,Roma,1,1\nI1,15/09/23,Roma,Inter,0,3\n"), season="2023/24")
    import_matches(db, parse_csv(HEADER + "I2,01/09/24,Lazio,Bari,3,0\nI2,08/09/24,Bari,Pisa,0,0\n"), season="2024/25")
    return db


def team_id(client, name):
    return next(t["id"] for t in client.get("/api/lab/teams").json() if t["name"] == name)


def test_requires_login(client):
    assert client.get("/api/lab/competitions").status_code == 401


def test_competitions_list_only_those_with_matches(logged_client, seeded):
    data = logged_client.get("/api/lab/competitions").json()
    assert [(c["competition"]["code"], [s["season"] for s in c["seasons"]]) for c in data] == [
        ("ITA-A", ["2023/24"]),
        ("ITA-B", ["2024/25"]),
    ]
    assert data[0]["seasons"][0] == {"season": "2023/24", "matches": 3, "finished": 3, "pending": 0, "cancelled": 0}


def test_season_detail(logged_client, seeded):
    d = logged_client.get("/api/lab/competitions/ITA-A/seasons/2023-24").json()
    assert d["season"] == "2023/24" and d["finished"] == 3
    assert d["summary"]["home_win"] == 0.333 and d["summary"]["draw"] == 0.333 and d["summary"]["away_win"] == 0.333
    assert d["summary"]["goals_per_match"] == 2.33  # 7 gol in 3 partite
    # Lazio e Roma a 1 punto, scontro diretto 1-1: decide la differenza reti (Lazio -2, Roma -3)
    assert [(r["team"]["name"], r["points"]) for r in d["standings"]] == [("Inter", 6), ("Lazio", 1), ("Roma", 1)]


def test_unknown_season_and_competition(logged_client, seeded):
    assert logged_client.get("/api/lab/competitions/ITA-A/seasons/1990-91").status_code == 404
    assert logged_client.get("/api/lab/competitions/XYZ/seasons/2023-24").status_code == 404


def test_trend_oldest_first(logged_client, seeded):
    import_matches(seeded, parse_csv(HEADER + "I1,01/09/22,Inter,Roma,1,0\n"), season="2022/23")
    trend = logged_client.get("/api/lab/competitions/ITA-A/trend").json()
    assert [t["season"] for t in trend] == ["2022/23", "2023/24"]
    assert trend[0]["summary"]["matches"] == 1


def test_team_search(logged_client, seeded):
    found = logged_client.get("/api/lab/teams?q=laz").json()
    assert found == [{"id": found[0]["id"], "name": "Lazio", "last_season": "2024/25", "last_competition": "Serie B"}]


def test_team_history_across_competitions(logged_client, seeded):
    lazio = team_id(logged_client, "Lazio")
    history = logged_client.get(f"/api/lab/teams/{lazio}").json()
    rows = [(s["season"], s["competition"]["code"], s["rank"], s["teams"], s["points"]) for s in history["seasons"]]
    assert rows == [
        ("2024/25", "ITA-B", 1, 3, 3),  # prima in B
        ("2023/24", "ITA-A", 2, 3, 1),  # seconda in A (vedi test_season_detail)
    ]
    assert all(s["complete"] for s in history["seasons"])


def test_team_matches_of_a_season(logged_client, seeded):
    lazio = team_id(logged_client, "Lazio")
    games = logged_client.get(f"/api/lab/teams/{lazio}/matches?season=2023-24").json()
    assert [(g["home"]["name"], g["away"]["name"]) for g in games] == [("Inter", "Lazio"), ("Lazio", "Roma")]
    assert logged_client.get("/api/lab/teams/99999").status_code == 404


def test_cancelled_matches_do_not_make_a_season_in_progress(logged_client, seeded):
    from sqlalchemy import select

    from app.models import Match, MatchStatus

    # Come Taranto e Turris nel 2024/25: partite annullate dopo un'esclusione
    match = seeded.scalar(select(Match).where(Match.season == "2024/25").order_by(Match.id.desc()))
    match.status = MatchStatus.CANCELLED
    match.home_goals = match.away_goals = None
    seeded.commit()
    d = logged_client.get("/api/lab/competitions/ITA-B/seasons/2024-25").json()
    assert (d["matches"], d["finished"], d["pending"], d["cancelled"]) == (2, 1, 0, 1)
    lazio = team_id(logged_client, "Lazio")
    assert logged_client.get(f"/api/lab/teams/{lazio}").json()["seasons"][0]["complete"] is True

    # Una partita ancora da giocare invece sì
    match.status = MatchStatus.SCHEDULED
    seeded.commit()
    assert logged_client.get("/api/lab/competitions/ITA-B/seasons/2024-25").json()["pending"] == 1
    assert logged_client.get(f"/api/lab/teams/{lazio}").json()["seasons"][0]["complete"] is False
