from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import func, select

from app.adapters.cache import FileCache
from app.adapters.football_data import FootballDataAdapter, parse_csv
from app.ingest.football_data import import_matches, sync_football_data
from app.models import Competition, Match, MatchOdds, MatchStatus, Team, TeamAlias

HEADER = "Div,Date,Time,HomeTeam,AwayTeam,FTHG,FTAG,HS,AS,B365H,B365D,B365A\n"
SEASON = HEADER + "I1,22/08/2026,17:30,Inter,Monza,4,1,13,7,1.2,7,13\nI1,23/08/2026,19:45,Milan,Inter,0,0,9,11,2.6,3.3,2.7\n"
FIXTURE_HEADER = "Div,Date,Time,HomeTeam,AwayTeam,B365H,B365D,B365A\n"


def count(db, model):
    return db.scalar(select(func.count()).select_from(model))


def test_import_creates_teams_matches_and_odds(db):
    report = import_matches(db, parse_csv(SEASON), season="2026/27")
    assert (report.created, report.updated, report.odds) == (2, 0, 6)
    assert {t.name for t in db.scalars(select(Team))} == {"Inter", "Monza", "Milan"}
    assert count(db, TeamAlias) == 3
    inter_monza = db.scalar(select(Match).join(Match.home_team).where(Team.name == "Inter"))
    assert inter_monza.competition.code == "ITA-A"
    assert inter_monza.season == "2026/27"
    assert inter_monza.status == MatchStatus.FINISHED
    assert (inter_monza.home_goals, inter_monza.away_goals, inter_monza.home_shots) == (4, 1, 13)


def test_reimport_updates_without_duplicates(db):
    import_matches(db, parse_csv(SEASON), season="2026/27")
    report = import_matches(db, parse_csv(SEASON), season="2026/27")
    assert (report.created, report.updated) == (0, 2)
    assert count(db, Match) == 2
    assert count(db, MatchOdds) == 6
    assert count(db, Competition) == 13  # Serie A, B, tre gironi di C e 8 campionati esteri, creati una volta sola


def test_fixture_becomes_result(db):
    fixture = FIXTURE_HEADER + "I1,22/08/2026,17:30,Inter,Monza,1.25,6.5,12\n"
    import_matches(db, parse_csv(fixture))
    match = db.scalar(select(Match))
    assert match.status == MatchStatus.SCHEDULED and match.home_goals is None
    assert match.season == "2026/27"  # ricavata dalla data

    import_matches(db, parse_csv(SEASON), season="2026/27")
    db.refresh(match)
    assert match.status == MatchStatus.FINISHED and match.home_goals == 4
    assert count(db, Match) == 2
    # Le quote di questa fonte sono state sostituite, non sommate
    assert db.scalar(select(MatchOdds.price).where(MatchOdds.match_id == match.id, MatchOdds.selection == "1")) == Decimal("1.2")


def test_same_match_twice_in_one_file(db):
    text = FIXTURE_HEADER + "I1,22/08/2026,17:30,Inter,Monza,1.25,6.5,12\nI1,22/08/2026,18:30,Inter,Monza,1.3,6,11\n"
    report = import_matches(db, parse_csv(text))
    assert (report.created, report.updated, report.odds) == (1, 0, 3)
    assert db.scalar(select(Match)).kickoff_at == datetime(2026, 8, 22, 17, 30, tzinfo=UTC)


def test_other_leagues_ignored(db):
    import_matches(db, parse_csv(FIXTURE_HEADER + "B1,09/10/2026,19:45,Beveren,Lommel SK,1.75,3.8,3.9\n"))
    assert count(db, Match) == 0


def test_sync_downloads_each_season_and_logs_calls(db, tmp_path):
    urls: list[str] = []
    calls: list[str] = []

    def fake_get(url: str) -> str:
        urls.append(url)
        if url.endswith("fixtures.csv"):
            return FIXTURE_HEADER + "I2,10/10/2026,14:00,Benevento,Cesena,2.1,3.2,3.5\n"
        if url.endswith("2627/I1.csv"):
            return SEASON
        return HEADER

    adapter = FootballDataAdapter(FileCache(tmp_path, "football-data"), on_call=calls.append, http_get=fake_get)
    now = datetime(2026, 10, 11, tzinfo=UTC)
    sync_football_data(db, adapter, first_season=2025, now=now, log=lambda _: None)

    assert sorted(u.rsplit("/", 2)[-2] + "/" + u.rsplit("/", 1)[-1] for u in urls if "mmz4281" in u) == [
        "2526/D1.csv", "2526/D2.csv", "2526/E0.csv", "2526/E1.csv", "2526/F1.csv", "2526/F2.csv", "2526/I1.csv", "2526/I2.csv", "2526/SP1.csv", "2526/SP2.csv",
        "2627/D1.csv", "2627/D2.csv", "2627/E0.csv", "2627/E1.csv", "2627/F1.csv", "2627/F2.csv", "2627/I1.csv", "2627/I2.csv", "2627/SP1.csv", "2627/SP2.csv",
    ]  # fmt: skip
    assert len(calls) == 21  # 10 campionati × 2 stagioni + prossime partite
    assert count(db, Match) == 3
    assert db.scalar(select(Competition.code).join(Match).join(Match.home_team).where(Team.name == "Benevento")) == "ITA-B"

    # Seconda volta: tutto dalla cache, nessuna chiamata in più
    sync_football_data(db, adapter, first_season=2025, now=now, log=lambda _: None)
    assert len(calls) == 21


def test_automatic_sync_skips_past_seasons_already_imported(db, tmp_path):
    read: list[str] = []
    past = HEADER + "I1,22/08/2025,17:30,Inter,Monza,4,1,13,7,1.2,7,13\n"

    def fake_get(url: str) -> str:
        return FIXTURE_HEADER if url.endswith("fixtures.csv") else (past if url.endswith("2526/I1.csv") else HEADER)

    adapter = FootballDataAdapter(FileCache(tmp_path, "football-data"), http_get=fake_get)
    original = adapter.season
    adapter.season = lambda league, year, current: (read.append(f"{league}{year}"), original(league, year, current))[1]
    now = datetime(2026, 10, 11, tzinfo=UTC)
    sync_football_data(db, adapter, first_season=2025, now=now, log=lambda _: None, skip_imported=True)
    assert "I12025" in read
    read.clear()
    sync_football_data(db, adapter, first_season=2025, now=now, log=lambda _: None, skip_imported=True)
    assert "I12025" not in read  # 2025/26 di Serie A già importata con le quote: non si rilegge
    assert "I12026" in read and "E02025" in read  # stagione in corso sempre; stagioni senza quote si riprovano
