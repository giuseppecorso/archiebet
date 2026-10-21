"""Logica delle giocate: registrazione con fotografia, avvisi di budget, chiusura automatica, riepiloghi."""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.betting.calc import (
    LOST,
    OPEN,
    VOID,
    WON,
    bet_status,
    clv,
    fair_closing_odds,
    is_settled_by_goals,
    is_valid_pick,
    secondary_outcome,
    selection_outcome,
    settled_payout,
    total_odds,
)
from app.models import Bet, BetKind, BetSelection, BetSnapshot, Match, MatchOdds, MatchStatus, UserSettings

ROME = ZoneInfo("Europe/Rome")
MAX_SELECTIONS = 20


class BetError(ValueError):
    """Giocata non valida: il messaggio si mostra all'utente così com'è."""


@dataclass(frozen=True)
class SelectionInput:
    match_id: int
    market: str
    pick: str
    odds: Decimal


# ---------- Registrazione ----------


def create_bet(
    db: Session,
    user_id: int,
    kind: str,
    stake: Decimal,
    selections: Sequence[SelectionInput],
    bookmaker: str | None = None,
    note: str | None = None,
    snapshot: dict | None = None,
    now: datetime | None = None,
) -> Bet:
    now = now or datetime.now(UTC)
    if kind not in (BetKind.REAL, BetKind.SIMULATED):
        raise BetError("Tipo di giocata non valido")
    if stake <= 0:
        raise BetError("L'importo deve essere maggiore di zero")
    if not 1 <= len(selections) <= MAX_SELECTIONS:
        raise BetError(f"Una schedina ha da 1 a {MAX_SELECTIONS} partite")
    if len({s.match_id for s in selections}) != len(selections):
        raise BetError("La stessa partita compare due volte: una selezione per partita")
    for s in selections:
        if not is_valid_pick(s.market, s.pick):
            raise BetError(f"Esito '{s.pick}' non valido per il mercato '{s.market}'")
        if s.odds <= 1:
            raise BetError("Ogni quota deve essere maggiore di 1")
        match = db.get(Match, s.match_id)
        if match is None:
            raise BetError("Partita non trovata")
        if match.status != MatchStatus.SCHEDULED or match.kickoff_at <= now:
            raise BetError(f"{match.home_team.name} – {match.away_team.name} è già iniziata: si gioca solo prima del calcio d'inizio")

    bet = Bet(
        user_id=user_id,
        kind=kind,
        stake=stake,
        total_odds=total_odds([s.odds for s in selections]),
        bookmaker=bookmaker,
        note=note,
        placed_at=now,
        selections=[BetSelection(match_id=s.match_id, market=s.market, pick=s.pick, odds=s.odds) for s in selections],
    )
    db.add(bet)
    db.flush()
    if snapshot is not None:
        db.add(BetSnapshot(bet_id=bet.id, taken_at=now, data=snapshot))
    db.commit()
    return bet


# ---------- Budget (solo avvisi, mai blocchi: D39) ----------


def week_start(now: datetime) -> datetime:
    local = now.astimezone(ROME)
    monday = (local - timedelta(days=local.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
    return monday.astimezone(UTC)


def month_start_rome(now: datetime) -> datetime:
    return now.astimezone(ROME).replace(day=1, hour=0, minute=0, second=0, microsecond=0).astimezone(UTC)


def real_staked_since(db: Session, user_id: int, since: datetime) -> Decimal:
    total = db.scalar(
        select(func.coalesce(func.sum(Bet.stake), 0)).where(Bet.user_id == user_id, Bet.kind == BetKind.REAL, Bet.placed_at >= since)
    )
    return Decimal(str(total))


@dataclass(frozen=True)
class BudgetStatus:
    week_staked: Decimal
    week_budget: Decimal | None
    month_staked: Decimal
    month_budget: Decimal | None
    warnings: list[str]


def budget_status(db: Session, user_id: int, now: datetime | None = None) -> BudgetStatus:
    now = now or datetime.now(UTC)
    settings = db.get(UserSettings, user_id)
    week = real_staked_since(db, user_id, week_start(now))
    month = real_staked_since(db, user_id, month_start_rome(now))
    warnings = []
    if settings and settings.weekly_budget is not None and week > settings.weekly_budget:
        warnings.append(f"Questa settimana hai giocato {week:.2f} € reali, oltre il tuo limite di {settings.weekly_budget:.2f} €.")
    if settings and settings.monthly_budget is not None and month > settings.monthly_budget:
        warnings.append(f"Questo mese hai giocato {month:.2f} € reali, oltre il tuo limite di {settings.monthly_budget:.2f} €.")
    return BudgetStatus(
        week_staked=week,
        week_budget=settings.weekly_budget if settings else None,
        month_staked=month,
        month_budget=settings.monthly_budget if settings else None,
        warnings=warnings,
    )


# ---------- Chiusura automatica ----------


def _closing_prices(db: Session, match_id: int, market: str) -> dict[str, Decimal] | None:
    """Chiusura del mercato: media dei bookmaker (football-data) o, dove manca, Pinnacle (OddsPapi)."""
    for bookmaker in ("market_avg", "pinnacle"):
        rows = db.execute(
            select(MatchOdds.selection, MatchOdds.price).where(
                MatchOdds.match_id == match_id,
                MatchOdds.bookmaker == bookmaker,
                MatchOdds.market == market,
                MatchOdds.is_closing.is_(True),
            )
        ).all()
        if rows:
            return {sel: price for sel, price in rows}
    return None


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


STATS_WAIT = timedelta(days=14)  # angoli e cartellini: se le statistiche non arrivano entro 14 giorni la selezione si annulla


def settle_open_bets(db: Session, now: datetime | None = None) -> int:
    """Chiude le selezioni delle partite finite (o annullate) e poi le schedine. Restituisce le schedine chiuse."""
    now = now or datetime.now(UTC)
    open_selections = db.scalars(select(BetSelection).where(BetSelection.status == OPEN)).all()
    touched: set[int] = set()
    for sel in open_selections:
        match = sel.match
        if match.status == MatchStatus.FINISHED and match.home_goals is not None and not is_settled_by_goals(sel.market):
            status = secondary_outcome(sel.market, sel.pick, (match.home_corners, match.away_corners),
                                       (match.home_yellow, match.away_yellow), (match.home_red, match.away_red))
            if status is None:
                if now - _aware(match.kickoff_at) < STATS_WAIT:
                    continue  # statistiche di angoli e cartellini non ancora arrivate (football-data, qualche giorno)
                status = VOID
            sel.status = status
        elif match.status == MatchStatus.FINISHED and match.home_goals is not None:
            sel.status = selection_outcome(sel.market, sel.pick, match.home_goals, match.away_goals)
        elif match.status == MatchStatus.CANCELLED:
            sel.status = VOID
        else:
            continue
        fair = fair_closing_odds(
            sel.market, sel.pick, _closing_prices(db, match.id, "1X2"), _closing_prices(db, match.id, sel.market if sel.market not in ("1X2", "DC", "GG") else "OU2.5")
        )
        sel.fair_closing_odds = fair.quantize(Decimal("0.001")) if fair is not None else None
        sel.clv = clv(sel.odds, fair)
        touched.add(sel.bet_id)

    closed = 0
    for bet_id in touched:
        bet = db.get(Bet, bet_id)
        status = bet_status([s.status for s in bet.selections])
        if status != OPEN:
            bet.status = status
            bet.payout = settled_payout(bet.stake, [(s.status, s.odds) for s in bet.selections])
            bet.settled_at = now
            closed += 1
    db.commit()
    return closed


# ---------- Riepiloghi ----------


@dataclass(frozen=True)
class BetSummary:
    bets: int
    open: int
    settled: int
    won: int
    staked: Decimal  # solo schedine chiuse
    returned: Decimal
    profit: Decimal
    roi: float | None  # profitto / giocato
    win_rate: float | None
    avg_clv: float | None  # media del CLV delle selezioni che ce l'hanno
    clv_count: int


def summarize(bets: Sequence[Bet]) -> BetSummary:
    settled = [b for b in bets if b.status in (WON, LOST, VOID)]
    staked = sum((b.stake for b in settled if b.status != VOID), Decimal(0))
    returned = sum((b.payout or Decimal(0) for b in settled if b.status != VOID), Decimal(0))
    decided = [b for b in settled if b.status != VOID]
    clvs = [s.clv for b in bets for s in b.selections if s.clv is not None]
    return BetSummary(
        bets=len(bets),
        open=sum(b.status == OPEN for b in bets),
        settled=len(settled),
        won=sum(b.status == WON for b in bets),
        staked=staked,
        returned=returned,
        profit=returned - staked,
        roi=round(float((returned - staked) / staked), 4) if staked else None,
        win_rate=round(sum(b.status == WON for b in decided) / len(decided), 4) if decided else None,
        avg_clv=round(float(sum(clvs) / len(clvs)), 4) if clvs else None,
        clv_count=len(clvs),
    )
