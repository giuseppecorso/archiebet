from datetime import UTC, datetime, timedelta

from app.forecast.cup_model import (
    R,
    cup_test,
    from_fixtures,
    improvement,
    joint_fit,
    league_games,
    outcome,
    passed,
    probabilities,
)
from app.forecast.history_sim import Estimate

START = datetime(2023, 8, 1, tzinfo=UTC)


def _season(league: list[int], first_id: int, start: datetime, goals) -> list[R]:
    """Andata e ritorno tra le squadre del campionato, una partita al giorno."""
    out, day = [], 0
    for h in league:
        for a in league:
            if h != a:
                hg, ag = goals(h, a)
                out.append(R(first_id + day, start + timedelta(days=day), 2023, h, a, hg, ag, cup=False))
                day += 1
    return out


def _two_leagues():
    strong, weak = [1, 2, 3, 4], [11, 12, 13, 14]
    even = lambda h, a: (1 + (h + a) % 2, 1)  # noqa: E731 - campionati equilibrati al loro interno
    games = _season(strong, 0, START, even) + _season(weak, 100, START, even)
    cups = []
    for k in range(12):  # le squadre del campionato forte vincono 3-0 in coppa
        h, a = strong[k % 4], weak[k % 4]
        home_first = k % 2 == 0
        cups.append(R(500 + k, START + timedelta(days=20 + k), 2023, h if home_first else a, a if home_first else h,
                      3 if home_first else 0, 0 if home_first else 3, cup=True))  # fmt: skip
    return games, cups


def test_linked_model_learns_league_strength():
    games, cups = _two_leagues()
    when = START + timedelta(days=60)
    unlinked = joint_fit(games + cups, when, with_cups=False)
    linked = joint_fit(games + cups, when, with_cups=True)
    # gol attesi in casa della squadra forte contro quella debole, e viceversa
    assert abs(unlinked.expected_goals(1, 11)[0] - unlinked.expected_goals(11, 1)[0]) < 0.3  # scollegati: valgono uguale
    assert linked.expected_goals(1, 11)[0] > linked.expected_goals(11, 1)[0] + 0.5  # collegati: il campionato forte vale di più


def test_league_games_counts_only_league_matches_in_window():
    games, cups = _two_leagues()
    counts = league_games(games + cups, START + timedelta(days=60))
    assert counts[1] == 6 and counts[11] == 6
    assert league_games(games, START)[1] == 0  # niente dal futuro


def test_probabilities_and_outcomes():
    p = probabilities(1.6, 1.1, -0.05)
    for market in p.values():
        assert abs(sum(market.values()) - 1) < 1e-9
    g = R(1, START, 2023, 1, 2, 2, 0, cup=True)
    assert [outcome(m, g) for m in ("1X2", "OU2.5", "GG", "TGH0.5", "TGA0.5")] == ["1", "under", "no", "over", "under"]


def test_cup_test_skips_teams_with_few_league_games():
    games, cups = _two_leagues()
    assert cup_test(games + cups, [2023], log=lambda _: None) == []  # 6 partite di campionato a testa: meno di 10


def test_pass_rule():
    assert passed(Estimate(0.03, 0.01, 100, 100), Estimate(0.025, 0.012, 50, 50))
    assert not passed(Estimate(0.03, 0.01, 100, 100), Estimate(0.02, 0.012, 50, 50))
    assert improvement([], [2023]) is None


class _F:
    def __init__(self, id, day, status="finished", short="FT", hg=1, ag=0):
        from app.adapters.api_football import AFTeam

        self.id, self.kickoff_at, self.season, self.status, self.status_short = id, START + timedelta(days=day), 2023, status, short
        self.home, self.away, self.home_goals, self.away_goals = AFTeam(1, "a"), AFTeam(2, "b"), hg, ag


def test_from_fixtures_marks_the_final_and_skips_awarded():
    rows = from_fixtures([_F(1, 0), _F(2, 5), _F(3, 9, short="AWD"), _F(4, 12, status="scheduled", hg=None)], cup=True)
    assert [(r.id, r.final) for r in rows] == [(1, False), (2, True)]


def test_cup_fit_from_database_uses_tested_leagues_and_cups(db):
    from app.forecast.study_service import cup_fit
    from app.ingest.teams import ensure_competitions
    from app.models import Match, MatchStatus, Team

    comps = ensure_competitions(db)
    teams = {name: Team(name=name, country=country) for name, country in
             [("Inter", "Italia"), ("Roma", "Italia"), ("Porto", "Portogallo"), ("Braga", "Portogallo"), ("Exeter", "Inghilterra")]}  # fmt: skip
    db.add_all(teams.values())
    db.flush()
    now = datetime(2026, 10, 1, tzinfo=UTC)

    def played(code, home, away, days_ago, hg=1, ag=0, season="2026/27"):  # una sola sfida per stagione: si cambia stagione
        db.add(Match(competition_id=comps[code].id, season=season, home_team_id=teams[home].id, away_team_id=teams[away].id,
                     kickoff_at=now - timedelta(days=days_ago), status=MatchStatus.FINISHED, home_goals=hg, away_goals=ag))  # fmt: skip

    for k in range(6):
        played("ITA-A", "Inter", "Roma", 10 + 2 * k, season=f"20{20 + k}/{21 + k}")
        played("POR-1", "Porto", "Braga", 11 + 2 * k, season=f"20{20 + k}/{21 + k}")
    played("EU-CL", "Inter", "Porto", 5, 2, 0)
    played("ENG-3", "Exeter", "Roma", 4)  # serie minore: fuori dal modello delle coppe (non provata in D146)
    db.commit()
    fit, counts = cup_fit(db, now, "2026/27")
    assert fit.has_team(teams["Inter"].id) and fit.has_team(teams["Porto"].id) and not fit.has_team(teams["Exeter"].id)
    assert counts[teams["Inter"].id] == 6  # la partita di coppa non conta come campionato
