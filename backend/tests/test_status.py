"""Stato dei dati: registro degli aggiornamenti, freschezza per campionato, un solo aggiornamento alla volta."""

from datetime import UTC, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

import app.jobs as jobs
from app.forecast.service import refresh_predictions
from app.models import SyncRun
from tests.test_football_api import seeded  # noqa: F401 (fixture condivisa)


@pytest.fixture
def jobs_db(db, monkeypatch):
    """I lavori programmati scrivono nel DB dei test, non in quello vero."""
    monkeypatch.setattr(jobs, "SessionLocal", sessionmaker(bind=db.get_bind(), expire_on_commit=False))
    return db


def test_tracked_runs_are_recorded_ok_or_failed(jobs_db):
    jobs._tracked("football-data", lambda: "3 partite nuove")

    def broken() -> str:
        raise RuntimeError("rete giù")

    jobs._tracked("football-data", broken)
    runs = list(jobs_db.scalars(select(SyncRun).order_by(SyncRun.id)))
    assert [(r.ok, r.message) for r in runs] == [(True, "3 partite nuove"), (False, "errore: riprovo al prossimo giro")]


def test_status_reports_freshness(logged_client, seeded, jobs_db):  # noqa: F811
    status = logged_client.get("/api/status").json()
    assert status["syncing"] is False
    assert {s["source"]: s["last_ok_at"] for s in status["sources"]} == {
        "football-data": None,
        "api-football": None,
        "predictions": None,
    }
    serie_a = next(c for c in status["competitions"] if c["competition"]["code"] == "ITA-A")
    assert serie_a["awaiting_results"] == 1  # Lazio-Milan giocata da 3 giorni, risultato non arrivato
    assert serie_a["last_result_at"] is not None and serie_a["next_match_at"] is not None
    assert (status["upcoming"], status["upcoming_with_prediction"]) == (2, 0)

    refresh_predictions(jobs_db, datetime.now(UTC))
    jobs._tracked("football-data", lambda: "ok")
    status = logged_client.get("/api/status").json()
    assert status["upcoming_with_prediction"] == 2
    fd = next(s for s in status["sources"] if s["source"] == "football-data")
    assert fd["last_run_ok"] is True and fd["last_ok_at"] is not None


def test_only_one_sync_at_a_time(logged_client, monkeypatch):
    monkeypatch.setattr(jobs, "sync_football_data_job", lambda: pytest.fail("non deve partire"))
    with jobs._sync_lock:  # un aggiornamento è già in corso
        assert jobs.sync_all_job() is False
        assert logged_client.post("/api/status/refresh").json() == {"started": False}
        assert logged_client.get("/api/status").json()["syncing"] is True


def test_status_requires_login(client):
    assert client.get("/api/status").status_code == 401
    assert client.post("/api/status/refresh").status_code == 401
