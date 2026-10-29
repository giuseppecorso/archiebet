"""Il profilo di chi gioca (D161): specialità, traguardi, andamento per mese. Funzioni pure.

`bets` sono oggetti con id, placed_at, status, total_odds, stake, payout, system e selections (market, status, match).
"""

from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from app.betting.coins import ROME, earned

FAMILIES = (  # (prefisso del mercato, nome della famiglia), il primo che combacia vince
    ("1T_", "Primo e secondo tempo"), ("2T_", "Primo e secondo tempo"), ("MG", "Multigol"), ("CB_", "Combo"),
    ("COR", "Angoli e cartellini"), ("CRD", "Angoli e cartellini"), ("TG", "Gol delle squadre"), ("OU", "Under / Over"),
    ("GG", "Goal / No goal"), ("1X2", "Esito finale"), ("DC", "Esito finale"), ("DNB", "Esito finale"),
)  # fmt: skip
MIN_FOR_SPECIALTY = 5  # pronostici chiusi in una famiglia per giudicarla


def family(market: str) -> str:
    return next((name for prefix, name in FAMILIES if market.startswith(prefix)), "Altro")


@dataclass(frozen=True)
class Specialty:
    name: str
    won: int
    closed: int


def specialty(bets: Iterable) -> Specialty | None:
    """La famiglia di mercati in cui azzecchi di più (almeno 5 pronostici chiusi)."""
    won, closed = defaultdict(int), defaultdict(int)
    for b in bets:
        for s in b.selections:
            if s.status in ("won", "lost"):
                closed[family(s.market)] += 1
                won[family(s.market)] += s.status == "won"
    ok = [(won[f] / closed[f], closed[f], f) for f in closed if closed[f] >= MIN_FOR_SPECIALTY]
    if not ok:
        return None
    _, _, best = max(ok)
    return Specialty(best, won[best], closed[best])


@dataclass(frozen=True)
class Badge:
    key: str
    title: str
    text: str
    got: bool


def badges(bets: Sequence) -> list[Badge]:
    closed = sorted((b for b in bets if b.status in ("won", "lost")), key=lambda b: (b.placed_at, b.id))
    won = [b for b in closed if b.status == "won"]
    streak = best = 0
    for b in closed:
        streak = streak + 1 if b.status == "won" else 0
        best = max(best, streak)
    coins = sum(e.coins for e in earned(bets))
    return [
        Badge("prima", "Prima vittoria", "Vinci la tua prima giocata", bool(won)),
        Badge("dieci", "Abituale", "Registra 10 giocate", len(bets) >= 10),
        Badge("serie", "In serie", "Vinci 5 giocate di fila", best >= 5),
        Badge("colpo", "Il colpo", "Vinci una giocata a quota 10 o più", any(float(b.total_odds) >= 10 for b in won)),
        Badge("cento", "Cento monete", "Arriva a 100 ArchieCoins guadagnati", coins >= 100),
        Badge("mille", "Mille monete", "Arriva a 1.000 ArchieCoins guadagnati", coins >= 1000),
    ]


@dataclass(frozen=True)
class Month:
    month: str  # AAAA-MM
    bets: int
    won: int
    coins: int


def by_month(bets: Sequence) -> list[Month]:
    coins = {e.bet_id: e.coins for e in earned(bets)}
    rows: dict[str, list[int]] = defaultdict(lambda: [0, 0, 0])
    for b in bets:
        key = b.placed_at.astimezone(ROME).strftime("%Y-%m")
        rows[key][0] += 1
        rows[key][1] += b.status == "won"
        rows[key][2] += coins.get(b.id, 0)
    return [Month(k, *v) for k, v in sorted(rows.items())]


@dataclass(frozen=True)
class TeamRecord:
    picks: int
    won: int
    lost: int


def team_record(bets: Iterable, team_id: int) -> TeamRecord:
    """I tuoi pronostici sulle partite della squadra del cuore."""
    picks = won = lost = 0
    for b in bets:
        for s in b.selections:
            if team_id in (s.match.home_team_id, s.match.away_team_id):
                picks += 1
                won += s.status == "won"
                lost += s.status == "lost"
    return TeamRecord(picks, won, lost)
