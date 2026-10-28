"""ArchieCoins e Premium (D159): saldo, monete guadagnate, riscatto di un mese di Premium."""

from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select

from app.auth.deps import CurrentUser, DbSession
from app.betting.coins import COUNTED_PER_DAY, MONTH_COST, TRIAL_DAYS, earned, extend, premium_until
from app.betting.service import settle_open_bets
from app.config import get_settings
from app.models import Bet, CoinRedemption

router = APIRouter(prefix="/api/coins", tags=["coins"])


class CoinRow(BaseModel):
    bet_id: int
    coins: int
    placed_at: datetime


class CoinsOut(BaseModel):
    balance: int
    earned: int
    spent: int
    month_cost: int
    counted_per_day: int
    trial_days: int
    premium_until: datetime
    premium_active: bool
    subscriptions_enabled: bool  # False = per ora tutto è gratis per tutti
    recent: list[CoinRow]  # le ultime giocate che hanno dato monete


def _state(db, user) -> CoinsOut:
    bets = list(db.scalars(select(Bet).where(Bet.user_id == user.id)))
    rows = earned(bets)
    total = sum(r.coins for r in rows)
    spent = db.scalar(select(func.coalesce(func.sum(CoinRedemption.coins), 0)).where(CoinRedemption.user_id == user.id)) or 0
    until = premium_until(user.created_at, user.premium_paid_until)
    placed = {b.id: b.placed_at for b in bets}
    recent = sorted((r for r in rows if r.coins), key=lambda r: placed[r.bet_id], reverse=True)[:10]
    return CoinsOut(balance=total - spent, earned=total, spent=spent, month_cost=MONTH_COST, counted_per_day=COUNTED_PER_DAY,
                    trial_days=TRIAL_DAYS, premium_until=until, premium_active=user.is_admin or until >= datetime.now(UTC),
                    subscriptions_enabled=get_settings().subscriptions_enabled,
                    recent=[CoinRow(bet_id=r.bet_id, coins=r.coins, placed_at=placed[r.bet_id]) for r in recent])  # fmt: skip


@router.get("")
def coins(user: CurrentUser, db: DbSession) -> CoinsOut:
    settle_open_bets(db)
    return _state(db, user)


@router.post("/redeem")
def redeem(user: CurrentUser, db: DbSession) -> CoinsOut:
    """Un mese di Premium in cambio di 1.000 ArchieCoins."""
    state = _state(db, user)
    if state.balance < MONTH_COST:
        raise HTTPException(422, f"Servono {MONTH_COST} ArchieCoins: ne hai {state.balance}")
    now = datetime.now(UTC)
    user.premium_paid_until = extend(premium_until(user.created_at, user.premium_paid_until), now)
    db.add(CoinRedemption(user_id=user.id, coins=MONTH_COST, what="premium-month", created_at=now))
    db.commit()
    return _state(db, user)
