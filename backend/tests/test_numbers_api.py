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
    assert line["offers"] == {"Sisal": {"over": 1.9, "under": 1.85}}
    assert abs(1 / line["fair_over"] + 1 / line["fair_under"] - 1) < 1e-9
