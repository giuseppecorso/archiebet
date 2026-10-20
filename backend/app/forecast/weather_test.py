"""Prova del nove del meteo (D76): pioggia, vento e temperatura estrema contro il mercato di apertura.

1. fetch_features: per ogni stadio e stagione una richiesta all'archivio Open-Meteo; si salvano solo i 3 numeri
   di ogni partita (file JSON), riprendibile se il servizio dice "basta" (limiti del piano gratuito).
2. run: Under/Over 2.5 (ricalibrazione a due esiti) e 1X2 (D56) con e senza meteo, walk-forward per stagione.
"""

import json
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
from sqlalchemy import select
from sqlalchemy.orm import Session, aliased

from app.adapters.open_meteo import OpenMeteoAdapter, OpenMeteoError
from app.forecast.binary_model import BinaryRow
from app.forecast.binary_model import walk_forward_by_season as binary_walk_forward
from app.forecast.backtest import paired
from app.forecast.weather import match_weather
from app.models import Competition, Match, MatchStatus, Team

LEAGUES = ("ITA-A", "ITA-B", "ENG-1", "ENG-2", "ESP-1", "ESP-2", "GER-1", "GER-2", "FRA-1", "FRA-2")
FIRST, LAST = "2019/20", "2024/25"  # da quando football-data ha gli orari; la 2025/26 non si usa per tarare
FEATURE_NAMES = ("pioggia", "vento", "temperatura estrema")


@dataclass(frozen=True)
class Target:
    match_id: int
    season: str
    kickoff: datetime
    lat: float
    lon: float


def targets(db: Session, first: str = FIRST, last: str = LAST) -> list[Target]:
    home = aliased(Team)
    rows = db.execute(
        select(Match.id, Match.season, Match.kickoff_at, home.latitude, home.longitude)
        .join(Competition, Match.competition_id == Competition.id)
        .join(home, Match.home_team_id == home.id)
        .where(
            Competition.code.in_(LEAGUES), Match.status == MatchStatus.FINISHED, Match.kickoff_has_time.is_(True),
            Match.season.between(first, last), home.latitude.is_not(None),
        )
    ).all()  # fmt: skip
    return [Target(*r) for r in rows]


def fetch_features(
    meteo: OpenMeteoAdapter, items: list[Target], store: Path, log: Callable[[str], None] = print, max_requests: int = 4000
) -> dict[str, list[float] | None]:
    """Meteo di ogni partita, salvato in `store`. Riprende da dove si era fermato; si ferma se il servizio limita."""
    done: dict[str, list[float] | None] = json.loads(store.read_text(encoding="utf-8")) if store.exists() else {}
    groups: dict[tuple[float, float, str], list[Target]] = defaultdict(list)
    for t in items:
        if str(t.match_id) not in done:
            groups[(round(t.lat, 2), round(t.lon, 2), t.season)].append(t)
    log(f"Meteo: {len(done)} partite già pronte, {sum(map(len, groups.values()))} da scaricare in {len(groups)} richieste")
    for i, ((lat, lon, _), group) in enumerate(groups.items()):
        if i >= max_requests:
            break
        start = min(t.kickoff for t in group).date()
        end = (max(t.kickoff for t in group) + timedelta(hours=3)).date()
        try:
            hourly = meteo.hourly_uncached(lat, lon, start, end)
        except OpenMeteoError as e:
            log(f"Open-Meteo si è fermato ({e}): riprendo al prossimo lancio")
            break
        for t in group:
            w = match_weather(hourly, t.kickoff)
            done[str(t.match_id)] = list(w) if w else None
        if i % 25 == 0:
            store.parent.mkdir(parents=True, exist_ok=True)
            store.write_text(json.dumps(done), encoding="utf-8")
    store.parent.mkdir(parents=True, exist_ok=True)
    store.write_text(json.dumps(done), encoding="utf-8")
    return done


def standardize(features: dict[int, list[float]], seasons: dict[int, str], reference_season: str) -> dict[int, list[float]]:
    """Scala ogni fattore con media e deviazione della prima stagione (solo passato: niente dati dal futuro)."""
    ref = np.array([v for m, v in features.items() if seasons.get(m) == reference_season])
    mean, std = ref.mean(axis=0), ref.std(axis=0)
    std[std == 0] = 1.0
    return {m: list((np.array(v) - mean) / std) for m, v in features.items()}


@dataclass(frozen=True)
class BinaryResult:
    name: str
    n: int
    log_loss: float
    diff: float | None  # rispetto al mercato ricalibrato (negativo = meglio)
    std_error: float | None

    @property
    def passes(self) -> bool:
        return self.diff is not None and self.diff < -2 * self.std_error


def run_binary(rows: list[BinaryRow], factors: dict[str, dict[int, list[float]]], eval_seasons: list[str]) -> list[BinaryResult]:
    by_id = {r.match_id: r for r in rows}

    def losses(probs: dict[int, float]) -> dict[int, float]:
        return {m: -float(np.log(p if by_id[m].outcome else 1 - p)) for m, p in probs.items()}

    base = losses(binary_walk_forward(rows, {}, eval_seasons, n_features=1))
    out = [BinaryResult("Mercato ricalibrato", len(base), float(np.mean(list(base.values()))), None, None)]
    for name, feats in factors.items():
        ll = losses(binary_walk_forward(rows, feats, eval_seasons, n_features=len(next(iter(feats.values())))))
        common = [m for m in ll if m in base]
        cmp = paired(np.array([ll[m] - base[m] for m in common]))
        out.append(BinaryResult(name, len(ll), float(np.mean(list(ll.values()))), cmp.mean_diff, cmp.std_error))
    return out
