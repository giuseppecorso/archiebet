"""Regolamento personale (Fase 6, D114): regole di gioco dell'utente controllate prima di "L'ho giocata".

Le regole si scrivono a mano o nascono dai dati: Archie suggerisce di evitare i gruppi di giocate (mercato, campionato,
schedine lunghe, quote sotto il giusto) dove l'utente ha perso valore con abbastanza giocate da fidarsi. Solo avvisi, mai
blocchi (come per il budget, D39).
"""

from collections import defaultdict
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from decimal import Decimal

from app.models import Bet, Match
from app.betting.calc import market_name

KINDS = ("max_legs", "max_total_odds", "max_stake", "avoid_market", "avoid_competition", "avoid_team", "no_low_price")
MARKET_NAMES = {"1X2": "1X2", "DC": "doppia chance", "OU1.5": "Under/Over 1.5", "OU2.5": "Under/Over 2.5", "OU3.5": "Under/Over 3.5", "GG": "Gol/No gol"}
MIN_SELECTIONS = 10  # un gruppo si giudica da almeno 10 selezioni chiuse con CLV
MIN_LONG_BETS = 8
BAD_CLV = -0.02  # CLV medio sotto -2%: si perde valore
BAD_ROI_LONG = -0.30


@dataclass(frozen=True)
class Rule:
    kind: str
    value: str  # numero o codice, come testo
    reason: str = ""


@dataclass(frozen=True)
class DraftSelection:
    match: Match
    market: str
    pick: str
    odds: float


def describe(rule: Rule, team_names: dict[int, str] | None = None) -> str:
    v = rule.value
    return {
        "max_legs": f"Al massimo {v} partite per schedina",
        "max_total_odds": f"Quota totale al massimo {v}",
        "max_stake": f"Puntata al massimo {v} €",
        "avoid_market": f"Evita il mercato {(MARKET_NAMES.get(v) or market_name(v))}",
        "avoid_competition": f"Evita il campionato {v}",
        "avoid_team": f"Niente partite di {(team_names or {}).get(int(v), 'questa squadra') if v.isdigit() else v}",
        "no_low_price": "Solo quote non sotto il giusto",
    }.get(rule.kind, rule.kind)


def violations(rules: Sequence[Rule], stake: Decimal, selections: Sequence[DraftSelection],
               value_of: Callable[[DraftSelection], float | None], team_names: dict[int, str] | None = None) -> list[str]:  # fmt: skip
    """Avvisi per una schedina in preparazione: una frase per ogni regola violata."""
    out = []
    total = 1.0
    for s in selections:
        total *= s.odds
    for r in rules:
        name = describe(r, team_names)
        if r.kind == "max_legs" and len(selections) > int(r.value):
            out.append(f"{name}: questa ne ha {len(selections)}.")
        elif r.kind == "max_total_odds" and total > float(r.value):
            out.append(f"{name}: questa è {total:.2f}.")
        elif r.kind == "max_stake" and stake > Decimal(r.value):
            out.append(f"{name}: stai puntando {stake} €.")
        elif r.kind == "avoid_market":
            hit = [s for s in selections if s.market == r.value]
            if hit:
                out.append(f"{name}: c'è in {len(hit)} partita/e.")
        elif r.kind == "avoid_competition":
            hit = [s for s in selections if s.match.competition.code == r.value or s.match.competition.name == r.value]
            if hit:
                out.append(f"{name}: c'è {hit[0].match.home_team.name}-{hit[0].match.away_team.name}.")
        elif r.kind == "avoid_team":
            hit = [s for s in selections if str(s.match.home_team_id) == r.value or str(s.match.away_team_id) == r.value]
            if hit:
                out.append(f"{name}: c'è {hit[0].match.home_team.name}-{hit[0].match.away_team.name}.")
        elif r.kind == "no_low_price":
            for s in selections:
                v = value_of(s)
                if v is not None and v < 0:
                    out.append(f"{name}: {s.match.home_team.name}-{s.match.away_team.name} paga sotto il giusto ({v:+.1%}).")
    return out


def suggest(bets: Sequence[Bet]) -> list[Rule]:
    """Regole suggerite dalle giocate chiuse: dove si è perso valore con abbastanza dati."""
    out: list[Rule] = []
    settled = [b for b in bets if b.status in ("won", "lost")]
    selections = [s for b in settled for s in b.selections if s.clv is not None]
    for kind, key in (("avoid_market", lambda s: s.market), ("avoid_competition", lambda s: s.match.competition.code)):
        groups: dict[str, list[float]] = defaultdict(list)
        for s in selections:
            groups[key(s)].append(float(s.clv))
        for value, clvs in sorted(groups.items()):
            mean = sum(clvs) / len(clvs)
            if len(clvs) >= MIN_SELECTIONS and mean < BAD_CLV:
                out.append(Rule(kind, value, f"su {len(clvs)} selezioni il CLV medio è {mean:+.1%}"))
    long = [b for b in settled if len(b.selections) >= 4]
    if len(long) >= MIN_LONG_BETS:
        staked = sum(float(b.stake) for b in long)
        profit = sum(float((b.payout or 0) - b.stake) for b in long)
        if staked and profit / staked < BAD_ROI_LONG:
            out.append(Rule("max_legs", "3", f"con 4 o più partite {len(long)} schedine hanno reso {profit / staked:+.0%}"))
    if len(selections) >= 2 * MIN_SELECTIONS:
        mean = sum(float(s.clv) for s in selections) / len(selections)
        if mean < BAD_CLV:
            out.append(Rule("no_low_price", "", f"in media prendi quote {mean:+.1%} sotto la chiusura"))
    return out
