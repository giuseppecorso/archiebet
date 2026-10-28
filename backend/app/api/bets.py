"""API delle giocate e delle impostazioni: dati PER UTENTE, ognuno vede solo i propri."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.api.football import MatchCard, match_cards, match_detail
from app.auth.deps import CurrentUser, DbSession
from app.betting.analysis import Breakdown, breakdown
from app.betting.calc import LOST, MARKETS, WON, at_least, potential_payout
from app.betting.service import BetError, BudgetStatus, BetSummary, SelectionInput, budget_status, create_bet, settle_open_bets, summarize
from app.betting.versus import JudgedPick, Versus, archie_probability, versus
from app.forecast.radar_markets import is_secondary
from app.models import Bet, BetSelection, BetSnapshot, Match, MatchOdds, Team, UserSettings
from app.adapters.football_data import season_of

router = APIRouter(prefix="/api", tags=["giocate"])

# Bookmaker italiani previsti dalle specifiche (sezione 3.6)
BOOKMAKERS = ["Sisal", "Eurobet", "bet365", "Snai", "Lottomatica", "Goldbet", "Betsson", "Planetwin365"]


# ---------- Modelli ----------


# 1X2, doppia chance, Draw No Bet, Under/Over dei gol e di una squadra, Gol/No gol, angoli e cartellini; l'esito lo controlla is_valid_pick
MARKET_PATTERN = r"^(1X2|DC|DNB|GG|OU[0-4]\.5|TG[HA]\d\.5|(COR|CRD)[HA]?\d{1,2}\.5|[12]T_(OU[01]\.5|TG[HA]0\.5)|MG\d-\d|CB_(1X|X2|1|2|GG)_[OU]\d\.5)$"


class SelectionIn(BaseModel):
    match_id: int
    market: str = Field(pattern=MARKET_PATTERN)
    pick: str
    odds: Decimal = Field(gt=1, max_digits=8, decimal_places=3)


class BetIn(BaseModel):
    kind: Literal["real", "simulated"] = "simulated"  # D159: niente più reale/simulata, resta per le giocate vecchie
    stake: Decimal = Field(gt=0, max_digits=10, decimal_places=2)
    bookmaker: str | None = Field(None, max_length=40)
    note: str | None = Field(None, max_length=300)
    selections: list[SelectionIn] = Field(min_length=1, max_length=20)
    system: int | None = Field(None, ge=2, le=19)  # sistema "k su n" (D157)


class SelectionOut(BaseModel):
    id: int
    match: MatchCard
    market: str
    pick: str
    odds: Decimal
    status: str
    fair_closing_odds: Decimal | None
    clv: Decimal | None
    probability: float | None = None  # probabilità che vinca adesso (termometro, D92); solo per le schedine aperte
    autopsy: "AutopsyOut | None" = None  # sfortuna o errore? (D113), solo a selezione chiusa


class AutopsyOut(BaseModel):
    verdict: str  # "giocata giusta" | "fortuna" | "sfortuna" | "ci sta" | "errore di prezzo" | "rimborsata" | "senza chiusura"
    probability: float | None
    text: str


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
    system: int | None = None  # sistema "k su n" (D157)
    hope: float | None = None  # termometro della speranza: probabilità di vincere adesso (solo aperte)
    live: bool = False  # almeno una partita della schedina è in corso


class BetCreated(BaseModel):
    bet: BetOut
    warnings: list[str]


class SummaryOut(BaseModel):
    period: str
    total: BetSummary  # tutte le giocate (D159)
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
    from app.forecast.live_service import hope, leg_probability, selection_states

    now = datetime.now(UTC)
    cards = {c.id: c for c in match_cards(db, [s.match for s in bet.selections], now)}
    states = selection_states(db, bet.selections, now) if bet.status == "open" else {}
    chance = hope(states.values()) if states else None
    if states and bet.system is not None:  # sistema: probabilità di indovinarne almeno k
        legs = [leg_probability(x) for x in states.values()]
        chance = None if None in legs else at_least(legs, bet.system)
    return BetOut(
        hope=chance,
        system=bet.system,
        live=any(c.live is not None for c in cards.values()),
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
                probability=leg_probability(states[s.id]) if s.id in states else None,
                autopsy=_autopsy(s),
            )
            for s in bet.selections
        ],
    )


def _autopsy(s: BetSelection) -> AutopsyOut | None:
    from app.betting.autopsy import SelectionFacts, autopsy

    if s.status == "open":
        return None
    from app.betting.service import CLV_WAIT

    m = s.match
    note = None
    if not s.fair_closing_odds:
        kickoff = m.kickoff_at if m.kickoff_at.tzinfo else m.kickoff_at.replace(tzinfo=UTC)
        note = "senza riferimento" if m.competition.code.startswith("ITA-C") else "in arrivo" if datetime.now(UTC) - kickoff < CLV_WAIT else None
    a = autopsy(SelectionFacts(s.market, s.pick, float(s.odds), s.status, float(s.fair_closing_odds) if s.fair_closing_odds else None,
                               m.home_shots_on_target, m.away_shots_on_target, m.home_goals, m.away_goals, note))  # fmt: skip
    return AutopsyOut(verdict=a.verdict, probability=a.probability, text=a.text)


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


class MyPickOut(BaseModel):
    """Una giocata dell'utente su una partita, per vederla nella lista delle partite (D155)."""

    match_id: int
    match: MatchCard  # la partita, per il filtro "Giocate" di Partite (anche di altri giorni)
    bet_id: int
    legs: int  # gambe della schedina (1 = singola)
    market: str
    pick: str
    state: Literal["waiting", "winning", "losing", "won", "lost", "void", "unknown"]
    probability: float | None  # probabilità che vinca adesso (termometro), se calcolabile


def now_state(market: str, pick: str, status: str, home_goals: int, away_goals: int) -> str:
    """Come andrebbe se finisse adesso: "winning" o "losing"; "unknown" per i mercati che il punteggio non decide
    (angoli, cartellini) o per quelli del secondo tempo prima della fine del primo."""
    from app.betting.calc import selection_outcome

    if is_secondary(market) or (market.startswith("2T_") and status in ("NS", "1H")):
        return "unknown"
    try:
        ht = (home_goals, away_goals) if market.startswith("1T_") and status == "1H" else None
        outcome = selection_outcome(market, pick, home_goals, away_goals, ht)
    except ValueError:
        return "unknown"
    return "winning" if outcome == "won" else "losing" if outcome == "lost" else "unknown"


@router.get("/bets/on-matches")
def my_picks_on_matches(user: CurrentUser, db: DbSession) -> list[MyPickOut]:
    """Le giocate aperte dell'utente, partita per partita, con come stanno andando adesso."""
    from app.forecast.live import leg_probability
    from app.forecast.live_service import selection_states

    bets = list(db.scalars(select(Bet).where(Bet.user_id == user.id, Bet.status == "open")))
    selections = [s for b in bets for s in b.selections]
    now = datetime.now(UTC)
    states = selection_states(db, selections, now)
    cards = {c.id: c for c in match_cards(db, list({s.match_id: s.match for s in selections}.values()), now)}
    out = []
    for b in bets:
        for sel in b.selections:
            st = states.get(sel.id)
            if sel.status in ("won", "lost", "void"):
                state = sel.status
            elif st is None or st.status == "NS":
                state = "waiting"
            else:
                state = now_state(sel.market, sel.pick, st.status, st.home_goals, st.away_goals)
            out.append(MyPickOut(match_id=sel.match_id, match=cards[sel.match_id], bet_id=b.id, legs=len(b.selections), market=sel.market, pick=sel.pick, state=state,
                                 probability=leg_probability(st) if st is not None and state not in ("waiting",) else None))  # fmt: skip
    return out


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
            system=body.system,
        )
    except BetError as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(error)) from None
    return BetCreated(bet=_bet_out(db, bet), warnings=[])  # D159: niente più limiti di spesa


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
        total=summarize(list(bets)),
        real=summarize([b for b in bets if b.kind == "real"]),
        simulated=summarize([b for b in bets if b.kind == "simulated"]),
    )


@router.get("/bets/breakdown")
def bets_breakdown(
    user: CurrentUser,
    db: DbSession,
    kind: Literal["real", "simulated"] | None = None,  # None = tutte (D159)
    period: Literal["week", "30d", "season", "all"] = "all",
) -> Breakdown:
    """Dove vinci e dove perdi + abitudini, per un tipo di giocata e un periodo."""
    settle_open_bets(db)
    query = select(Bet).where(Bet.user_id == user.id)
    if kind:
        query = query.where(Bet.kind == kind)
    since = _period_start(period, datetime.now(UTC))
    if since:
        query = query.where(Bet.placed_at >= since)
    return breakdown(db.scalars(query).all())


@router.get("/bets/versus")
def bets_versus(
    user: CurrentUser,
    db: DbSession,
    kind: Literal["real", "simulated"] | None = None,  # None = tutte (D159)
    period: Literal["week", "30d", "season", "all"] = "all",
) -> Versus:
    """Io contro Archie: selezioni chiuse giudicate con le probabilità di Archie al momento della giocata."""
    settle_open_bets(db)
    query = select(Bet).where(Bet.user_id == user.id)
    if kind:
        query = query.where(Bet.kind == kind)
    since = _period_start(period, datetime.now(UTC))
    if since:
        query = query.where(Bet.placed_at >= since)
    bets = db.scalars(query).all()
    snapshots = {s.bet_id: s.data for s in db.scalars(select(BetSnapshot).where(BetSnapshot.bet_id.in_([b.id for b in bets])))}
    judged, without = [], 0
    for bet in bets:
        for sel in bet.selections:
            if sel.status not in (WON, LOST):
                continue
            p = archie_probability(snapshots.get(bet.id, {}).get(str(sel.match_id)), sel.market, sel.pick)
            if p is None:
                without += 1
            else:
                judged.append(JudgedPick(p, float(sel.odds), sel.status == WON))
    return versus(judged, without)


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
