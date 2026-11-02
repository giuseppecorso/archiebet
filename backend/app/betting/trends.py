"""Andamenti per i grafici delle statistiche (D170). Funzioni pure sulle giocate: i numeri li calcola il codice.

- saldo giorno per giorno (cumulato) delle schedine chiuse;
- vinte e perse per mese;
- CLV medio per settimana;
- selezioni per fascia di quota: quante ne azzecchi contro quante ne promette la quota (1 / quota).
"""

from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from app.betting.calc import LOST, VOID, WON
from app.models import Bet

ROME = ZoneInfo("Europe/Rome")

# Fasce di quota delle singole selezioni: (etichetta, da, fino a esclusa)
ODDS_BANDS: list[tuple[str, float, float]] = [
    ("fino a 1,50", 1.0, 1.5),
    ("1,50 – 2,00", 1.5, 2.0),
    ("2,00 – 3,00", 2.0, 3.0),
    ("3,00 – 5,00", 3.0, 5.0),
    ("oltre 5,00", 5.0, float("inf")),
]


@dataclass(frozen=True)
class DayPoint:
    day: date
    bets: int  # schedine chiuse quel giorno (rimborsate escluse)
    won: int
    profit: Decimal
    cum_profit: Decimal  # saldo dall'inizio del periodo


@dataclass(frozen=True)
class MonthPoint:
    month: str  # "2026-10"
    won: int
    lost: int


@dataclass(frozen=True)
class WeekClv:
    week: date  # lunedì della settimana in cui è stata giocata la schedina
    avg_clv: float
    count: int


@dataclass(frozen=True)
class OddsBand:
    label: str
    selections: int
    won: int
    hit_rate: float | None
    expected_rate: float | None  # media di 1 / quota: quanto "promette" la quota, margine compreso


@dataclass(frozen=True)
class Trends:
    days: list[DayPoint]
    months: list[MonthPoint]
    clv_weeks: list[WeekClv]
    odds_bands: list[OddsBand]


def _local_day(moment: datetime) -> date:
    return moment.astimezone(ROME).date()


def daily_balance(bets: Sequence[Bet]) -> list[DayPoint]:
    per_day: dict[date, list[Bet]] = defaultdict(list)
    for bet in bets:
        if bet.status in (WON, LOST) and bet.settled_at:
            per_day[_local_day(bet.settled_at)].append(bet)
    out, running = [], Decimal(0)
    for day in sorted(per_day):
        items = per_day[day]
        profit = sum(((b.payout or Decimal(0)) - b.stake for b in items), Decimal(0))
        running += profit
        out.append(DayPoint(day, len(items), sum(b.status == WON for b in items), profit, running))
    return out


def monthly_results(bets: Sequence[Bet]) -> list[MonthPoint]:
    won: dict[str, int] = defaultdict(int)
    lost: dict[str, int] = defaultdict(int)
    for bet in bets:
        if bet.status in (WON, LOST) and bet.settled_at:
            month = _local_day(bet.settled_at).strftime("%Y-%m")
            (won if bet.status == WON else lost)[month] += 1
    return [MonthPoint(m, won[m], lost[m]) for m in sorted(won.keys() | lost.keys())]


def weekly_clv(bets: Sequence[Bet]) -> list[WeekClv]:
    per_week: dict[date, list[float]] = defaultdict(list)
    for bet in bets:
        day = _local_day(bet.placed_at)
        monday = day - timedelta(days=day.weekday())
        per_week[monday] += [float(s.clv) for s in bet.selections if s.clv is not None]
    return [WeekClv(w, round(sum(v) / len(v), 4), len(v)) for w, v in sorted(per_week.items()) if v]


def odds_bands(bets: Sequence[Bet]) -> list[OddsBand]:
    selections = [s for b in bets for s in b.selections if s.status in (WON, LOST)]
    out = []
    for label, low, high in ODDS_BANDS:
        items = [s for s in selections if low <= float(s.odds) < high]
        n = len(items)
        won = sum(s.status == WON for s in items)
        out.append(
            OddsBand(
                label=label,
                selections=n,
                won=won,
                hit_rate=round(won / n, 4) if n else None,
                expected_rate=round(sum(1 / float(s.odds) for s in items) / n, 4) if n else None,
            )
        )
    return out


def trends(bets: Sequence[Bet]) -> Trends:
    bets = [b for b in bets if b.status != VOID]
    return Trends(daily_balance(bets), monthly_results(bets), weekly_clv(bets), odds_bands(bets))
