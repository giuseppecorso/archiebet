"""API delle giocate e delle impostazioni: dati PER UTENTE, ognuno vede solo i propri."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.api.football import MatchCard, match_cards, match_detail
from app.auth.deps import CurrentUser, DbSession
from app.betting.calc import MARKETS, potential_payout
from app.betting.service import BetError, BudgetStatus, BetSummary, SelectionInput, budget_status, create_bet, settle_open_bets, summarize
from app.models import Bet, BetSnapshot, Match, MatchOdds, Team, UserSettings
from app.adapters.football_data import season_of

router = APIRouter(prefix="/api", tags=["giocate"])

# Bookmaker italiani previsti dalle specifiche (sezione 3.6)
BOOKMAKERS = ["Sisal", "Eurobet", "bet365", "Snai", "Lottomatica", "Goldbet", "Betsson", "Planetwin365"]


# ---------- Modelli ----------


class SelectionIn(BaseModel):
    match_id: int
    market: Literal["1X2", "DC", "OU2.5", "GG"]
    pick: str
    odds: Decimal = Field(gt=1, max_digits=8, decimal_places=3)


class BetIn(BaseModel):
    kind: Literal["real", "simulated"]
    stake: Decimal = Field(gt=0, max_digits=10, decimal_places=2)
    bookmaker: str | None = Field(None, max_length=40)
    note: str | None = Field(None, max_length=300)
    selections: list[SelectionIn] = Field(min_length=1, max_length=20)


class SelectionOut(BaseModel):
    id: int
    match: MatchCard
    market: str
    pick: str
    odds: Decimal
    status: str
    fair_closing_odds: Decimal | None
    clv: Decimal | None


class BetOut(BaseModel):
    id: int
    kind: str
    stake: Decimal
    total_odds: Decimal
    potential_payout: Decimal
    bookmaker: str | None
    note: str | None
    status: str
    payout: Decimal | None
    placed_at: datetime
    settled_at: datetime | None
    selections: list[SelectionOut]


class BetCreated(BaseModel):
    bet: BetOut
    warnings: list[str]


class SummaryOut(BaseModel):
    period: str
    real: BetSummary
    simulated: BetSummary


class SettingsIO(BaseModel):
    weekly_budget: Decimal | None = Field(None, ge=0, max_digits=10, decimal_places=2)
    monthly_budget: Decimal | None = Field(None, ge=0, max_digits=10, decimal_places=2)
    favorite_team_id: int | None = None
    bookmakers: list[str] = []


class SettingsOut(SettingsIO):
    available_bookmakers: list[str]
    favorite_team_name: str | None


class Prefill(BaseModel):
    match: MatchCard
    markets: dict[str, list[str]]  # mercati ed esiti giocabili
    odds: dict[str, dict[str, float]]  # quote medie di mercato disponibili, per precompilare


# ---------- Utilità ----------


def _bet_out(db, bet: Bet) -> BetOut:
    now = datetime.now(UTC)
    cards = {c.id: c for c in match_cards(db, [s.match for s in bet.selections], now)}
    return BetOut(
        id=bet.id,
        kind=bet.kind,
        stake=bet.stake,
        total_odds=bet.total_odds,
        potential_payout=potential_payout(bet.stake, bet.total_odds),
        bookmaker=bet.bookmaker,
        note=bet.note,
        status=bet.status,
        payout=bet.payout,
        placed_at=bet.placed_at,
        settled_at=bet.settled_at,
        selections=[
            SelectionOut(
                id=s.id,
                match=cards[s.match_id],
                market=s.market,
                pick=s.pick,
                odds=s.odds,
                status=s.status,
                fair_closing_odds=s.fair_closing_odds,
                clv=s.clv,
            )
            for s in bet.selections
        ],
    )


def _own_bet(db, user_id: int, bet_id: int) -> Bet:
    bet = db.get(Bet, bet_id)
    if bet is None or bet.user_id != user_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Schedina non trovata")
    return bet


def _period_start(period: str, now: datetime) -> datetime | None:
    if period == "week":
        return now - timedelta(days=7)
    if period == "30d":
        return now - timedelta(days=30)
    if period == "season":
        start_year = season_of(now.date())
        return datetime(start_year, 7, 1, tzinfo=UTC)
    return None


# ---------- Giocate ----------


@router.get("/bets")
def list_bets(user: CurrentUser, db: DbSession, kind: Literal["real", "simulated"] | None = None) -> list[BetOut]:
    settle_open_bets(db)  # chiude subito ciò che ha già un risultato
    query = select(Bet).where(Bet.user_id == user.id).order_by(Bet.placed_at.desc())
    if kind:
        query = query.where(Bet.kind == kind)
    return [_bet_out(db, b) for b in db.scalars(query)]


@router.post("/bets", status_code=status.HTTP_201_CREATED)
def place_bet(body: BetIn, user: CurrentUser, db: DbSession) -> BetCreated:
    # Fotografia: quello che la pagina partita mostrava in questo momento, per ogni partita
    snapshot = {}
    for s in body.selections:
        try:
            snapshot[str(s.match_id)] = match_detail(s.match_id, user, db).model_dump(mode="json")
        except HTTPException:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Partita non trovata") from None
    try:
        bet = create_bet(
            db,
            user.id,
            body.kind,
            body.stake,
            [SelectionInput(s.match_id, s.market, s.pick, s.odds) for s in body.selections],
            bookmaker=body.bookmaker,
            note=body.note,
            snapshot=snapshot,
        )
    except BetError as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(error)) from None
    return BetCreated(bet=_bet_out(db, bet), warnings=budget_status(db, user.id).warnings if body.kind == "real" else [])


@router.get("/bets/summary")
def bets_summary(user: CurrentUser, db: DbSession, period: Literal["week", "30d", "season", "all"] = "all") -> SummaryOut:
    settle_open_bets(db)
    since = _period_start(period, datetime.now(UTC))
    query = select(Bet).where(Bet.user_id == user.id)
    if since:
        query = query.where(Bet.placed_at >= since)
    bets = db.scalars(query).all()
    return SummaryOut(
        period=period,
        real=summarize([b for b in bets if b.kind == "real"]),
        simulated=summarize([b for b in bets if b.kind == "simulated"]),
    )


@router.get("/bets/{bet_id}")
def get_bet(bet_id: int, user: CurrentUser, db: DbSession) -> BetOut:
    return _bet_out(db, _own_bet(db, user.id, bet_id))


@router.get("/bets/{bet_id}/snapshot")
def get_snapshot(bet_id: int, user: CurrentUser, db: DbSession) -> dict:
    _own_bet(db, user.id, bet_id)
    snap = db.scalar(select(BetSnapshot).where(BetSnapshot.bet_id == bet_id))
    if snap is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Nessuna fotografia per questa schedina")
    return {"taken_at": snap.taken_at.isoformat(), "matches": snap.data}


@router.delete("/bets/{bet_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_bet(bet_id: int, user: CurrentUser, db: DbSession) -> None:
    """Solo per correggere un errore: schedina aperta e nessuna partita ancora iniziata."""
    bet = _own_bet(db, user.id, bet_id)
    now = datetime.now(UTC)
    if bet.status != "open" or any(s.match.kickoff_at <= now for s in bet.selections):
        raise HTTPException(status.HTTP_409_CONFLICT, "Si può cancellare solo una schedina aperta prima che inizi la prima partita")
    db.delete(bet)
    db.commit()


# ---------- Budget e impostazioni ----------


@router.get("/budget")
def get_budget(user: CurrentUser, db: DbSession) -> BudgetStatus:
    return budget_status(db, user.id)


def _settings_out(db, settings: UserSettings | None) -> SettingsOut:
    team = db.get(Team, settings.favorite_team_id) if settings and settings.favorite_team_id else None
    return SettingsOut(
        weekly_budget=settings.weekly_budget if settings else None,
        monthly_budget=settings.monthly_budget if settings else None,
        favorite_team_id=team.id if team else None,
        bookmakers=settings.bookmakers if settings else [],
        available_bookmakers=BOOKMAKERS,
        favorite_team_name=team.name if team else None,
    )


@router.get("/settings")
def get_settings_(user: CurrentUser, db: DbSession) -> SettingsOut:
    return _settings_out(db, db.get(UserSettings, user.id))


@router.put("/settings")
def put_settings(body: SettingsIO, user: CurrentUser, db: DbSession) -> SettingsOut:
    if body.favorite_team_id is not None and db.get(Team, body.favorite_team_id) is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Squadra non trovata")
    unknown = set(body.bookmakers) - set(BOOKMAKERS)
    if unknown:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, f"Bookmaker sconosciuti: {', '.join(sorted(unknown))}")
    settings = db.get(UserSettings, user.id) or UserSettings(user_id=user.id)
    settings.weekly_budget = body.weekly_budget
    settings.monthly_budget = body.monthly_budget
    settings.favorite_team_id = body.favorite_team_id
    settings.bookmakers = body.bookmakers
    db.add(settings)
    db.commit()
    return _settings_out(db, settings)


# ---------- Quote per precompilare ----------


@router.get("/matches/{match_id}/prefill")
def prefill(match_id: int, _: CurrentUser, db: DbSession) -> Prefill:
    match = db.get(Match, match_id)
    if match is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Partita non trovata")
    odds: dict[str, dict[str, float]] = {}
    rows = db.execute(
        select(MatchOdds.market, MatchOdds.selection, MatchOdds.price).where(
            MatchOdds.match_id == match_id, MatchOdds.bookmaker == "market_avg", MatchOdds.is_closing.is_(False)
        )
    ).all()
    for market, selection, price in rows:
        odds.setdefault(market, {})[selection] = float(price)
    return Prefill(match=match_cards(db, [match], datetime.now(UTC))[0], markets={k: list(v) for k, v in MARKETS.items()}, odds=odds)
