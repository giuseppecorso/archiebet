"""Fammi una multipla (D137): pronostici studiati da Archie, per livello, con la spiegazione."""

from datetime import UTC, date, datetime
from typing import Literal

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app.api.football import BOOKMAKER_LABELS, MatchCard, _news_counts, match_cards
from app.api.picks import ROME, Horizon, horizon_window
from app.auth.deps import CurrentUser, DbSession, PremiumUser
from app.betting.calc import market_name
from app.forecast.study import LEVELS, THEMES, auto_legs, choose_multiple, leg_price, theme_market, theme_match, up_to_target, within_range
from app.forecast.study_service import _aware, load_studies
from app.ingest.teams import CUP_COUNTRY
from app.models import Match, MatchStudy

router = APIRouter(prefix="/api/study", tags=["studio"])

MAX_LEGS = 30

Level = Literal["cauto", "equilibrato", "rischioso"]
Theme = Literal["tutte", "primo_tempo", "gol", "maggiori", "minori", "coppe", "notizie"]


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
    avg_price: float | None = None  # quota media dei bookmaker che quotano il pronostico


class StudyMultipleOut(BaseModel):
    level: str
    legs: list[StudyLegOut]
    win_probability: float  # le partite sono indipendenti: prodotto delle probabilità di Archie
    totals: dict[str, float]  # quota totale per bookmaker, solo se quota tutte le gambe
    more: bool  # ci sono altre partite per "genera un'altra multipla"
    total_odds: float  # quota totale: migliore quota di ogni gamba, o quella giusta dello studio dove manca
    target_reached: bool = True  # con la quota obiettivo: ci è arrivata?


def _labelled(prices: dict[str, float]) -> dict[str, float]:
    """Quote per nome mostrato: se due bookmaker hanno lo stesso nome ("Altri bookmakers") resta la migliore."""
    out: dict[str, float] = {}
    for bm, price in prices.items():
        label = BOOKMAKER_LABELS.get(bm, bm)
        out[label] = max(out.get(label, 0.0), price)
    return out


def _leg(card: MatchCard, pick: dict) -> StudyLegOut:
    return StudyLegOut(
        match=card, market=pick["market"], selection=pick["selection"], market_label=market_name(pick["market"]),
        event=pick["event"], level=pick["level"], p_archie=pick["p_archie"], p_model=pick["p_model"],
        evidence=pick["evidence"], reasons=pick["reasons"], prices=_labelled(pick["prices"]),
        avg_price=round(sum(pick["prices"].values()) / len(pick["prices"]), 2) if pick["prices"] else None,
    )  # fmt: skip


@router.get("/multiple")
def study_multiple(
    _: PremiumUser,  # Premium (D159)
    db: DbSession,
    level: Level = "equilibrato",
    legs: int = Query(4, ge=1, le=MAX_LEGS),
    horizon: Horizon = "today",
    date_from: date | None = None,
    date_to: date | None = None,
    competitions: str | None = Query(None, description="codici separati da virgola"),
    days: str | None = Query(None, description="giorni scelti (italiani), AAAA-MM-GG separati da virgola: prevale su horizon"),
    exclude: str | None = Query(None, description="partite già proposte, id separati da virgola"),
    theme: Theme = "tutte",
    target: float | None = Query(None, gt=1, le=100000, description="quota totale obiettivo: Archie aggiunge gambe finché ci arriva"),
    target_max: float | None = Query(None, gt=1, le=100000, description="con target: quota totale massima (moltiplicatore da target a target_max)"),
    auto: bool = Query(False, description="Archie decide quante partite: finché la multipla esce abbastanza spesso per il livello"),
) -> StudyMultipleOut:
    now = datetime.now(UTC)
    chosen_days: set[date] = set()
    try:
        if days:
            chosen_days = {date.fromisoformat(d.strip()) for d in days.split(",") if d.strip()}
            start, end = horizon_window(now, "range", min(chosen_days), max(chosen_days))
        else:
            start, end = horizon_window(now, horizon, date_from, date_to)
    except ValueError as error:
        raise HTTPException(422, str(error)) from error
    studies = load_studies(db, start, end, competitions.split(",") if competitions else None)
    if chosen_days:  # giorni non consecutivi: solo quelli scelti
        studies = [(m, d) for m, d in studies if _aware(m.kickoff_at).astimezone(ROME).date() in chosen_days]
    skip = {int(x) for x in exclude.split(",") if x.strip().isdigit()} if exclude else set()
    news = _news_counts(db, [m for m, _ in studies], now) if theme == "notizie" else {}
    pool = [(m.id, [p for p in d["picks"] if theme_market(theme, p["market"])]) for m, d in studies
            if theme_match(theme, m.competition.tier, m.competition.country == CUP_COUNTRY, news.get(m.id, 0))]  # fmt: skip
    if auto and not target:
        chosen = auto_legs(choose_multiple(pool, level, MAX_LEGS, skip), level)
    elif target and target_max and target_max >= target:
        chosen = within_range(choose_multiple(pool, level, MAX_LEGS, skip), target, target_max)
    elif target:
        chosen = up_to_target(choose_multiple(pool, level, MAX_LEGS, skip), target)
    else:
        chosen = choose_multiple(pool, level, legs, skip)
    total_odds = 1.0
    for _, pick in chosen:
        total_odds *= leg_price(pick)
    matches = {m.id: m for m, _ in studies}
    chosen.sort(key=lambda c: matches[c[0]].kickoff_at)
    cards = {c.id: c for c in match_cards(db, [matches[mid] for mid, _ in chosen], now)}
    out = [_leg(cards[mid], pick) for mid, pick in chosen]
    probability = 1.0
    for leg in out:
        probability *= leg.p_archie
    totals = {}
    for label in dict.fromkeys(BOOKMAKER_LABELS[bm] for bm in ("sisal", "eurobet")):
        if out and all(label in leg.prices for leg in out):
            total = 1.0
            for leg in out:
                total *= leg.prices[label]
            totals[label] = round(total, 2)
    remaining = choose_multiple(pool, level, 1, skip | {mid for mid, _ in chosen})
    return StudyMultipleOut(level=level, legs=out, win_probability=round(probability, 4) if out else 0.0, totals=totals, more=bool(remaining),
                            total_odds=round(total_odds, 2) if chosen else 0.0, target_reached=not target or (total_odds >= target and (not target_max or total_odds <= target_max)))


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


@router.get("/themes")
def study_themes(_: CurrentUser) -> dict[str, str]:
    """Temi delle multiple: chiave → nome da mostrare."""
    return THEMES
