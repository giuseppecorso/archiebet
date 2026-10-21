"""Sfida contro Archie (D116)."""

import pytest

from app.betting.challenge import Settled, archie_pick, credits, outcome, score


def test_scoring():
    assert outcome(2, 1) == "1" and outcome(0, 0) == "X" and outcome(0, 3) == "2"
    assert credits(Settled("2", 4.0, "2")) == pytest.approx(30.0)
    assert credits(Settled("1", 1.5, "X")) == -10.0
    s = score([Settled("1", 2.0, "1"), Settled("X", 3.5, "1"), Settled("2", 5.0, "2")])
    assert (s.picks, s.correct, s.credits) == (3, 2, 40.0)
    assert s.hit_rate == pytest.approx(2 / 3)
    assert archie_pick({"1": 0.3, "X": 0.25, "2": 0.45}) == "2"


def test_fair_odds_make_random_picks_worth_zero_on_average():
    probs = {"1": 0.5, "X": 0.3, "2": 0.2}
    expected = sum(p_out * sum(credits(Settled(sel, 1 / probs[sel], out)) for sel in probs) for out, p_out in probs.items()) / 3
    assert expected == pytest.approx(0.0)


def test_play_api(logged_client, db):
    from datetime import UTC, datetime, timedelta
    from decimal import Decimal

    from app.models import Competition, Match, MatchOdds, Team

    comp = Competition(code="ITA-A", name="Serie A", country="Italia", tier=1)
    a, b = Team(name="Napoli", country="Italia"), Team(name="Roma", country="Italia")
    db.add_all([comp, a, b])
    db.flush()
    m = Match(competition_id=comp.id, season="2026/27", kickoff_at=datetime.now(UTC) + timedelta(days=2), kickoff_has_time=True, home_team_id=a.id, away_team_id=b.id)
    db.add(m)
    db.flush()
    for sel, price in (("1", "2.00"), ("X", "3.50"), ("2", "4.00")):
        db.add(MatchOdds(match_id=m.id, source="football-data", bookmaker="pinnacle", market="1X2", selection=sel, price=Decimal(price), is_closing=False))
    db.commit()
    assert [c["id"] for c in logged_client.get("/api/play/matches").json()] == [m.id]
    sim = logged_client.get(f"/api/play/simulate?match_id={m.id}&minute=60&home=1&away=0").json()
    assert sim["n"] == 10000 and sim["p_home"] > 0.6 and all(g["minute"] > 60 for g in sim["sample"])
    assert logged_client.post("/api/play/challenge", json={"match_id": m.id, "selection": "2"}).json() == {"ok": True}
    row = logged_client.get("/api/play/challenge?competition=ITA-A").json()["rows"][0]
    assert (row["my_pick"], row["archie_pick"], row["open"]) == ("2", "1", True)
    m.status, m.home_goals, m.away_goals = "finished", 0, 1
    db.commit()
    body = logged_client.get("/api/play/challenge?competition=ITA-A").json()
    standings = {s["name"]: s for s in body["standings"]}
    assert standings["giuse"]["credits"] > 20 and standings["Archie"]["credits"] == -10.0
    assert logged_client.post("/api/play/challenge", json={"match_id": m.id, "selection": "1"}).status_code == 409
