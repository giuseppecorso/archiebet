from datetime import UTC, datetime, timedelta

from app.adapters.base import DataSourceAdapter
from app.adapters.cache import MISSING, FileCache


class Clock:
    def __init__(self):
        self.now = datetime(2026, 10, 11, 12, 0, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.now


class FakeSource(DataSourceAdapter):
    source = "fake"


def test_cache_respects_max_age(tmp_path):
    clock = Clock()
    cache = FileCache(tmp_path, "fake", now=clock)
    assert cache.get("k", timedelta(hours=1)) is MISSING

    cache.set("k", {"partite": ["Napoli – Roma"]})
    assert cache.get("k", timedelta(hours=1)) == {"partite": ["Napoli – Roma"]}

    clock.now += timedelta(hours=2)
    assert cache.get("k", timedelta(hours=1)) is MISSING


def test_adapter_calls_source_once_and_logs_it(tmp_path):
    calls: list[str] = []
    adapter = FakeSource(FileCache(tmp_path, "fake"), on_call=calls.append)
    fetches = []

    def fetch():
        fetches.append(1)
        return [1, 2, 3]

    assert adapter.cached("fixtures", timedelta(hours=1), fetch) == [1, 2, 3]
    assert adapter.cached("fixtures", timedelta(hours=1), fetch) == [1, 2, 3]
    assert len(fetches) == 1
    assert calls == ["fake"]


def test_cached_none_is_not_refetched(tmp_path):
    adapter = FakeSource(FileCache(tmp_path, "fake"))
    fetches = []
    adapter.cached("k", timedelta(hours=1), lambda: fetches.append(1))
    adapter.cached("k", timedelta(hours=1), lambda: fetches.append(1))
    assert len(fetches) == 1


def test_scheduler_off_when_disabled():
    from app.config import Settings
    from app.jobs import start_scheduler

    assert start_scheduler(Settings(sync_enabled=False)) is None


def test_scheduler_registers_sync_job():
    from app.config import Settings
    from app.jobs import start_scheduler

    scheduler = start_scheduler(Settings(sync_enabled=True, sync_interval_hours=6))
    try:
        jobs = {job.id: job for job in scheduler.get_jobs()}
        assert set(jobs) == {"sync-data", "live"}
        assert jobs["sync-data"].trigger.interval.total_seconds() == 6 * 3600
        assert jobs["live"].trigger.interval.total_seconds() == 60  # risultati in diretta (D92)
    finally:
        scheduler.shutdown(wait=False)
