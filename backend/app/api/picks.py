"""Pronostici (D67): la stima migliore per ogni partita in programma, con le quote di Sisal ed Eurobet."""

from datetime import UTC, date, datetime, time, timedelta
from typing import Literal
from zoneinfo import ZoneInfo

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app.api.football import BOOKMAKER_LABELS, MatchCard, match_cards
from app.auth.deps import CurrentUser, DbSession
from app.config import get_settings
from app.forecast.clv import SUSPICIOUS_VALUE
from app.forecast.data import ODDS_MARKETS
from app.forecast.multiple import LEGS, PROFILES, build_multiple
from app.forecast.picks import MODEL_SOURCE, PICK_MARKETS, favorite, off_line
from app.forecast.picks_service import legs_for, upcoming_picks
from app.ingest.teams import competition_sort_key

router = APIRouter(prefix="/api/picks", tags=["pronostici"])

SOURCE_LABELS = BOOKMAKER_LABELS | {"archie": "Modello di Archie", "consenso": "Media dei bookmaker italiani"}


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
    # Occasioni sui bookmaker di Giuse: esiti dei mercati del radar con almeno una quota "valore" (stessa regola, D72/D74)
    signals = {
        m.id: len({(p.market, sel) for p in mp if p.market in ODDS_MARKETS for sel, offers in p.offers.items() if any(o.verdict == "valore" for o in offers)})
        for m, mp in upcoming
    }

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


# Oggi, domani, oggi+domani, prossimi 3 giorni, 7 giorni, oppure dal giorno al giorno (D83)
Horizon = Literal["today", "tomorrow", "2days", "3days", "week", "range"]
MAX_DAYS_AHEAD = 7  # oltre non ci sono ancora quote


class MultiplesOut(BaseModel):
    horizon: Horizon
    profile: str
    legs: int
    multiples: list[MultipleOut]  # una per bookmaker di Giuse
    missing: list[str]  # bookmaker per cui oggi non c'è una multipla sensata


def _midnight(day: date) -> datetime:
    """Mezzanotte italiana all'inizio del giorno, in UTC."""
    return datetime.combine(day, time(0), ROME).astimezone(UTC)


def horizon_window(now: datetime, horizon: str, date_from: date | None = None, date_to: date | None = None) -> tuple[datetime, datetime]:
    """Da quando a quando cercare le partite: i giorni sono quelli italiani (finiscono a mezzanotte)."""
    today = now.astimezone(ROME).date()
    days = {"today": 1, "2days": 2, "3days": 3}
    if horizon in days:
        return now, _midnight(today + timedelta(days=days[horizon]))
    if horizon == "tomorrow":
        return _midnight(today + timedelta(days=1)), _midnight(today + timedelta(days=2))
    if horizon == "range":
        if date_from is None or date_to is None or date_to < date_from:
            raise ValueError("servono date_from e date_to, con date_to non prima di date_from")
        return max(now, _midnight(date_from)), min(_midnight(date_to + timedelta(days=1)), now + timedelta(days=MAX_DAYS_AHEAD))
    return now, now + timedelta(days=MAX_DAYS_AHEAD)


def horizon_end(now: datetime, horizon: str) -> datetime:
    """Fine dell'orizzonte (mezzanotte italiana di oggi, oppure tra 7 giorni, ...)."""
    return horizon_window(now, horizon)[1]


@router.get("/multiple")
def multiple(
    _: CurrentUser,
    db: DbSession,
    horizon: Horizon = "today",
    date_from: date | None = Query(None, description="Con horizon=range: primo giorno, AAAA-MM-GG"),
    date_to: date | None = Query(None, description="Con horizon=range: ultimo giorno, AAAA-MM-GG"),
    profile: Literal["tranquilla", "equilibrata", "coraggiosa"] = "equilibrata",
    legs: int = Query(LEGS, ge=2, le=6),
    markets: str | None = Query(None, description="Mercati separati da virgola, es. 1X2,DC"),
    competitions: str | None = Query(None, description="Codici dei campionati separati da virgola, es. ITA-A,ENG-1"),
) -> MultiplesOut:
    """Multipla del giorno (senza parametri) o generatore "Archie, fammi una multipla"."""
    now = datetime.now(UTC)
    bookmakers = get_settings().radar_bookmaker_list
    try:
        start, end = horizon_window(now, horizon, date_from, date_to)
    except ValueError as error:
        raise HTTPException(422, str(error)) from error
    upcoming = upcoming_picks(db, start, end, bookmakers)
    if competitions:
        wanted = set(competitions.split(","))
        upcoming = [(m, mp) for m, mp in upcoming if m.competition.code in wanted]
    if markets:
        allowed = set(markets.split(",")) & set(PICK_MARKETS)
        upcoming = [(m, [p for p in mp if p.market in allowed]) for m, mp in upcoming]
    cards = {c.id: c for c in match_cards(db, [m for m, _ in upcoming], now)}
    multiples, missing = [], []
    for bm in bookmakers:
        label = BOOKMAKER_LABELS.get(bm, bm)
        best = build_multiple(legs_for(upcoming, bm), legs, PROFILES[profile])
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
    return MultiplesOut(horizon=horizon, profile=profile, legs=legs, multiples=multiples, missing=missing)


# ---------- Quote fuori linea oggi (D70) ----------


class OffLineOut(BaseModel):
    match: MatchCard
    market: str
    selection: str
    probability: float
    bookmaker: str
    price: float
    value: float
    suspicious: bool  # sopra il 15%: probabile errore, rischio annullamento (regola 4)


@router.get("/off-line")
def off_line_today(_: CurrentUser, db: DbSession) -> list[OffLineOut]:
    """Quote di Sisal ed Eurobet di oggi molto sopra il giusto (≥ 8%)."""
    now = datetime.now(UTC)
    upcoming = upcoming_picks(db, now, horizon_end(now, "today"), get_settings().radar_bookmaker_list)
    cards = {c.id: c for c in match_cards(db, [m for m, _ in upcoming], now)}
    rows = [
        OffLineOut(
            match=cards[m.id], market=x.market, selection=x.selection, probability=x.probability,
            bookmaker=BOOKMAKER_LABELS.get(x.offer.bookmaker, x.offer.bookmaker), price=x.offer.price,
            value=x.offer.value, suspicious=x.offer.value > SUSPICIOUS_VALUE,
        )
        for m, market_picks in upcoming
        for x in off_line(market_picks)
    ]  # fmt: skip
    return sorted(rows, key=lambda r: r.value, reverse=True)
