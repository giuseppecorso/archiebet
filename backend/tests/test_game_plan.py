"""Piano partita live (D124)."""

import pytest

from app.forecast import game_plan as gp
from app.forecast.live import outcome_probabilities
from app.forecast.radar import required_value


def test_min_odds_meets_d72_threshold():
    m = gp.min_odds(2.0)
    assert m > 2.0 and (m / 2.0 - 1) == pytest.approx(required_value(m), abs=0.002)
    assert gp.min_odds(4.5) is None


def test_plan_states_consistent_with_engine():
    states = gp.plan((1.5, 1.1))
    first = states[0]
    assert (first.minute, first.home_goals, first.away_goals) == (30, 0, 0)
    lines = {(x.market, x.selection): x for x in first.lines}
    p = outcome_probabilities(*first.remaining, 0, 0)
    assert lines[("1X2", "1")].probability == pytest.approx(p["1"])
    assert lines[("OU2.5", "under")].probability == pytest.approx(1 - p["over"])
    assert sum(lines[("1X2", s)].probability for s in "1X2") == pytest.approx(1.0)


def test_leading_late_means_short_odds():
    by_state = {(s.minute, s.home_goals, s.away_goals): {(x.market, x.selection): x for x in s.lines} for s in gp.plan((1.4, 1.2))}
    assert by_state[(75, 1, 0)][("1X2", "1")].probability > by_state[(45, 1, 0)][("1X2", "1")].probability > 0.6
    assert by_state[(75, 0, 0)][("OU2.5", "under")].probability > 0.8
    # con 1-1 al 60' "Goal" è già uscito: non compare
    assert ("GG", "yes") not in by_state[(60, 1, 1)]


def test_plan_and_lineups_api(logged_client, db):
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
        db.add(MatchOdds(match_id=m.id, source="oddspapi", bookmaker="pinnacle", market="1X2", selection=sel, price=Decimal(price), is_closing=False))
    db.commit()
    states = logged_client.get(f"/api/picks/match/{m.id}/plan").json()
    assert len(states) == len(gp.STATES) and states[0]["minute"] == 30
    home = next(x for x in states[0]["lines"] if x["selection"] == "1")
    assert home["min_odds"] > home["fair_odds"]
    assert logged_client.get(f"/api/picks/match/{m.id}/lineups").json() == []  # senza dati API-Football
    assert logged_client.get("/api/picks/match/999999/plan").status_code == 404
