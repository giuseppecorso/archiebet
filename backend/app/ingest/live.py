"""Risultati in diretta da API-Football (Fase 5, D92) e cronaca con marcatori (D133).

Ogni minuto, solo se una nostra partita è in corso (o sta per iniziare): una richiesta per tutte le partite live
dei nostri campionati. Minuto e punteggio vanno in `match_live`; la cronaca (gol, cartellini, cambi) arriva dalle
richieste per id, fino a 20 partite l'una. Quando una partita esce dall'elenco live si chiede il risultato finale
e la cronaca definitiva. Le partite finite senza cronaca (app spenta) si recuperano con `sync_missing_events`.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import and_, delete, or_, select
from sqlalchemy.orm import Session

from app.adapters.api_football import SOURCE, AFEvent, ApiFootballAdapter
from app.ingest.api_football import import_fixtures
from app.models import Match, MatchEvent, MatchLive, MatchSource, MatchStatus

WATCH_BEFORE = timedelta(minutes=5)  # si comincia a guardare poco prima del calcio d'inizio
WATCH_AFTER = timedelta(minutes=150)  # e si smette dopo 2 ore e mezza (recuperi, supplementari)
MAX_IDS_PER_CALL = 20
OVERDUE = timedelta(hours=2)  # da giocare due ore dopo il fischio d'inizio: si richiede il risultato
EVENTS_BACKFILL_DAYS = 3  # cronaca recuperata per le partite finite negli ultimi 3 giorni
EVENTS_BACKFILL_CALLS = 10  # al massimo 200 partite per giro


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


def store_events(db: Session, match_id: int, events: Sequence[AFEvent], now: datetime, final: bool) -> None:
    """Sostituisce la cronaca della partita; a partita finita la segna come scaricata."""
    db.execute(delete(MatchEvent).where(MatchEvent.match_id == match_id))
    for seq, e in enumerate(events):
        db.add(MatchEvent(match_id=match_id, seq=seq, minute=e.minute, extra=e.extra, side=e.side, kind=e.kind,
                          player=(e.player or "")[:80] or None, other=(e.other or "")[:80] or None, detail=(e.detail or "")[:80] or None))  # fmt: skip
    if final:
        db.get(Match, match_id).events_synced_at = now


def _by_ids(adapter: ApiFootballAdapter, ids: Sequence[int]):
    for start in range(0, len(ids), MAX_IDS_PER_CALL):
        yield adapter.fixtures_by_ids(ids[start : start + MAX_IDS_PER_CALL])


def sync_missing_events(db: Session, adapter: ApiFootballAdapter, now: datetime) -> int:
    """Cronaca delle partite finite negli ultimi giorni che non l'hanno ancora (es. app spenta durante la partita),
    e risultato delle partite che dovrebbero essere finite ma risultano ancora da giocare."""
    rows = db.execute(
        select(MatchSource.external_id, Match.id)
        .join(Match, Match.id == MatchSource.match_id)
        .where(MatchSource.source == SOURCE, Match.kickoff_at >= now - timedelta(days=EVENTS_BACKFILL_DAYS),
               or_(and_(Match.status == MatchStatus.FINISHED, Match.events_synced_at.is_(None)),
                   and_(Match.status == MatchStatus.SCHEDULED, Match.kickoff_at <= now - OVERDUE)))
        .order_by(Match.kickoff_at.desc())
        .limit(MAX_IDS_PER_CALL * EVENTS_BACKFILL_CALLS)
    ).all()  # fmt: skip
    links = {int(ext): mid for ext, mid in rows}
    done = 0
    for fixtures in _by_ids(adapter, list(links)):
        import_fixtures(db, fixtures)  # risultato finale (se mancava), primo tempo e arbitro
        for fx in fixtures:
            if fx.id in links and fx.status == MatchStatus.FINISHED:
                store_events(db, links[fx.id], fx.events, now, final=True)
                done += 1
        db.commit()
    return done


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

    # Cronaca delle partite in corso (marcatori, cartellini, cambi)
    live_ids = [ext for ext, mid in links.items() if mid in seen]
    for fixtures in _by_ids(adapter, live_ids):
        for fx in fixtures:
            if fx.id in links:
                store_events(db, links[fx.id], fx.events, now, final=False)
        db.commit()

    # Uscite dall'elenco live: finite (o sospese). Si chiede la loro situazione e si salva il risultato
    ended = [m for m in db.scalars(select(MatchLive.match_id)) if m not in seen]
    by_match = {mid: ext for ext, mid in links.items()}
    ids = [by_match[m] for m in ended if m in by_match]
    for fixtures in _by_ids(adapter, ids):
        import_fixtures(db, fixtures)
        for fx in fixtures:
            if fx.id in links and not fx.is_live:
                store_events(db, links[fx.id], fx.events, now, final=fx.status == MatchStatus.FINISHED)
        done = [links[fx.id] for fx in fixtures if not fx.is_live and fx.id in links]
        if done:
            db.execute(delete(MatchLive).where(MatchLive.match_id.in_(done)))
            report.finished += sum(1 for fx in fixtures if fx.status == MatchStatus.FINISHED)
        db.commit()
    return report
