"""Profilo e classifica tra amici (D161)."""

from datetime import datetime

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import select

from app.api.coins import _state
from app.auth.deps import CurrentUser, DbSession
from app.betting.coins import earned
from app.betting.profile import Badge, Month, Specialty, TeamRecord, badges, by_month, specialty, team_record
from app.betting.service import settle_open_bets
from app.models import Bet, Team, User, UserSettings

router = APIRouter(prefix="/api/profile", tags=["profile"])


class ProfileOut(BaseModel):
    username: str
    display_name: str | None = None
    since: datetime
    bets: int
    won: int
    lost: int
    coins: int
    premium_until: datetime
    premium_active: bool
    specialty: Specialty | None
    badges: list[Badge]
    months: list[Month]
    team: str | None
    team_record: TeamRecord | None


class LeaderRow(BaseModel):
    username: str  # il nome da mostrare, se c'è
    coins: int  # guadagnati in tutto
    bets: int
    hit_rate: float | None  # pronostici azzeccati su quelli chiusi
    me: bool


@router.get("")
def profile(user: CurrentUser, db: DbSession) -> ProfileOut:
    settle_open_bets(db)
    bets = list(db.scalars(select(Bet).where(Bet.user_id == user.id)))
    state = _state(db, user)
    settings = db.get(UserSettings, user.id)
    team = db.get(Team, settings.favorite_team_id) if settings and settings.favorite_team_id else None
    return ProfileOut(
        username=user.username, display_name=user.display_name, since=user.created_at, bets=len(bets), won=sum(b.status == "won" for b in bets),
        lost=sum(b.status == "lost" for b in bets), coins=state.balance, premium_until=state.premium_until,
        premium_active=state.premium_active, specialty=specialty(bets), badges=badges(bets), months=by_month(bets),
        team=team.name if team else None, team_record=team_record(bets, team.id) if team else None,
    )  # fmt: skip


@router.get("/leaderboard")
def leaderboard(user: CurrentUser, db: DbSession) -> list[LeaderRow]:
    """Classifica tra gli account dell'app: monete guadagnate, poi pronostici azzeccati."""
    rows = []
    for u in db.scalars(select(User)):
        bets = list(db.scalars(select(Bet).where(Bet.user_id == u.id)))
        closed = [s for b in bets for s in b.selections if s.status in ("won", "lost")]
        rows.append(LeaderRow(username=u.display_name or u.username, coins=sum(e.coins for e in earned(bets)), bets=len(bets),
                              hit_rate=round(sum(s.status == "won" for s in closed) / len(closed), 3) if closed else None, me=u.id == user.id))  # fmt: skip
    return sorted(rows, key=lambda r: (r.coins, r.hit_rate or 0), reverse=True)
