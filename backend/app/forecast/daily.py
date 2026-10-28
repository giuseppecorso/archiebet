"""Bacheca Daily (D153): le schedine che Archie pubblica ogni giorno, con le loro regole e le statistiche.

Funzioni pure: quando esce ogni schedina, su quali partite, come si chiude e come si contano i risultati.
Una schedina pubblicata non cambia più: si aggiorna solo l'esito di ogni pronostico.
"""

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime, time, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from app.betting.calc import system_payout, system_status

ROME = ZoneInfo("Europe/Rome")
PUBLISH_AT = time(10, 0)  # ora di pubblicazione (italiana)
OPEN, WON, LOST, VOID, DONE = "open", "won", "lost", "void", "done"


@dataclass(frozen=True)
class Kind:
    key: str
    title: str
    weekday: int | None  # giorno della settimana in cui esce (0 = lunedì), None = ogni giorno
    days: int  # quanti giorni copre (1 = solo oggi; weekend e settimana arrivano alla domenica)
    level: str | None  # livello dello studio; None = occasioni (CLV)
    min_legs: int = 1
    max_legs: int = 30
    target: float | None = None  # quota obiettivo
    singles: bool = False  # pronostici da giocare uno per uno (occasioni)
    system: int | None = None  # sistema "k su n" (D157): multiple da k partite


KINDS = {
    "giorno": Kind("giorno", "La schedina del giorno", None, 1, "equilibrato"),
    "weekend": Kind("weekend", "La schedina del weekend", 4, 3, "equilibrato", min_legs=4, max_legs=6),
    "settimana": Kind("settimana", "La schedina della settimana", 0, 7, "cauto"),
    "colpo": Kind("colpo", "Il colpo", None, 3, "rischioso", target=20.0),
    "clv": Kind("clv", "La schedina del CLV", None, 1, None, max_legs=3, singles=True),
    # D157: per divertirsi, con la probabilità vera in vista
    "pazza": Kind("pazza", "La pazza della settimana", 0, 7, "rischioso", min_legs=4, target=400.0),
    "sistema": Kind("sistema", "Il sistemone del weekend", 4, 3, "rischioso", min_legs=6, max_legs=6, system=4),  # quote basse: con 4 giuste non tornerebbe la puntata
}


def due(now: datetime) -> list[tuple[Kind, str, datetime, datetime]]:
    """Schedine da pubblicare adesso: (tipo, periodo, inizio, fine delle partite). Escono dalle 10 del loro giorno;
    se l'app era spenta alle 10 escono appena riparte, ma solo nello stesso giorno (niente pubblicazioni a posteriori)."""
    local = now.astimezone(ROME)
    if local.time() < PUBLISH_AT:
        return []
    out = []
    for kind in KINDS.values():
        if kind.weekday is not None and local.weekday() != kind.weekday:
            continue
        last_day = local.date() + timedelta(days=kind.days - 1)
        end = datetime.combine(last_day, time(23, 59, 59), ROME)
        out.append((kind, local.date().isoformat(), now, end))
    return out


def leg_status(match_status: str, outcome: str | None) -> str:
    """Stato di un pronostico: l'esito se la partita è finita, nullo se annullata, altrimenti aperto."""
    if match_status == "finished" and outcome is not None:
        return outcome
    if match_status == "cancelled":
        return VOID
    return OPEN


def slip_status(legs: Sequence[dict], singles: bool, system: int | None = None) -> str:
    """Multipla: persa al primo pronostico sbagliato, vinta quando sono tutti giusti (i nulli non contano).
    Singole: chiusa quando ogni pronostico ha il suo esito."""
    states = [leg["status"] for leg in legs]
    if system is not None:
        return system_status(states, system)
    if singles:
        return OPEN if OPEN in states else DONE
    if LOST in states:
        return LOST
    if OPEN in states:
        return OPEN
    return VOID if all(s == VOID for s in states) else WON


def profit(slip_legs: Sequence[dict], status: str, total_odds: float, singles: bool, system: int | None = None) -> float:
    """Guadagno con 1 € a schedina (o 1 € a pronostico per le singole); nullo = quota 1."""
    if system is not None and status != OPEN:
        sels = [(leg["status"] if leg["status"] != OPEN else LOST, Decimal(str(leg["price"]))) for leg in slip_legs]
        return float(system_payout(Decimal(1), sels, system)) - 1
    if singles:
        return sum((leg["price"] - 1 if leg["status"] == WON else -1.0 if leg["status"] == LOST else 0.0) for leg in slip_legs)
    if status == WON:
        odds = 1.0
        for leg in slip_legs:
            odds *= leg["price"] if leg["status"] == WON else 1.0
        return odds - 1
    return -1.0 if status == LOST else 0.0


@dataclass
class KindStats:
    published: int = 0
    closed: int = 0
    won: int = 0
    expected: float = 0.0  # schedine (o pronostici) che dovevano uscire secondo le probabilità di Archie
    legs_won: int = 0
    legs_closed: int = 0
    profit: float = 0.0  # con 1 € a schedina


def stats(slips: Iterable) -> dict[str, KindStats]:
    """Statistiche per tipo; `slips` ha gli attributi kind, legs, status, total_odds, win_probability."""
    out = {key: KindStats() for key in KINDS}
    for s in slips:
        k, st = KINDS[s.kind], out[s.kind]
        st.published += 1
        settled = [leg for leg in s.legs if leg["status"] in (WON, LOST)]
        st.legs_closed += len(settled)
        st.legs_won += sum(1 for leg in settled if leg["status"] == WON)
        if s.status == OPEN:
            continue
        st.closed += 1
        st.profit += profit(s.legs, s.status, s.total_odds, k.singles, k.system)
        if k.singles:
            st.won += sum(1 for leg in settled if leg["status"] == WON)
            st.expected += sum(leg["p"] for leg in settled)
        elif s.status in (WON, LOST):
            st.won += s.status == WON
            st.expected += s.win_probability
    return out
