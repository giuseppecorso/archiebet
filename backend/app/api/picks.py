"""Pronostici (D67): la stima migliore per ogni partita in programma, con le quote di Sisal ed Eurobet."""

from datetime import UTC, datetime, time, timedelta
from typing import Literal
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Query
from pydantic import BaseModel
from sqlalchemy import select

from app.api.football import BOOKMAKER_LABELS, MatchCard, match_cards
from app.auth.deps import CurrentUser, DbSession
from app.config import get_settings
from app.forecast.multiple import multiple_of_the_day
from app.forecast.picks import MODEL_SOURCE, favorite
from app.forecast.picks_service import legs_for, upcoming_picks
from app.ingest.teams import competition_sort_key
from app.models import RadarSignal

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
    bookmakers = get_settings().radar_bookmaker_list
    upcoming = upcoming_picks(db, now, now + timedelta(days=days), bookmakers)
    matches = [m for m, _ in upcoming]
    ids = [m.id for m in matches]
    signals: dict[int, int] = {}
    for match_id in db.scalars(select(RadarSignal.match_id).where(RadarSignal.match_id.in_(ids))):
        signals[match_id] = signals.get(match_id, 0) + 1

    cards = {c.id: c for c in match_cards(db, matches, now)}
    out = []
    for m, market_picks in sorted(upcoming, key=lambda mp: (mp[0].kickoff_at, competition_sort_key(mp[0].competition))):
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


# ---------- Multipla del giorno (D68) ----------

ROME = ZoneInfo("Europe/Rome")


class LegOut(BaseModel):
    match: MatchCard
    market: str
    selection: str
    probability: float
    price: float
    value: float


class MultipleOut(BaseModel):
    bookmaker: str
    legs: list[LegOut]
    with_value: bool
    price: float
    win_probability: float
    one_in: float
    alive_before_last: float
    expected_value: float


class MultiplesOut(BaseModel):
    horizon: Literal["today", "week"]
    multiples: list[MultipleOut]  # una per bookmaker di Giuse
    missing: list[str]  # bookmaker per cui oggi non c'è una multipla sensata


def horizon_end(now: datetime, horizon: str) -> datetime:
    """Fine dell'orizzonte: mezzanotte italiana di oggi, oppure tra 7 giorni."""
    if horizon == "today":
        local = now.astimezone(ROME)
        return datetime.combine(local.date() + timedelta(days=1), time(0), ROME).astimezone(UTC)
    return now + timedelta(days=7)


@router.get("/multiple")
def multiple(_: CurrentUser, db: DbSession, horizon: Literal["today", "week"] = "today") -> MultiplesOut:
    now = datetime.now(UTC)
    bookmakers = get_settings().radar_bookmaker_list
    upcoming = upcoming_picks(db, now, horizon_end(now, horizon), bookmakers)
    cards = {c.id: c for c in match_cards(db, [m for m, _ in upcoming], now)}
    multiples, missing = [], []
    for bm in bookmakers:
        label = BOOKMAKER_LABELS.get(bm, bm)
        best = multiple_of_the_day(legs_for(upcoming, bm))
        if best is None:
            missing.append(label)
            continue
        multiples.append(
            MultipleOut(
                bookmaker=label,
                legs=[
                    LegOut(match=cards[leg.match_id], market=leg.market, selection=leg.selection,
                           probability=leg.probability, price=leg.price, value=leg.value)
                    for leg in best.legs
                ],
                with_value=best.with_value,
                price=best.price,
                win_probability=best.win_probability,
                one_in=best.one_in,
                alive_before_last=best.alive_before_last,
                expected_value=best.expected_value,
            )
        )
    return MultiplesOut(horizon=horizon, multiples=multiples, missing=missing)
