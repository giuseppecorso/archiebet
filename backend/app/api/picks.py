"""Pronostici (D67): la stima migliore per ogni partita in programma, con le quote di Sisal ed Eurobet."""

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Query
from pydantic import BaseModel
from sqlalchemy import select

from app.api.football import BOOKMAKER_LABELS, MatchCard, match_cards
from app.auth.deps import CurrentUser, DbSession
from app.config import get_settings
from app.forecast.picks import MODEL_SOURCE, favorite, match_picks
from app.forecast.radar_service import load_book_odds
from app.ingest.teams import competition_sort_key
from app.models import Match, MatchPrediction, MatchStatus, RadarSignal

router = APIRouter(prefix="/api/picks", tags=["pronostici"])

SOURCE_LABELS = BOOKMAKER_LABELS | {"archie": "Modello di Archie"}


class OfferOut(BaseModel):
    bookmaker: str
    price: float
    value: float
    verdict: str  # "valore" | "nella norma" | "paga poco"


class MarketOut(BaseModel):
    market: str
    source: str  # etichetta della fonte della probabilità
    from_model: bool
    probabilities: dict[str, float]
    offers: dict[str, list[OfferOut]]


class PickOut(BaseModel):
    match: MatchCard
    favorite: str | None  # esito 1X2 più probabile
    favorite_probability: float | None
    markets: list[MarketOut]
    signals: int  # occasioni del radar su questa partita


class PicksOut(BaseModel):
    bookmakers: list[str]
    picks: list[PickOut]


@router.get("")
def picks(_: CurrentUser, db: DbSession, days: int = Query(7, ge=1, le=14)) -> PicksOut:
    now = datetime.now(UTC)
    matches = list(
        db.scalars(
            select(Match)
            .where(Match.status == MatchStatus.SCHEDULED, Match.kickoff_at > now, Match.kickoff_at <= now + timedelta(days=days))
            .order_by(Match.kickoff_at, Match.id)
        )
    )
    ids = [m.id for m in matches]
    books = load_book_odds(db, ids, closing=False)
    models = {p.match_id: p.markets for p in db.scalars(select(MatchPrediction).where(MatchPrediction.match_id.in_(ids)))}
    signals: dict[int, int] = {}
    for match_id in db.scalars(select(RadarSignal.match_id).where(RadarSignal.match_id.in_(ids))):
        signals[match_id] = signals.get(match_id, 0) + 1
    bookmakers = get_settings().radar_bookmaker_list

    cards = {c.id: c for c in match_cards(db, matches, now)}
    out = []
    for m in sorted(matches, key=lambda m: (m.kickoff_at, competition_sort_key(m.competition))):
        market_picks = match_picks(books.get(m.id, {}), models.get(m.id), bookmakers)
        fav = favorite(market_picks)
        out.append(
            PickOut(
                match=cards[m.id],
                favorite=fav[0] if fav else None,
                favorite_probability=fav[1] if fav else None,
                markets=[
                    MarketOut(
                        market=p.market,
                        source=SOURCE_LABELS.get(p.source, p.source),
                        from_model=p.source == MODEL_SOURCE,
                        probabilities=p.probabilities,
                        offers={
                            sel: [OfferOut(bookmaker=BOOKMAKER_LABELS.get(o.bookmaker, o.bookmaker), price=o.price, value=o.value, verdict=o.verdict) for o in offers]
                            for sel, offers in p.offers.items()
                        },
                    )
                    for p in market_picks
                ],
                signals=signals.get(m.id, 0),
            )
        )
    return PicksOut(bookmakers=[BOOKMAKER_LABELS.get(b, b) for b in bookmakers], picks=out)
