"""Fammi una multipla (D137): pronostici studiati da Archie, per livello, con la spiegazione."""

from datetime import UTC, date, datetime
from typing import Literal

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app.api.football import MatchCard, match_cards
from app.api.picks import Horizon, horizon_window
from app.auth.deps import CurrentUser, DbSession
from app.betting.calc import market_name
from app.forecast.study import LEVELS, choose_multiple
from app.forecast.study_service import load_studies
from app.models import Match, MatchStudy

router = APIRouter(prefix="/api/study", tags=["studio"])

BOOKMAKER_LABELS = {"sisal": "Sisal", "eurobet": "Eurobet"}
MAX_LEGS = 30

Level = Literal["cauto", "equilibrato", "rischioso"]


class StudyLegOut(BaseModel):
    match: MatchCard
    market: str
    selection: str
    market_label: str
    event: str  # il pronostico detto a parole
    level: str
    p_archie: float  # probabilità dello studio
    p_model: float  # solo il modello dei gol
    evidence: list[int]  # [volte in casa, partite in casa, volte in trasferta, partite in trasferta]
    reasons: list[str]
    prices: dict[str, float]  # quote di Sisal ed Eurobet, se il bookmaker quota il mercato


class StudyMultipleOut(BaseModel):
    level: str
    legs: list[StudyLegOut]
    win_probability: float  # le partite sono indipendenti: prodotto delle probabilità di Archie
    totals: dict[str, float]  # quota totale per bookmaker, solo se quota tutte le gambe
    more: bool  # ci sono altre partite per "genera un'altra multipla"


def _leg(card: MatchCard, pick: dict) -> StudyLegOut:
    return StudyLegOut(
        match=card, market=pick["market"], selection=pick["selection"], market_label=market_name(pick["market"]),
        event=pick["event"], level=pick["level"], p_archie=pick["p_archie"], p_model=pick["p_model"],
        evidence=pick["evidence"], reasons=pick["reasons"], prices={BOOKMAKER_LABELS.get(k, k): v for k, v in pick["prices"].items()},
    )  # fmt: skip


@router.get("/multiple")
def study_multiple(
    _: CurrentUser,
    db: DbSession,
    level: Level = "equilibrato",
    legs: int = Query(4, ge=1, le=MAX_LEGS),
    horizon: Horizon = "today",
    date_from: date | None = None,
    date_to: date | None = None,
    competitions: str | None = Query(None, description="codici separati da virgola"),
    exclude: str | None = Query(None, description="partite già proposte, id separati da virgola"),
) -> StudyMultipleOut:
    now = datetime.now(UTC)
    try:
        start, end = horizon_window(now, horizon, date_from, date_to)
    except ValueError as error:
        raise HTTPException(422, str(error)) from error
    studies = load_studies(db, start, end, competitions.split(",") if competitions else None)
    skip = {int(x) for x in exclude.split(",") if x.strip().isdigit()} if exclude else set()
    chosen = choose_multiple([(m.id, d["picks"]) for m, d in studies], level, legs, skip)
    matches = {m.id: m for m, _ in studies}
    chosen.sort(key=lambda c: matches[c[0]].kickoff_at)
    cards = {c.id: c for c in match_cards(db, [matches[mid] for mid, _ in chosen], now)}
    out = [_leg(cards[mid], pick) for mid, pick in chosen]
    probability = 1.0
    for leg in out:
        probability *= leg.p_archie
    totals = {}
    for label in BOOKMAKER_LABELS.values():
        if out and all(label in leg.prices for leg in out):
            total = 1.0
            for leg in out:
                total *= leg.prices[label]
            totals[label] = round(total, 2)
    remaining = choose_multiple([(m.id, d["picks"]) for m, d in studies], level, 1, skip | {mid for mid, _ in chosen})
    return StudyMultipleOut(level=level, legs=out, win_probability=round(probability, 4) if out else 0.0, totals=totals, more=bool(remaining))


@router.get("/match/{match_id}")
def study_match_picks(match_id: int, _: CurrentUser, db: DbSession) -> dict[str, list[StudyLegOut]]:
    """I pronostici studiati di una partita, il migliore per livello e gli altri."""
    match = db.get(Match, match_id)
    study = db.get(MatchStudy, match_id)
    if match is None or study is None:
        return {level: [] for level in LEVELS}
    [card] = match_cards(db, [match], datetime.now(UTC))
    from app.forecast.study import pick_strength

    return {level: [_leg(card, p) for p in sorted((p for p in study.data["picks"] if p["level"] == level), key=pick_strength, reverse=True)[:5]]
            for level in LEVELS}  # fmt: skip
