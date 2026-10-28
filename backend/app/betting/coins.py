"""ArchieCoins e Premium (D159). Funzioni pure.

Si guadagnano monete con le giocate vinte, e la puntata non conta: chi punta di più non guadagna di più (principio 7).
Monete di una giocata vinta = 10 × la quota (per un sistema, 10 × quanto è tornato diviso la puntata). Così in media
ogni giocata vale lo stesso, a quota 1,50 come a quota 50: guadagna di più solo chi prevede meglio del caso.
Contano le prime 10 giocate di ogni giorno: giocarne cento non serve.
"""

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

ROME = ZoneInfo("Europe/Rome")
COINS_PER_ODD = 10
COUNTED_PER_DAY = 10
MONTH_COST = 1000  # monete per un mese di Premium
TRIAL_DAYS = 15
MONTH_DAYS = 30


def coins_for(status: str, total_odds: Decimal, stake: Decimal, payout: Decimal | None, system: int | None) -> int:
    if status != "won":
        return 0
    if system is not None:
        return round(COINS_PER_ODD * float((payout or 0) / stake)) if stake else 0
    return round(COINS_PER_ODD * float(total_odds))


@dataclass(frozen=True)
class Earned:
    bet_id: int
    coins: int
    counted: bool  # False = oltre le 10 giocate del giorno


def earned(bets: Iterable) -> list[Earned]:
    """`bets`: oggetti con id, placed_at, status, total_odds, stake, payout, system."""
    per_day: dict = defaultdict(int)
    out = []
    for b in sorted(bets, key=lambda b: (b.placed_at, b.id)):
        day = b.placed_at.astimezone(ROME).date()
        per_day[day] += 1
        counted = per_day[day] <= COUNTED_PER_DAY
        out.append(Earned(b.id, coins_for(b.status, b.total_odds, b.stake, b.payout, b.system) if counted else 0, counted))
    return out


def premium_until(created_at: datetime, paid_until: datetime | None) -> datetime:
    """Fino a quando l'utente ha tutto: prova gratuita di 15 giorni dall'iscrizione, poi mesi riscattati o pagati."""
    trial = created_at + timedelta(days=TRIAL_DAYS)
    return max(trial, paid_until) if paid_until else trial


def extend(current_until: datetime, now: datetime, months: int = 1) -> datetime:
    """Un mese in più, da adesso se è già scaduto."""
    return max(current_until, now) + timedelta(days=MONTH_DAYS * months)
