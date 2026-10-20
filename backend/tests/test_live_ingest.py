"""Risultati in diretta (D92): minuto e punteggio salvati, risultato finale appena la partita esce dal live."""

from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.adapters.api_football import parse_fixtures
from app.ingest.api_football import import_fixtures
from app.ingest.live import needs_live, sync_live
from app.models import Match, MatchLive
from tests.test_api_football import body, fixture

KICKOFF = "2026-10-24T13:00:00+00:00"
NOW = datetime(2026, 10, 24, 13, 50, tzinfo=UTC)


class FakeLiveAF:
    def __init__(self, live, by_ids=None):
        self.live_body, self.by_ids_body, self.asked = live, by_ids or body(), []

    def live(self, league_ids):
        return parse_fixtures(self.live_body)

    def fixtures_by_ids(self, ids):
        self.asked.append(list(ids))
        return parse_fixtures(self.by_ids_body)


def scheduled_match(db):
    import_fixtures(db, parse_fixtures(body(fixture(77, (505, "Inter"), (489, "AC Milan"), date=KICKOFF, status="NS", league=135, season=2026))))
    return db.scalar(select(Match))


def test_live_score_and_minute_are_saved(db):
    m = scheduled_match(db)
    assert needs_live(db, NOW)
    live = fixture(77, (505, "Inter"), (489, "AC Milan"), date=KICKOFF, status="2H", goals=(1, 0), league=135, season=2026)
    live["fixture"]["status"]["elapsed"] = 52
    report = sync_live(db, FakeLiveAF(body(live)), [135], NOW)
    row = db.get(MatchLive, m.id)
    assert report.live == 1 and (row.status, row.minute, row.home_goals, row.away_goals) == ("2H", 52, 1, 0)
    db.refresh(m)
    assert m.status == "scheduled" and m.home_goals is None  # il risultato vero arriva solo a fine partita


def test_finished_match_gets_its_result_and_leaves_live(db):
    m = scheduled_match(db)
    db.add(MatchLive(match_id=m.id, status="2H", minute=88, home_goals=2, away_goals=1, updated_at=NOW))
    db.commit()
    final = fixture(77, (505, "Inter"), (489, "AC Milan"), date=KICKOFF, status="FT", goals=(2, 1), ht=(1, 1), league=135, season=2026)
    af = FakeLiveAF(body(), by_ids=body(final))
    report = sync_live(db, af, [135], NOW + timedelta(minutes=50))
    assert af.asked == [[77]] and report.finished == 1
    db.refresh(m)
    assert (m.status, m.home_goals, m.away_goals) == ("finished", 2, 1)
    assert db.get(MatchLive, m.id) is None


def test_no_live_requests_when_nothing_is_on(db):
    scheduled_match(db)
    assert not needs_live(db, NOW - timedelta(hours=3))  # tre ore prima: niente da guardare
    assert not needs_live(db, NOW + timedelta(hours=3))  # dopo la finestra, e nessuna partita segnata in corso
