"""API-Football: lettura delle risposte (struttura copiata da una risposta reale), freni, import."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select

from app.adapters.api_football import (
    ApiFootballAdapter,
    ApiFootballError,
    QuotaExhausted,
    map_status,
    parse_fixtures,
    parse_matchday,
)
from app.adapters.cache import FileCache
from app.adapters.football_data import parse_csv
from app.ingest.api_football import import_fixtures, sync_api_football
from app.ingest.football_data import import_matches
from app.ingest.teams import normalize_team_name, tidy_teams
from app.models import Match, MatchSource, Team


def fixture(fid, home, away, date="2022-09-04T15:30:00+00:00", status="FT", goals=(3, 0), ht=(3, 0), rnd="Girone C - 1", league=943, season=2022):
    return {
        "fixture": {
            "id": fid, "referee": "V. Crezzini", "timezone": "UTC", "date": date,
            "venue": {"id": 945, "name": "Stadio Ettore Mannucci", "city": "Pontedera"},
            "status": {"long": "", "short": status, "elapsed": 90},
        },
        "league": {"id": league, "season": season, "round": rnd},
        "teams": {"home": {"id": home[0], "name": home[1]}, "away": {"id": away[0], "name": away[1]}},
        "goals": {"home": goals[0], "away": goals[1]},
        "score": {"halftime": {"home": ht[0], "away": ht[1]}},
    }  # fmt: skip


def body(*fixtures):
    return {"errors": [], "results": len(fixtures), "response": list(fixtures)}


def count(db, model):
    return db.scalar(select(func.count()).select_from(model))


def test_status_and_matchday():
    assert [map_status(s) for s in ("FT", "AET", "PEN", "AWD", "NS", "1H", "PST", "CANC")] == [
        "finished", "finished", "finished", "finished", "scheduled", "scheduled", "postponed", "cancelled",
    ]  # fmt: skip
    assert parse_matchday("Girone C - 12") == 12
    assert parse_matchday("Regular Season - 7") == 7
    assert parse_matchday("Promotion - Play-offs - Semi-finals") is None
    assert parse_matchday(None) is None


def test_parse_fixture():
    [f] = parse_fixtures(body(fixture(952792, (882, "Guidonia Montecelio 1937"), (9539, "Audace Cerignola"))))
    assert f.id == 952792 and f.league_id == 943 and f.season == 2022
    assert f.kickoff_at == datetime(2022, 9, 4, 15, 30, tzinfo=UTC)
    assert (f.status, f.matchday, f.home_goals, f.away_goals, f.ht_home_goals) == ("finished", 1, 3, 0, 3)
    assert (f.venue_name, f.venue_city) == ("Stadio Ettore Mannucci", "Pontedera")


def test_not_started_has_no_goals():
    [f] = parse_fixtures(body(fixture(1, (1, "A"), (2, "B"), status="NS", goals=(None, None), ht=(None, None))))
    assert f.status == "scheduled" and f.home_goals is None


def test_normalize_team_names():
    assert normalize_team_name("SS Monopoli 1966") == "monopoli"
    assert normalize_team_name("FeralpiSalò") == "feralpisalo"
    assert normalize_team_name("US Catanzaro 1929") == "catanzaro"
    assert normalize_team_name("Südtirol") == normalize_team_name("Sudtirol")
    assert normalize_team_name("Hellas Verona") == normalize_team_name("Verona")
    assert normalize_team_name("Juventus U23") != normalize_team_name("Juventus")
    assert normalize_team_name("Milan Futuro") != normalize_team_name("Milan")


class FakeApi:
    def __init__(self, responses, remaining=90):
        self.responses = list(responses)
        self.calls = []
        self.remaining = remaining

    def __call__(self, url, params, headers):
        assert headers == {"x-apisports-key": "chiave-test"}
        self.calls.append((url, params))
        self.remaining -= 1
        return 200, {"x-ratelimit-requests-remaining": str(self.remaining)}, self.responses.pop(0)


def adapter_with(tmp_path, api, **kwargs):
    return ApiFootballAdapter(FileCache(tmp_path, "api-football"), "chiave-test", http_get=api, **kwargs)


def test_adapter_waits_between_calls(tmp_path):
    waits = []
    now = [100.0]
    api = FakeApi([body(), body()])
    adapter = adapter_with(tmp_path, api, sleep=waits.append, clock=lambda: now[0])
    adapter.fixtures(943, 2022, timedelta(days=1))
    now[0] += 1.0
    adapter.fixtures(942, 2022, timedelta(days=1))
    assert waits == [pytest.approx(5.5)]  # 6.5 secondi tra due chiamate, 1 già passato
    assert adapter.remaining_today == 88


def test_plan_error_is_raised_and_not_cached(tmp_path):
    error = {"errors": {"plan": "Free plans do not have access to this season, try from 2022 to 2024."}, "response": []}
    api = FakeApi([error, body()])
    adapter = adapter_with(tmp_path, api, sleep=lambda _: None)
    with pytest.raises(ApiFootballError, match="Free plans"):
        adapter.fixtures(943, 2026, timedelta(hours=6))
    assert adapter.fixtures(943, 2026, timedelta(hours=6)) == []  # ripete la chiamata: l'errore non era in cache
    assert len(api.calls) == 2


def test_quota_reserve_stops_calls(tmp_path):
    api = FakeApi([body(), body()], remaining=11)
    adapter = adapter_with(tmp_path, api, sleep=lambda _: None, daily_reserve=10)
    adapter.fixtures(943, 2022, timedelta(days=1))  # ne restano 10
    with pytest.raises(QuotaExhausted):
        adapter.fixtures(942, 2022, timedelta(days=1))
    assert len(api.calls) == 1


def test_import_creates_serie_c_matches_with_links(db):
    fixtures = parse_fixtures(body(
        fixture(1, (882, "Guidonia Montecelio 1937"), (9539, "Audace Cerignola")),
        fixture(2, (9539, "Audace Cerignola"), (882, "Guidonia Montecelio 1937"), date="2023-01-15T13:30:00+00:00",
                goals=(1, 1), ht=(0, 1), rnd="Girone C - 20"),
    ))  # fmt: skip
    report = import_fixtures(db, fixtures)
    assert (report.created, report.updated) == (2, 0)
    match = db.scalar(select(Match).where(Match.matchday == 20))
    assert match.competition.code == "ITA-C-C" and match.season == "2022/23"
    assert (match.home_team.name, match.home_goals, match.ht_away_goals) == ("Audace Cerignola", 1, 1)
    assert match.venue_city == "Pontedera"
    assert count(db, MatchSource) == 2 and count(db, Team) == 2

    again = import_fixtures(db, fixtures)
    assert (again.created, again.updated) == (0, 2)
    assert count(db, Match) == 2


def test_renamed_team_stays_the_same_team(db):
    import_fixtures(db, parse_fixtures(body(fixture(1, (882, "Monterosi Tuscia"), (9539, "Audace Cerignola")))))
    import_fixtures(db, parse_fixtures(body(fixture(2, (882, "Guidonia Montecelio 1937"), (9539, "Audace Cerignola"), season=2024))))
    assert count(db, Team) == 2  # stesso id 882: stessa squadra anche col nome nuovo


def test_team_shared_with_football_data(db):
    csv = "Div,Date,HomeTeam,AwayTeam,FTHG,FTAG\nI2,15/09/2024,Catanzaro,Sudtirol,1,0\n"
    import_matches(db, parse_csv(csv), season="2024/25")
    import_fixtures(db, parse_fixtures(body(fixture(9, (1, "US Catanzaro 1929"), (2, "Südtirol"), league=943))))
    assert count(db, Team) == 2  # riconosciute come le stesse squadre di football-data



def test_foreign_teams_are_matched_in_their_country(db):
    csv = "Div,Date,HomeTeam,AwayTeam,FTHG,FTAG\nSP2,15/09/2025,Sociedad B,Celta B,1,0\n"
    import_matches(db, parse_csv(csv), season="2025/26")
    import_fixtures(db, parse_fixtures(body(fixture(7, (9585, "Real Sociedad II"), (9571, "Celta de Vigo II"), league=141, season=2025))))
    assert count(db, Team) == 2  # stesse squadre di football-data, cercate tra quelle spagnole
    import_fixtures(db, parse_fixtures(body(fixture(8, (50, "Manchester City"), (49, "Chelsea"), league=39, season=2025))))
    assert {t.country for t in db.scalars(select(Team).where(Team.name.in_(["Manchester City", "Chelsea"])))} == {"Inghilterra"}

def test_sync_skips_seasons_outside_plan_and_reports(db, tmp_path):
    plan_error = {"errors": {"plan": "Free plans do not have access to this season"}, "response": []}
    api = FakeApi([body(fixture(1, (1, "A"), (2, "B"))), plan_error])
    adapter = adapter_with(tmp_path, api, sleep=lambda _: None)
    lines = []
    sync_api_football(db, adapter, leagues=[943], seasons=[2022, 2026], now=datetime(2026, 10, 11, tzinfo=UTC), log=lines.append)
    assert count(db, Match) == 1
    assert any("saltato" in line and "Free plans" in line for line in lines)


def test_tidy_teams_merges_refounded_clubs_and_renames(db):
    csv = "Div,Date,HomeTeam,AwayTeam,FTHG,FTAG\nI2,15/09/2020,Vicenza,Pisa,1,0\n"
    import_matches(db, parse_csv(csv), season="2020/21")
    # Squadre create prima che esistessero le regole: simuliamo nomi "grezzi" già salvati
    db.add_all([Team(name="Vicenza Virtus", country="Italia"), Team(name="Milan II", country="Italia")])
    db.commit()
    vicenza_virtus = db.scalar(select(Team).where(Team.name == "Vicenza Virtus"))
    db.add(Match(competition_id=db.scalar(select(Match.competition_id)), season="2023/24", home_team_id=vicenza_virtus.id,
                 away_team_id=db.scalar(select(Team.id).where(Team.name == "Pisa")), kickoff_at=datetime(2023, 9, 1, tzinfo=UTC)))
    db.commit()

    assert tidy_teams(db, log=lambda _: None) == 2
    names = sorted(db.scalars(select(Team.name)))
    assert names == ["Milan Futuro", "Pisa", "Vicenza"]
    vicenza = db.scalar(select(Team).where(Team.name == "Vicenza"))
    assert db.scalar(select(func.count()).select_from(Match).where(Match.home_team_id == vicenza.id)) == 2
    assert tidy_teams(db, log=lambda _: None) == 0  # una seconda volta non cambia nulla


def test_new_teams_get_italian_display_names(db):
    import_fixtures(db, parse_fixtures(body(fixture(1, (100, "Atalanta II"), (101, "SS Monopoli")))))
    assert sorted(db.scalars(select(Team.name))) == ["Atalanta U23", "Monopoli"]


def test_cup_teams_keep_their_country_and_known_teams_are_reused(db):
    import_fixtures(db, parse_fixtures(body(fixture(1, (505, "Inter"), (489, "AC Milan"), league=135, season=2026))))
    cup = parse_fixtures(body(fixture(2, (505, "Inter"), (211, "Benfica"), league=2, season=2026, rnd="League Stage - 1")))
    assert import_fixtures(db, cup).skipped == 1  # senza il paese di Benfica non si crea nulla
    report = import_fixtures(db, cup, {505: "Italy", 211: "Portugal"})
    assert report.created == 1
    teams = {t.name: t.country for t in db.scalars(select(Team))}
    assert teams["Inter"] == "Italia" and teams["Benfica"] == "Portugal"
    assert count(db, Team) == 3  # Inter è la stessa della Serie A


def test_cup_rematch_in_same_season_does_not_overwrite_first_match(db):
    countries = {505: "Italy", 211: "Portugal"}
    import_fixtures(db, parse_fixtures(body(fixture(2, (505, "Inter"), (211, "Benfica"), league=2, season=2026, date="2026-10-01T19:00:00+00:00"))), countries)
    later = parse_fixtures(body(fixture(3, (505, "Inter"), (211, "Benfica"), league=2, season=2026, date="2027-03-10T20:00:00+00:00", status="NS")))
    assert import_fixtures(db, later, countries).skipped == 1
    first = db.scalar(select(Match))
    assert first.kickoff_at.month == 10 and first.status == "finished"
