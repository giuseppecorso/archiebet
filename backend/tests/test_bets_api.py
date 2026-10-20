from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.adapters.football_data import parse_csv
from app.auth.service import create_user
from app.ingest.football_data import import_matches
from app.models import Match, MatchStatus


def day(offset: int) -> str:
    return (datetime.now(UTC) + timedelta(days=offset)).strftime("%d/%m/%Y")


@pytest.fixture
def matches(db):
    csv = (
        "Div,Date,Time,HomeTeam,AwayTeam,AvgH,AvgD,AvgA,Avg>2.5,Avg<2.5\n"
        f"I1,{day(3)},14:00,Inter,Roma,1.90,3.50,4.20,1.80,2.00\n"
        f"I1,{day(3)},17:00,Milan,Lazio,2.10,3.30,3.60,1.90,1.90\n"
    )
    import_matches(db, parse_csv(csv), season="2026/27")
    return {m.home_team.name: m.id for m in db.scalars(select(Match))}


def bet_body(match_id, kind="real", stake="10", pick="1", odds="2.00"):
    return {"kind": kind, "stake": stake, "bookmaker": "Snai", "selections": [{"match_id": match_id, "market": "1X2", "pick": pick, "odds": odds}]}


def test_place_and_list_bet(logged_client, matches):
    r = logged_client.post("/api/bets", json={
        "kind": "real", "stake": "10", "bookmaker": "Snai",
        "selections": [
            {"match_id": matches["Inter"], "market": "1X2", "pick": "1", "odds": "1.95"},
            {"match_id": matches["Milan"], "market": "OU2.5", "pick": "over", "odds": "1.90"},
        ],
    })  # fmt: skip
    assert r.status_code == 201, r.text
    bet = r.json()["bet"]
    assert bet["total_odds"] == "3.7050" and bet["potential_payout"] == "37.05"
    assert [s["match"]["home"]["name"] for s in bet["selections"]] == ["Inter", "Milan"]
    assert r.json()["warnings"] == []

    listed = logged_client.get("/api/bets").json()
    assert [b["id"] for b in listed] == [bet["id"]]
    snap = logged_client.get(f"/api/bets/{bet['id']}/snapshot").json()
    assert set(snap["matches"]) == {str(matches["Inter"]), str(matches["Milan"])}
    assert snap["matches"][str(matches["Inter"])]["match"]["odds_1x2"] == {"1": 1.9, "X": 3.5, "2": 4.2}


def test_invalid_bet_messages(logged_client, matches):
    r = logged_client.post("/api/bets", json=bet_body(matches["Inter"], pick="over"))
    assert r.status_code == 422 and "non valido" in r.json()["detail"]
    r = logged_client.post("/api/bets", json=bet_body(matches["Inter"], odds="1.00"))
    assert r.status_code == 422  # validazione dei dati in ingresso


def test_bets_are_private(logged_client, client, db, matches):
    bet_id = logged_client.post("/api/bets", json=bet_body(matches["Inter"])).json()["bet"]["id"]
    logged_client.post("/api/auth/logout")
    create_user(db, "amico", "un-altra-password")
    client.post("/api/auth/login", json={"username": "amico", "password": "un-altra-password"})
    assert client.get("/api/bets").json() == []
    assert client.get(f"/api/bets/{bet_id}").status_code == 404
    assert client.delete(f"/api/bets/{bet_id}").status_code == 404


def test_budget_warning_on_real_bets(logged_client, matches):
    assert logged_client.put("/api/settings", json={"weekly_budget": "15", "monthly_budget": None, "bookmakers": ["Snai"]}).status_code == 200
    assert logged_client.post("/api/bets", json=bet_body(matches["Inter"], kind="simulated", stake="100")).json()["warnings"] == []
    assert logged_client.post("/api/bets", json=bet_body(matches["Inter"], stake="10")).json()["warnings"] == []
    warnings = logged_client.post("/api/bets", json=bet_body(matches["Milan"], stake="10")).json()["warnings"]
    assert len(warnings) == 1 and "20.00" in warnings[0]  # avviso, ma la giocata è registrata
    assert len(logged_client.get("/api/bets?kind=real").json()) == 2


def test_settings_validation(logged_client):
    assert logged_client.put("/api/settings", json={"bookmakers": ["BancoLotto"]}).status_code == 422
    s = logged_client.get("/api/settings").json()
    assert s["available_bookmakers"][0] == "Sisal" and s["weekly_budget"] is None


def test_summary_and_delete(logged_client, db, matches):
    first = logged_client.post("/api/bets", json=bet_body(matches["Inter"], odds="2.00")).json()["bet"]["id"]
    second = logged_client.post("/api/bets", json=bet_body(matches["Milan"], kind="simulated")).json()["bet"]["id"]
    assert logged_client.delete(f"/api/bets/{second}").status_code == 204

    inter = db.get(Match, matches["Inter"])
    inter.status, inter.home_goals, inter.away_goals = MatchStatus.FINISHED, 1, 0
    db.commit()
    summary = logged_client.get("/api/bets/summary?period=all").json()
    assert summary["real"]["won"] == 1 and summary["real"]["profit"] == "10.00"
    assert summary["simulated"]["bets"] == 0
    assert logged_client.delete(f"/api/bets/{first}").status_code == 409  # chiusa: non si cancella


def test_prefill(logged_client, matches):
    p = logged_client.get(f"/api/matches/{matches['Inter']}/prefill").json()
    assert p["odds"]["1X2"] == {"1": 1.9, "X": 3.5, "2": 4.2}
    assert p["odds"]["OU2.5"] == {"over": 1.8, "under": 2.0}
    assert p["markets"]["DC"] == ["1X", "X2", "12"]


def test_breakdown_endpoint(logged_client, db, matches):
    logged_client.post("/api/bets", json=bet_body(matches["Inter"], odds="2.00"))
    logged_client.post("/api/bets", json=bet_body(matches["Milan"], kind="simulated"))
    inter = db.get(Match, matches["Inter"])
    inter.status, inter.home_goals, inter.away_goals = MatchStatus.FINISHED, 2, 1
    db.commit()
    real = logged_client.get("/api/bets/breakdown?kind=real").json()
    assert [(g["label"], g["bets"], g["profit"]) for g in real["by_size"]] == [("Singole", 1, "10.00")]
    assert real["by_competition"][0]["label"] == "Serie A" and real["by_competition"][0]["hit_rate"] == 1.0
    assert real["habits"]["bets"] == 1 and real["habits"]["top_bookmaker"] == "Snai"
    simulated = logged_client.get("/api/bets/breakdown?kind=simulated").json()
    assert simulated["by_size"] == [] and simulated["habits"]["bets"] == 1  # aperta: solo abitudini


def test_live_match_and_hope_thermometer(logged_client, db, matches):
    from app.models import MatchLive

    inter = matches["Inter"]
    bet = logged_client.post("/api/bets", json=bet_body(inter, odds="1.95")).json()["bet"]
    before = logged_client.get(f"/api/bets/{bet['id']}").json()
    assert before["live"] is False and 0.4 < before["hope"] < 0.6  # Inter favorita dalla media di mercato

    db.add(MatchLive(match_id=inter, status="2H", minute=80, home_goals=2, away_goals=0, updated_at=datetime.now(UTC)))
    db.commit()
    during = logged_client.get(f"/api/bets/{bet['id']}").json()
    assert during["live"] is True and during["hope"] > 0.95  # 2-0 a dieci minuti dalla fine
    assert during["selections"][0]["probability"] == pytest.approx(during["hope"])
    live = logged_client.get("/api/matches?view=live").json()
    assert [m["id"] for g in live for m in g["matches"]] == [inter]
    assert live[0]["matches"][0]["live"] == {"status": "2H", "minute": 80, "home_goals": 2, "away_goals": 0}


def test_match_page_shows_live_probabilities(logged_client, db, matches):
    from app.models import MatchLive

    inter = matches["Inter"]
    assert logged_client.get(f"/api/matches/{inter}").json()["live_1x2"] is None  # non ancora iniziata
    db.add(MatchLive(match_id=inter, status="HT", minute=45, home_goals=0, away_goals=1, updated_at=datetime.now(UTC)))
    db.commit()
    live = logged_client.get(f"/api/matches/{inter}").json()["live_1x2"]
    assert sum(live.values()) == pytest.approx(1.0, abs=1e-6)
    assert live["2"] > live["1"]  # sotto 0-1 all'intervallo, anche da favorita
