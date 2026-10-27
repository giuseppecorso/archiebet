"""Dettaglio delle partite finite da API-Football per lo studio (D140): xG, arbitro, eventi, giocatori, titolari.

Una richiesta /fixtures?ids= porta 20 partite complete. Di ognuna si salva in cache, per sempre, solo una scheda
compatta (le partite finite non cambiano): i modelli e le prove leggono da lì, senza rete.
Circa 1.000 richieste per 4 stagioni di 13 campionati; si riprende da dove ci si era fermati.
"""

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from app.adapters.api_football import ApiFootballAdapter, ApiFootballError, QuotaExhausted
from app.adapters.cache import MISSING

FOREVER = timedelta(days=36500)
BATCH = 20
FINISHED = {"FT", "AET", "PEN"}


def detail_key(fixture_id: int) -> str:
    return f"fixture-detail?id={fixture_id}"


def _num(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def compact(item: dict[str, Any]) -> dict[str, Any]:
    """La scheda compatta di una partita: solo quello che usano lo studio e le prove."""
    fx, teams = item["fixture"], item["teams"]
    home_id = teams["home"]["id"]
    stats = {}
    for block in item.get("statistics") or []:
        side = "home" if block["team"]["id"] == home_id else "away"
        values = {s["type"]: s["value"] for s in block.get("statistics") or []}
        stats[side] = {"xg": _num(values.get("expected_goals")), "shots": _num(values.get("Total Shots")),
                       "shots_on": _num(values.get("Shots on Goal")), "corners": _num(values.get("Corner Kicks")),
                       "yellow": _num(values.get("Yellow Cards")), "red": _num(values.get("Red Cards"))}  # fmt: skip
    players = {}
    for block in item.get("players") or []:
        side = "home" if block["team"]["id"] == home_id else "away"
        rows = []
        for p in block.get("players") or []:
            s = (p.get("statistics") or [{}])[0]
            games, goals = s.get("games") or {}, s.get("goals") or {}
            rows.append([p["player"]["id"], p["player"]["name"], games.get("position"), games.get("minutes") or 0,
                         goals.get("total") or 0, goals.get("assists") or 0, bool(games.get("substitute"))])  # fmt: skip
        players[side] = rows
    starters = {}
    for block in item.get("lineups") or []:
        side = "home" if block["team"]["id"] == home_id else "away"
        starters[side] = [x["player"]["id"] for x in block.get("startXI") or [] if x.get("player")]
    events = [[(e.get("time") or {}).get("elapsed"), (e.get("time") or {}).get("extra"), "home" if (e.get("team") or {}).get("id") == home_id else "away",
               e.get("type"), e.get("detail")] for e in item.get("events") or []]  # fmt: skip
    score = item.get("score") or {}
    return {
        "id": fx["id"], "date": fx["date"], "referee": fx.get("referee"), "status": fx["status"]["short"],
        "league": item["league"]["id"], "season": item["league"]["season"],
        "home": teams["home"]["id"], "away": teams["away"]["id"],
        "goals": [item["goals"]["home"], item["goals"]["away"]],
        "ht": [(score.get("halftime") or {}).get("home"), (score.get("halftime") or {}).get("away")],
        "stats": stats, "players": players, "starters": starters, "events": events,
    }  # fmt: skip


@dataclass
class DetailReport:
    fixtures: int = 0
    downloaded: int = 0
    requests: int = 0
    stopped: str | None = None


def download_details(adapter: ApiFootballAdapter, leagues: Iterable[int], seasons: Iterable[int],
                     log: Callable[[str], None] = print, max_requests: int = 2500) -> DetailReport:  # fmt: skip
    """Scarica la scheda di tutte le partite finite dei campionati e delle stagioni indicate, 20 per richiesta."""
    report = DetailReport()
    for league in leagues:
        for season in seasons:
            try:
                fixtures = adapter.fixtures(league, season, FOREVER if season < 2026 else timedelta(hours=12))
            except (ApiFootballError, QuotaExhausted) as error:
                report.stopped = str(error)
                return report
            done = [f.id for f in fixtures if f.status_short in FINISHED]
            report.fixtures += len(done)
            missing = [i for i in done if adapter.cache.get(detail_key(i), FOREVER) is MISSING]
            for start in range(0, len(missing), BATCH):
                if report.requests >= max_requests:
                    report.stopped = f"limite di {max_requests} richieste per giro"
                    return report
                ids = missing[start : start + BATCH]
                try:
                    body = adapter._request("/fixtures", {"ids": "-".join(str(i) for i in ids)})
                except QuotaExhausted as error:
                    report.stopped = str(error)
                    return report
                except ApiFootballError as error:
                    log(f"  {league}/{season}: richiesta non riuscita ({error}), vado avanti")
                    continue
                report.requests += 1
                for item in body.get("response", []):
                    adapter.cache.set(detail_key(item["fixture"]["id"]), compact(item))
                    report.downloaded += 1
            log(f"campionato {league}, stagione {season}: {len(done)} partite finite, scaricate {len(missing)}")
    return report


def load_details(cache, fixture_ids: Iterable[int]) -> list[dict[str, Any]]:
    out = []
    for i in fixture_ids:
        d = cache.get(detail_key(i), FOREVER)
        if d is not MISSING:
            out.append(d)
    return out
