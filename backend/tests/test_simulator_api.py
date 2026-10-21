"""Simulatore partita (D115)."""


def test_simulator_api(logged_client, db):
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
