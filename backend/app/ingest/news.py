"""Archie tifoso (D101-D102): raccoglie le notizie della Serie C, ne estrae i fatti, giudica le partite e misura
se poi le quote si muovono verso il suo giudizio."""

import logging
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.adapters.news import FeedItem, NewsAdapter
from app.ai.client import Ai, AiError
from app.ai.gateway import BudgetExceeded
from app.ai.news import FactText, NewsText, extract_facts, judge_match
from app.forecast.history_sim import Estimate, clustered_mean
from app.forecast.picks import italian_consensus
from app.forecast.radar_service import load_book_odds
from app.models import Competition, Match, MatchInsight, MatchStatus, NewsItem, TeamFact

logger = logging.getLogger(__name__)

SERIE_C = "ITA-C%"
ITEMS_MAX_AGE = timedelta(days=4)  # notizie più vecchie non si leggono
GNEWS_AHEAD = timedelta(days=3)  # Google News solo per chi gioca nei prossimi 3 giorni
FACTS_WINDOW = timedelta(days=10)  # fatti considerati nel giudizio
JUDGE_AHEAD = timedelta(days=4)
JUDGE_EVERY = timedelta(hours=12)  # al massimo un giudizio ogni 12 ore per partita
SIGNAL_BEFORE = timedelta(minutes=30)  # D101: il segnale vale se registrato almeno 30 minuti prima
BATCH = 40
TARGET_SIGNALS = 150  # D101: verdetto a 150 segnali


def normalize(name: str) -> str:
    return " ".join(name.lower().replace(".", " ").split())


def upcoming_serie_c(db: Session, now: datetime, ahead: timedelta) -> list[Match]:
    return list(db.scalars(
        select(Match).join(Competition, Competition.id == Match.competition_id)
        .where(Competition.code.like(SERIE_C), Match.status == MatchStatus.SCHEDULED, Match.kickoff_at > now, Match.kickoff_at <= now + ahead)
        .order_by(Match.kickoff_at)
    ))  # fmt: skip


def serie_c_teams(db: Session, now: datetime) -> dict[int, str]:
    """Squadre di Serie C della stagione: quelle con partite negli ultimi 60 giorni o nei prossimi 60."""
    rows = db.scalars(
        select(Match).join(Competition, Competition.id == Match.competition_id)
        .where(Competition.code.like(SERIE_C), Match.kickoff_at >= now - timedelta(days=60), Match.kickoff_at <= now + timedelta(days=60))
    )  # fmt: skip
    out = {}
    for m in rows:
        out[m.home_team_id], out[m.away_team_id] = m.home_team.name, m.away_team.name
    return out


@dataclass
class NewsReport:
    fetched: int = 0
    new: int = 0
    processed: int = 0
    facts: int = 0
    judged: int = 0
    settled: int = 0
    errors: list[str] = field(default_factory=list)


def store_items(db: Session, items: Sequence[FeedItem], now: datetime) -> int:
    """Salva le notizie nuove (per link), solo se recenti. Restituisce quante."""
    fresh = {i.url: i for i in items if i.published_at >= now - ITEMS_MAX_AGE}
    if not fresh:
        return 0
    known = set(db.scalars(select(NewsItem.url).where(NewsItem.url.in_(list(fresh)))))
    added = 0
    for url, i in fresh.items():
        if url not in known:
            db.add(NewsItem(source=i.source, url=url, title=i.title, summary=i.summary, published_at=i.published_at, fetched_at=now))
            added += 1
    db.commit()
    return added


def fetch_news(db: Session, adapter: NewsAdapter, now: datetime, report: NewsReport) -> None:
    feeds: list[tuple[str, Callable[[], list[FeedItem]]]] = [("TuttoC", adapter.tuttoc)]
    playing = {t for m in upcoming_serie_c(db, now, GNEWS_AHEAD) for t in (m.home_team.name, m.away_team.name)}
    feeds += [(f"Google News {team}", lambda team=team: adapter.google_news(team)) for team in sorted(playing)]
    for label, read in feeds:
        try:
            items = read()
        except Exception as exc:  # noqa: BLE001 - un feed che non risponde non ferma gli altri
            report.errors.append(f"{label}: {exc}")
            continue
        report.fetched += len(items)
        report.new += store_items(db, items, now)


def process_news(db: Session, ai: Ai, model: str, now: datetime, report: NewsReport) -> None:
    """Fatti dalle notizie non ancora lette, a blocchi di 40."""
    teams = serie_c_teams(db, now)
    by_name = {normalize(name): team_id for team_id, name in teams.items()}
    todo = list(db.scalars(select(NewsItem).where(NewsItem.processed_at.is_(None), NewsItem.published_at >= now - ITEMS_MAX_AGE)
                          .order_by(NewsItem.published_at)))  # fmt: skip
    for start in range(0, len(todo), BATCH):
        batch = todo[start : start + BATCH]
        facts = extract_facts(ai, model, list(teams.values()), [NewsText(i.published_at, i.title, i.summary) for i in batch])
        for f in facts:
            team_id = by_name.get(normalize(f.team))
            if team_id is None or not 1 <= f.item <= len(batch):
                continue  # squadra fuori lista o notizia inesistente: si scarta
            item = batch[f.item - 1]
            db.add(TeamFact(team_id=team_id, news_id=item.id, kind=f.kind, player=f.player, detail=f.detail[:300],
                            published_at=item.published_at, created_at=now))  # fmt: skip
            report.facts += 1
        for item in batch:
            item.processed_at = now
        db.commit()
        report.processed += len(batch)


def team_facts(db: Session, team_id: int, now: datetime) -> list[TeamFact]:
    return list(db.scalars(select(TeamFact).where(TeamFact.team_id == team_id, TeamFact.published_at >= now - FACTS_WINDOW)
                           .order_by(TeamFact.published_at)))  # fmt: skip


def consensus_now(db: Session, match_id: int, closing: bool) -> dict[str, float] | None:
    book = load_book_odds(db, [match_id], closing=closing).get(match_id, {})
    return italian_consensus(book, "1X2")


def needs_judgment(last: MatchInsight | None, facts: Sequence[TeamFact], now: datetime) -> bool:
    """Si giudica se ci sono fatti e: mai giudicata, oppure fatti nuovi dopo l'ultimo giudizio e passate 12 ore."""
    if not facts:
        return False
    if last is None:
        return True
    return now - last.created_at >= JUDGE_EVERY and any(f.created_at > last.created_at for f in facts)


def refresh_insights(db: Session, ai: Ai, model: str, now: datetime, report: NewsReport) -> None:
    for m in upcoming_serie_c(db, now, JUDGE_AHEAD):
        if m.kickoff_at - now < SIGNAL_BEFORE:
            continue
        home, away = team_facts(db, m.home_team_id, now), team_facts(db, m.away_team_id, now)
        last = db.scalars(select(MatchInsight).where(MatchInsight.match_id == m.id).order_by(MatchInsight.created_at.desc())).first()
        if not needs_judgment(last, home + away, now):
            continue
        c = consensus_now(db, m.id, closing=False)
        if c is None:
            continue  # senza quote il giudizio non si può misurare (D101): si aspetta che arrivino, e non si spende
        as_text = lambda facts: [FactText(f.published_at, f.kind, f.player, f.detail) for f in facts]  # noqa: E731
        j = judge_match(ai, model, m.home_team.name, m.away_team.name, m.kickoff_at, as_text(home), as_text(away))
        db.add(MatchInsight(match_id=m.id, created_at=now, side=j.side, strength="" if j.side == "none" else j.strength, reason=j.reason,
                            facts=len(home) + len(away), p_home=c["1"], p_draw=c["X"], p_away=c["2"]))  # fmt: skip
        db.commit()
        report.judged += 1


def settle_insights(db: Session, now: datetime, report: NewsReport) -> None:
    """Consenso in chiusura per i giudizi delle partite iniziate (D101)."""
    rows = db.execute(select(MatchInsight, Match).join(Match, Match.id == MatchInsight.match_id)
                      .where(MatchInsight.close_home.is_(None), Match.kickoff_at <= now, Match.kickoff_at >= now - timedelta(days=7)))  # fmt: skip
    closing: dict[int, dict[str, float] | None] = {}
    for insight, match in rows:
        if match.id not in closing:
            closing[match.id] = consensus_now(db, match.id, closing=True)
        c = closing[match.id]
        if c:
            insight.close_home, insight.close_draw, insight.close_away = c["1"], c["X"], c["2"]
            report.settled += 1
    db.commit()


def run_news(db: Session, adapter: NewsAdapter, ai: Ai | None, extract_model: str, judge_model: str, now: datetime) -> NewsReport:
    """Un giro completo: notizie, fatti, giudizi, chiusure. Senza AI (chiave mancante o tetto raggiunto) solo raccolta e chiusure."""
    report = NewsReport()
    fetch_news(db, adapter, now, report)
    if ai is not None:
        try:
            process_news(db, ai, extract_model, now, report)
            refresh_insights(db, ai, judge_model, now, report)
        except BudgetExceeded as exc:
            report.errors.append(f"AI ferma: {exc}")
        except AiError as exc:
            report.errors.append(f"AI: {exc}")
    settle_insights(db, now, report)
    return report


# --- Prova D101 ---------------------------------------------------------------------------------------------------

@dataclass(frozen=True)
class FanSignal:
    match_id: int
    side: str
    strength: str
    p_signal: float
    p_close: float

    @property
    def move(self) -> float:
        return self.p_close - self.p_signal


def signals(rows: Sequence[tuple[MatchInsight, datetime]]) -> list[FanSignal]:
    """Il primo giudizio con un lato, almeno 30 minuti prima del calcio d'inizio, con consenso al momento e in chiusura."""
    first: dict[int, MatchInsight] = {}
    for insight, kickoff in sorted(rows, key=lambda r: r[0].created_at):
        if insight.side == "none" or insight.match_id in first or insight.created_at > kickoff - SIGNAL_BEFORE:
            continue
        first[insight.match_id] = insight
    out = []
    for i in first.values():
        p, c = (i.p_home, i.close_home) if i.side == "home" else (i.p_away, i.close_away)
        if p is not None and c is not None:
            out.append(FanSignal(i.match_id, i.side, i.strength, p, c))
    return out


def fan_test(db: Session) -> tuple[list[FanSignal], Estimate | None]:
    rows = db.execute(select(MatchInsight, Match.kickoff_at).join(Match, Match.id == MatchInsight.match_id)).all()
    found = signals([(i, k) for i, k in rows])
    if len(found) < 2:
        return found, None
    return found, clustered_mean([s.move for s in found], [s.match_id for s in found])
