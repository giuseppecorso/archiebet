"""Archie tifoso (D101-D102): i fatti delle due squadre e il giudizio di Archie per la pagina partita; stato della prova."""

from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy import select

from app.auth.deps import CurrentUser, DbSession
from app.ingest.news import FACTS_WINDOW, TARGET_SIGNALS, fan_test
from app.models import Match, MatchInsight, NewsItem, TeamFact

router = APIRouter(prefix="/api/fan", tags=["archie tifoso"])

KIND_LABELS = {
    "assente": "Assente",
    "rientro": "Rientro",
    "squalifica": "Squalifica",
    "allenatore_nuovo": "Nuovo allenatore",
    "allenatore_in_bilico": "Allenatore in bilico",
    "societa_in_crisi": "Società in difficoltà",
    "penalizzazione": "Penalizzazione",
    "acquisto": "Acquisto",
    "cessione": "Cessione",
    "clima_positivo": "Clima positivo",
    "clima_negativo": "Clima negativo",
}


class FactOut(BaseModel):
    team_id: int
    kind: str
    label: str
    player: str | None
    detail: str
    published_at: datetime
    url: str
    source: str


class InsightOut(BaseModel):
    created_at: datetime
    side: str  # "home" | "away" | "none"
    strength: str
    reason: str


class FanTestOut(BaseModel):
    signals: int
    target: int
    mean_move: float | None  # punti di probabilità verso il lato indicato (0,01 = un punto)
    std_error: float | None


class MatchFanOut(BaseModel):
    facts: list[FactOut]
    insight: InsightOut | None
    test: FanTestOut


def _test(db) -> FanTestOut:
    found, est = fan_test(db)
    return FanTestOut(signals=len(found), target=TARGET_SIGNALS, mean_move=est.mean if est else None, std_error=est.std_error if est else None)


@router.get("/test")
def fan_test_status(_: CurrentUser, db: DbSession) -> FanTestOut:
    return _test(db)


@router.get("/match/{match_id}")
def match_fan(match_id: int, _: CurrentUser, db: DbSession) -> MatchFanOut:
    match = db.get(Match, match_id)
    if match is None:
        raise HTTPException(status_code=404, detail="Partita non trovata")
    # Fatti dei 10 giorni prima della partita (o di oggi, se è ancora lontana)
    until = min(match.kickoff_at, datetime.now(UTC))
    rows = db.execute(
        select(TeamFact, NewsItem).join(NewsItem, NewsItem.id == TeamFact.news_id)
        .where(TeamFact.team_id.in_([match.home_team_id, match.away_team_id]), TeamFact.published_at >= until - FACTS_WINDOW,
               TeamFact.published_at <= match.kickoff_at)
        .order_by(TeamFact.published_at.desc())
    ).all()  # fmt: skip
    facts = [FactOut(team_id=f.team_id, kind=f.kind, label=KIND_LABELS.get(f.kind, f.kind), player=f.player, detail=f.detail,
                     published_at=f.published_at, url=n.url, source=n.source) for f, n in rows]  # fmt: skip
    last = db.scalars(select(MatchInsight).where(MatchInsight.match_id == match_id).order_by(MatchInsight.created_at.desc())).first()
    insight = InsightOut(created_at=last.created_at, side=last.side, strength=last.strength, reason=last.reason) if last else None
    return MatchFanOut(facts=facts, insight=insight, test=_test(db))
