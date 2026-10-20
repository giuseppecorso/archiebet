"""Archivio dello storico quote di OddsPapi (D82).

Lo storico gratuito copre solo gli ultimi ~6 mesi (verificato: da aprile 2026 in poi al 2026-10-20), quindi lo
salviamo prima che sparisca. Per non occupare decine di GB si tengono solo i mercati che usiamo o proviamo:
quelli principali, angoli e cartellini (Over/Under totali e per squadra, 1X2) a fine partita.
"""

import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from app.adapters.cache import MISSING, FileCache
from app.adapters.oddspapi import MARKETS, TOURNAMENTS, OddsPapiAdapter, OddsPapiError

ARCHIVE_SLUGS = ("pinnacle", "sisal.it", "eurobet.it")  # riferimento + bookmaker di Giuse: una chiamata per partita
FOREVER = timedelta(days=36500)
RETRIES = 3


def archived_market_ids(definitions: Iterable[dict[str, Any]]) -> set[str]:
    """Mercati da tenere: i principali e quelli di angoli/cartellini a fine partita (niente tempi, niente giocatori)."""
    keep = set(MARKETS)
    for m in definitions:
        name = m["marketName"]
        if m["period"] == "fulltime" and name.startswith(("Corners - ", "Bookings - ")) and "Half" not in name:
            if "Over Under" in name or name.endswith("1X2"):
                keep.add(str(m["marketId"]))
    return keep


def compact(body: dict[str, Any], keep: set[str]) -> dict[str, Any]:
    """Lo storico ridotto ai mercati da tenere."""
    return {
        bookmaker: {"markets": {m: v for m, v in (data.get("markets") or {}).items() if m in keep}}
        for bookmaker, data in body.get("bookmakers", {}).items()
    }


@dataclass
class ArchiveReport:
    saved: int = 0
    missing: int = 0  # OddsPapi non ha lo storico
    already: int = 0
    failed: int = 0


def archive_history(
    adapter: OddsPapiAdapter,
    archive: FileCache,
    since: datetime,
    log: Callable[[str], None] = print,
    sleep: Callable[[float], None] = time.sleep,
) -> ArchiveReport:
    """Scarica e salva lo storico delle partite finite dei campionati seguiti, dalla data since in poi.

    Riprendibile: le partite già in archivio (anche quelle senza storico) si saltano.
    """
    keep = archived_market_ids(adapter.markets())
    report = ArchiveReport()
    for tournament_id, code in TOURNAMENTS.items():
        fixtures = [f for f in adapter.finished_fixtures(tournament_id, max_age=timedelta(days=1)) if f["startTime"] >= since.isoformat()[:19]]
        log(f"{code}: {len(fixtures)} partite dal {since.date()}")
        for fixture in fixtures:
            key = fixture["fixtureId"]
            if archive.get(key, FOREVER) is not MISSING:
                report.already += 1
                continue
            body = _fetch(adapter, key, sleep)
            if body is False:
                report.failed += 1
                continue
            record = {
                "fixture": {k: fixture.get(k) for k in ("fixtureId", "tournamentId", "startTime", "participant1Id", "participant2Id",
                                                        "participant1Name", "participant2Name")},
                "bookmakers": compact(body, keep) if body else {},
            }
            archive.set(key, record)
            report.saved += bool(body)
            report.missing += not body
        log(f"{code}: finora {report.saved} salvate, {report.missing} senza storico, {report.already} già in archivio")
    return report


def _fetch(adapter: OddsPapiAdapter, fixture_id: str, sleep: Callable[[float], None]) -> dict[str, Any] | None | bool:
    """Storico grezzo; None se non esiste, False se la rete continua a fallire (si riproverà al prossimo lancio)."""
    for attempt in range(RETRIES):
        try:
            return adapter.raw_history(fixture_id, ARCHIVE_SLUGS)
        except OddsPapiError as error:
            if error.status is None or error.status < 500:
                raise
            sleep(10 * (attempt + 1))  # guasto momentaneo del servizio
        except Exception:  # timeout o rete: attendo e riprovo
            sleep(10 * (attempt + 1))
    return False

