"""Dove vinci e dove perdi, e le tue abitudini. Funzioni pure sulle giocate (i numeri li calcola il codice).

Due livelli di lettura:
- per SCHEDINA (numero di partite, bookmaker): rendimento vero = (tornato - giocato) / giocato;
- per SELEZIONE (mercato, campionato): precisione, CLV medio e rendimento "come singole"
  (come se ogni selezione fosse stata giocata da sola con la stessa puntata).
"""

from collections import Counter, defaultdict
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from decimal import Decimal

from app.betting.calc import LOST, VOID, WON
from app.models import Bet, BetSelection

MARKET_NAMES = {"1X2": "Esito finale", "DC": "Doppia chance", "OU1.5": "Under / Over 1.5", "OU2.5": "Under / Over 2.5", "OU3.5": "Under / Over 3.5", "GG": "Goal / NoGoal"}


@dataclass(frozen=True)
class BetGroup:
    """Rendimento di un gruppo di schedine chiuse."""

    label: str
    bets: int
    won: int
    staked: Decimal
    profit: Decimal
    roi: float | None


@dataclass(frozen=True)
class SelectionGroup:
    """Rendimento di un gruppo di selezioni chiuse (annullate escluse)."""

    label: str
    selections: int
    won: int
    hit_rate: float | None
    avg_odds: float | None
    flat_roi: float | None  # come singole a puntata fissa: (somma quote vinte - n) / n
    avg_clv: float | None
    clv_count: int


@dataclass(frozen=True)
class Habits:
    bets: int
    avg_stake: Decimal | None
    avg_odds: float | None  # quota media delle schedine
    multiple_share: float | None  # quota di schedine con più di una partita
    avg_selections: float | None
    top_market: str | None
    top_bookmaker: str | None
    top_teams: list[tuple[str, int]]  # squadre giocate più spesso (selezioni in cui compaiono)


def size_label(n: int) -> str:
    return {1: "Singole", 2: "Doppie", 3: "Triple"}.get(n, "4 o più partite")


def _ratio(a: Decimal | float, b: Decimal | float) -> float | None:
    return round(float(a) / float(b), 4) if b else None


def bet_groups(bets: Sequence[Bet], key: Callable[[Bet], str]) -> list[BetGroup]:
    groups: dict[str, list[Bet]] = defaultdict(list)
    for bet in bets:
        if bet.status in (WON, LOST):  # le rimborsate non contano: nessun rischio corso
            groups[key(bet)].append(bet)
    out = []
    for label, items in groups.items():
        staked = sum((b.stake for b in items), Decimal(0))
        returned = sum((b.payout or Decimal(0) for b in items), Decimal(0))
        out.append(
            BetGroup(
                label=label,
                bets=len(items),
                won=sum(b.status == WON for b in items),
                staked=staked,
                profit=returned - staked,
                roi=_ratio(returned - staked, staked),
            )
        )
    return sorted(out, key=lambda g: (-g.bets, g.label))


def selection_groups(selections: Sequence[BetSelection], key: Callable[[BetSelection], str]) -> list[SelectionGroup]:
    groups: dict[str, list[BetSelection]] = defaultdict(list)
    for sel in selections:
        if sel.status in (WON, LOST):
            groups[key(sel)].append(sel)
    out = []
    for label, items in groups.items():
        n = len(items)
        won = [s for s in items if s.status == WON]
        clvs = [s.clv for s in items if s.clv is not None]
        returned = sum((s.odds for s in won), Decimal(0))
        out.append(
            SelectionGroup(
                label=label,
                selections=n,
                won=len(won),
                hit_rate=_ratio(len(won), n),
                avg_odds=round(float(sum(s.odds for s in items) / n), 2),
                flat_roi=_ratio(returned - n, n),
                avg_clv=round(float(sum(clvs) / len(clvs)), 4) if clvs else None,
                clv_count=len(clvs),
            )
        )
    return sorted(out, key=lambda g: (-g.selections, g.label))


def habits(bets: Sequence[Bet], top: int = 5) -> Habits:
    n = len(bets)
    selections = [s for b in bets for s in b.selections]
    teams: Counter[str] = Counter()
    for s in selections:
        teams[s.match.home_team.name] += 1
        teams[s.match.away_team.name] += 1
    markets = Counter(MARKET_NAMES.get(s.market, s.market) for s in selections)
    books = Counter(b.bookmaker for b in bets if b.bookmaker)
    return Habits(
        bets=n,
        avg_stake=(sum((b.stake for b in bets), Decimal(0)) / n).quantize(Decimal("0.01")) if n else None,
        avg_odds=round(float(sum(b.total_odds for b in bets) / n), 2) if n else None,
        multiple_share=_ratio(sum(len(b.selections) > 1 for b in bets), n),
        avg_selections=round(len(selections) / n, 2) if n else None,
        top_market=markets.most_common(1)[0][0] if markets else None,
        top_bookmaker=books.most_common(1)[0][0] if books else None,
        top_teams=teams.most_common(top),
    )


@dataclass(frozen=True)
class Breakdown:
    by_size: list[BetGroup]
    by_bookmaker: list[BetGroup]
    by_market: list[SelectionGroup]
    by_competition: list[SelectionGroup]
    habits: Habits


def breakdown(bets: Sequence[Bet]) -> Breakdown:
    selections = [s for b in bets for s in b.selections if s.status != VOID]
    return Breakdown(
        by_size=bet_groups(bets, lambda b: size_label(len(b.selections))),
        by_bookmaker=bet_groups(bets, lambda b: b.bookmaker or "Non indicato"),
        by_market=selection_groups(selections, lambda s: MARKET_NAMES.get(s.market, s.market)),
        by_competition=selection_groups(selections, lambda s: s.match.competition.name),
        habits=habits(bets),
    )
