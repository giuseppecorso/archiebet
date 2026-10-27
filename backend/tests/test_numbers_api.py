"""Numeri attesi della pagina partita: tiri, angoli, cartellini con quote giuste (D109)."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from app.models import Competition, Match, MatchOdds, Team


def test_numbers_endpoint(logged_client, db):
    comp = Competition(code="ITA-A", name="Serie A", country="Italia", tier=1)
    teams = [Team(name=f"T{i}", country="Italia") for i in range(4)]
    db.add_all([comp, *teams])
    db.flush()
    t0 = datetime(2026, 8, 20, tzinfo=UTC)
    n = 0
    for season, start in (("2025/26", t0 - timedelta(days=365)), ("2026/27", t0)):
        pairs = [(h, a) for h in range(4) for a in range(4) if h != a and (h, a) != (0, 1)]  # 0-1 è la partita da giocare
        for rnd in range(len(pairs) // 2):
            for h, a in pairs[2 * rnd : 2 * rnd + 2]:
                n += 1
                db.add(Match(competition_id=comp.id, season=season, kickoff_at=start + timedelta(days=7 * rnd, hours=n % 4), kickoff_has_time=True,
                             home_team_id=teams[h].id, away_team_id=teams[a].id, status="finished", home_goals=1, away_goals=0,
                             home_shots=14, away_shots=9, home_corners=6 if h == 0 else 4, away_corners=4, home_yellow=2, away_yellow=2, home_red=0, away_red=0))  # fmt: skip
    upcoming = Match(competition_id=comp.id, season="2026/27", kickoff_at=t0 + timedelta(days=60), kickoff_has_time=True,
                     home_team_id=teams[0].id, away_team_id=teams[1].id)  # fmt: skip
    db.add(upcoming)
    db.flush()
    db.add_all([MatchOdds(match_id=upcoming.id, source="oddspapi", bookmaker="sisal", market="COR9.5", selection=s, price=Decimal(p), is_closing=False)
                for s, p in (("over", "1.90"), ("under", "1.85"))])  # fmt: skip
    db.commit()
    body = logged_client.get(f"/api/picks/match/{upcoming.id}/numbers").json()
    stats = {b["stat"]: b for b in body}
    assert set(stats) == {"shots", "corners", "cards"}
    corners = stats["corners"]
    assert corners["home"] > corners["away"]
    line = next(x for x in corners["lines"] if x["side"] == "totale" and x["line"] == 9.5)
    assert line["offers"] == {"Altri bookmakers": {"over": 1.9, "under": 1.85}}  # i bookmaker italiani non si nominano (D154)
    assert abs(1 / line["fair_over"] + 1 / line["fair_under"] - 1) < 1e-9


def test_players_endpoint_without_api_football_source(logged_client, db):
    comp = Competition(code="ITA-C-A", name="Serie C", country="Italia", tier=3)
    a, b = Team(name="A", country="Italia"), Team(name="B", country="Italia")
    db.add_all([comp, a, b])
    db.flush()
    m = Match(competition_id=comp.id, season="2026/27", kickoff_at=datetime(2026, 11, 1, tzinfo=UTC), kickoff_has_time=True, home_team_id=a.id, away_team_id=b.id)
    db.add(m)
    db.commit()
    assert logged_client.get(f"/api/picks/match/{m.id}/players").json() == []
    assert logged_client.get(f"/api/picks/match/{m.id}/numbers").json() == []  # Serie C: niente statistiche


def test_news_absences_until_the_player_is_back():
    from types import SimpleNamespace as F

    from app.api.picks import news_absences

    t = datetime(2026, 10, 1, tzinfo=UTC)
    facts = [F(player="Paulo Dybala", kind="assente", detail="infortunio", published_at=t),
             F(player="Vergara", kind="assente", detail="fuori", published_at=t),
             F(player="Vergara", kind="rientro", detail="torna", published_at=t + timedelta(days=1)),
             F(player=None, kind="clima_negativo", detail="x", published_at=t)]  # fmt: skip
    assert news_absences(facts) == {"dybala": "infortunio"}
