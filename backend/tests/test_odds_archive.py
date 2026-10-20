"""Archivio dello storico quote (D82): mercati tenuti, ripresa, partite senza storico, rete che cade."""

from datetime import UTC, datetime, timedelta

from app.adapters.cache import FileCache
from app.ingest.odds_archive import archive_history, archived_market_ids, compact

DEFS = [
    {"marketId": 101, "marketName": "Full Time Result", "period": "fulltime"},
    {"marketId": 10803, "marketName": "Corners - Over Under Full Time", "period": "fulltime"},
    {"marketId": 101551, "marketName": "Corners - Over Under First Half", "period": "p1"},
    {"marketId": 10911, "marketName": "Bookings - 1X2", "period": "fulltime"},
    {"marketId": 10851, "marketName": "Corners - Handicap", "period": "fulltime"},
    {"marketId": 999, "marketName": "Player To Score", "period": "result"},
]


def test_kept_markets():
    keep = archived_market_ids(DEFS)
    assert {"101", "10803", "10911"} <= keep
    assert not {"101551", "10851", "999"} & keep


def test_compact_drops_other_markets():
    body = {"bookmakers": {"pinnacle": {"markets": {"10803": {"x": 1}, "999": {"y": 2}}}}}
    assert compact(body, {"10803"}) == {"pinnacle": {"markets": {"10803": {"x": 1}}}}


class FakeAdapter:
    def __init__(self, fixtures, histories):
        self.fixtures, self.histories, self.calls = fixtures, histories, []

    def markets(self):
        return DEFS

    def finished_fixtures(self, tournament_id, max_age):
        return self.fixtures if tournament_id == 23 else []

    def raw_history(self, fixture_id, slugs):
        self.calls.append(fixture_id)
        answer = self.histories[fixture_id]
        if isinstance(answer, list):  # sequenza di tentativi
            answer = answer.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return answer


def fixture(fid, start):
    return {"fixtureId": fid, "startTime": start, "participant1Id": 1, "participant2Id": 2}


def test_archive_is_resumable_and_handles_missing_and_timeouts(tmp_path):
    fixtures = [fixture("old", "2026-03-01T15:00:00.000Z"), fixture("a", "2026-05-01T15:00:00.000Z"),
                fixture("b", "2026-05-02T15:00:00.000Z"), fixture("c", "2026-05-03T15:00:00.000Z")]
    full = {"bookmakers": {"pinnacle": {"markets": {"10803": {"o": 1}, "999": {}}}}}
    adapter = FakeAdapter(fixtures, {"a": full, "b": None, "c": [TimeoutError(), full]})
    archive = FileCache(tmp_path, "odds-archive")
    since = datetime(2026, 4, 1, tzinfo=UTC)

    report = archive_history(adapter, archive, since, log=lambda _: None, sleep=lambda s: None)
    assert (report.saved, report.missing, report.failed) == (2, 1, 0)
    assert "old" not in adapter.calls  # prima della data scelta
    saved = archive.get("a", timedelta(days=1))
    assert saved["bookmakers"] == {"pinnacle": {"markets": {"10803": {"o": 1}}}}
    assert saved["fixture"]["startTime"] == "2026-05-01T15:00:00.000Z"

    adapter.calls.clear()
    again = archive_history(adapter, archive, since, log=lambda _: None, sleep=lambda s: None)
    assert adapter.calls == [] and again.already == 3  # niente da riscaricare, nemmeno la partita senza storico


def test_prune_removes_only_old_files_with_prefix(tmp_path):
    clock = [datetime(2026, 10, 1, tzinfo=UTC)]
    cache = FileCache(tmp_path, "oddspapi", now=lambda: clock[0])
    cache.set("historical-odds?fixtureId=1", {})
    cache.set("participants?sportId=10", {})
    import os, time
    for path in cache.dir.glob("*.json"):
        old = time.time() - 3 * 86400
        os.utime(path, (old, old))
    clock[0] = datetime.now(UTC)
    assert cache.prune("historical-odds", timedelta(days=2)) == 1
    assert cache.get("participants?sportId=10", timedelta(days=3650)) == {}
