"""Risultati in diretta da API-Football (Fase 5, D92).

Ogni minuto, solo se una nostra partita è in corso (o sta per iniziare): una richiesta per tutte le partite live
dei nostri campionati. Minuto e punteggio vanno in `match_live`; quando una partita esce dall'elenco live si
chiede il risultato finale (fino a 20 partite per richiesta) e lo si salva come fa l'aggiornamento normale.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.adapters.api_football import SOURCE, ApiFootballAdapter
from app.ingest.api_football import import_fixtures
from app.models import Match, MatchLive, MatchSource, MatchStatus

WATCH_BEFORE = timedelta(minutes=5)  # si comincia a guardare poco prima del calcio d'inizio
WATCH_AFTER = timedelta(minutes=150)  # e si smette dopo 2 ore e mezza (recuperi, supplementari)
MAX_IDS_PER_CALL = 20


@dataclass
class LiveReport:
    live: int = 0
    finished: int = 0


def needs_live(db: Session, now: datetime) -> bool:
    """C'è qualcosa da seguire? Una partita in programma nella finestra, o una già segnata come in corso."""
    if db.scalar(select(MatchLive.match_id).limit(1)) is not None:
        return True
    return db.scalar(
        select(Match.id).where(
            Match.status == MatchStatus.SCHEDULED,
            Match.kickoff_at.between(now - WATCH_AFTER, now + WATCH_BEFORE),
        ).limit(1)
    ) is not None


def sync_live(db: Session, adapter: ApiFootballAdapter, league_ids: Sequence[int], now: datetime) -> LiveReport:
    report = LiveReport()
    links = {int(s.external_id): s.match_id for s in db.scalars(select(MatchSource).where(MatchSource.source == SOURCE))}
    seen: set[int] = set()
    for fx in adapter.live(league_ids):
        match_id = links.get(fx.id)
        if match_id is None or not fx.is_live:
            continue
        seen.add(match_id)
        row = db.get(MatchLive, match_id) or MatchLive(match_id=match_id)
        row.status, row.minute = fx.status_short, fx.elapsed
        row.home_goals, row.away_goals = fx.live_home_goals or 0, fx.live_away_goals or 0
        row.updated_at = now
        db.add(row)
        report.live += 1
    db.commit()

    # Uscite dall'elenco live: finite (o sospese). Si chiede la loro situazione e si salva il risultato
    ended = [m for m in db.scalars(select(MatchLive.match_id)) if m not in seen]
    by_match = {mid: ext for ext, mid in links.items()}
    ids = [by_match[m] for m in ended if m in by_match]
    for start in range(0, len(ids), MAX_IDS_PER_CALL):
        fixtures = adapter.fixtures_by_ids(ids[start : start + MAX_IDS_PER_CALL])
        import_fixtures(db, fixtures)
        done = [links[fx.id] for fx in fixtures if not fx.is_live and fx.id in links]
        if done:
            db.execute(delete(MatchLive).where(MatchLive.match_id.in_(done)))
            report.finished += sum(1 for fx in fixtures if fx.status == MatchStatus.FINISHED)
        db.commit()
    return report
