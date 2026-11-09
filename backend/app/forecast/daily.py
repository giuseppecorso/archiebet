"""Bacheca Daily (D153): le schedine che Archie pubblica ogni giorno, con le loro regole e le statistiche.

Funzioni pure: quando esce ogni schedina, su quali partite, come si chiude e come si contano i risultati.
Una schedina pubblicata non cambia più: si aggiorna solo l'esito di ogni pronostico.
"""

from collections import defaultdict
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
    multiplier_legs: int | None = None  # D177: multipla da 6 a 10 con questo numero di partite, scelte per prezzo


KINDS = {
    # D174: al massimo 3 partite, ogni partita in più paga di nuovo il margine del bookmaker
    "giorno": Kind("giorno", "La schedina del giorno", None, 1, "equilibrato", max_legs=3),
    "weekend": Kind("weekend", "La schedina del weekend", 4, 3, "equilibrato", min_legs=2, max_legs=3),
    "settimana": Kind("settimana", "La schedina della settimana", 0, 7, "equilibrato", max_legs=3),  # D172: dal livello cauto restavano solo quote sotto 1,40
    "colpo": Kind("colpo", "Il colpo", None, 3, "rischioso", target=20.0),
    "clv": Kind("clv", "La schedina del CLV", None, 1, None, max_legs=3, singles=True),
    "sei_dieci": Kind("sei_dieci", "La schedina 6–10", None, 1, None, multiplier_legs=2),  # D177
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


FAIR_TOLERANCE = 0.011  # la quota scritta coincide con 1/probabilità: è la quota giusta, non quella di un bookmaker


def net_prices(legs: Sequence[dict], margin: float) -> Sequence[dict]:
    """Dove manca una quota vera, la quota giusta meno il margine che il bookmaker applicherebbe (D173)."""
    if not margin:
        return legs
    return [{**leg, "price": max(1.0, leg["price"] * (1 - margin))} if leg["p"] and abs(leg["price"] - 1 / leg["p"]) < FAIR_TOLERANCE else leg for leg in legs]


def stats(slips: Iterable, margin: float = 0.0) -> dict[str, KindStats]:
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
        st.profit += profit(net_prices(s.legs, margin), s.status, s.total_odds, k.singles, k.system)
        if k.singles:
            st.won += sum(1 for leg in settled if leg["status"] == WON)
            st.expected += sum(leg["p"] for leg in settled)
        elif s.status in (WON, LOST):
            st.won += s.status == WON
            st.expected += s.win_probability
    return out


SHORT_NAMES = {"giorno": "Giorno", "weekend": "Weekend", "settimana": "Settimana", "colpo": "Colpo", "clv": "CLV", "sei_dieci": "6–10", "pazza": "Pazza", "sistema": "Sistema"}
ODDS_BANDS = (("fino a 1,40", 1.0, 1.4), ("1,40 – 2,00", 1.4, 2.0), ("2,00 – 3,00", 2.0, 3.0), ("3,00 – 5,00", 3.0, 5.0), ("oltre 5,00", 5.0, float("inf")))


@dataclass(frozen=True)
class DayProfit:
    day: str  # giorno di pubblicazione
    bets: int  # schedine chiuse (le singole del CLV contano solo nell'utile)
    won: int
    profit: float
    cum_profit: float


@dataclass(frozen=True)
class MonthResults:
    month: str  # "2026-11"
    won: int
    lost: int


@dataclass(frozen=True)
class LegBand:
    label: str
    selections: int
    won: int
    hit_rate: float | None
    expected_rate: float | None  # media delle probabilità di Archie


@dataclass(frozen=True)
class BoardCharts:
    days: list[DayProfit]
    months: list[MonthResults]
    by_kind: list[LegBand]
    by_odds: list[LegBand]


def _band(label: str, legs: Sequence[dict]) -> LegBand:
    n, won = len(legs), sum(leg["status"] == WON for leg in legs)
    return LegBand(label, n, won, round(won / n, 4) if n else None, round(sum(leg["p"] for leg in legs) / n, 4) if n else None)


def board_charts(slips: Iterable, margin: float = 0.0) -> BoardCharts:
    """I numeri dei grafici della bacheca (D173), su tutte le schedine chiuse: l'archivio ne mostra solo una settimana."""
    closed = [s for s in slips if s.status != OPEN]
    per_day: dict[str, list] = defaultdict(list)
    results: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    for s in closed:
        per_day[s.period].append(s)
        if s.status in (WON, LOST):
            results[s.period[:7]][s.status == LOST] += 1
    days, running = [], 0.0
    for day in sorted(per_day):
        items = per_day[day]
        gained = sum(profit(net_prices(s.legs, margin), s.status, s.total_odds, KINDS[s.kind].singles, KINDS[s.kind].system) for s in items)
        running += gained
        days.append(DayProfit(day, sum(s.status in (WON, LOST) for s in items), sum(s.status == WON for s in items), round(gained, 2), round(running, 2)))
    legs = [(s.kind, leg) for s in slips for leg in s.legs if leg["status"] in (WON, LOST)]
    return BoardCharts(
        days,
        [MonthResults(m, won, lost) for m, (won, lost) in sorted(results.items())],
        [_band(SHORT_NAMES.get(key, key), [leg for k, leg in legs if k == key]) for key in KINDS],
        [_band(label, [leg for _, leg in legs if low <= leg["price"] < high]) for label, low, high in ODDS_BANDS],
    )


def announcement(published: Sequence[str]) -> tuple[str, str] | None:
    """Testo della notifica quando escono schedine nuove (D158), None se non è uscito niente."""
    names = [KINDS[k].title for k in KINDS if k in published]
    if not names:
        return None
    if len(names) == 1:
        return "Nuova schedina in bacheca", f"{names[0]}: guardala su Archie."
    return f"{len(names)} nuove schedine in bacheca", ", ".join(names[:-1]) + f" e {names[-1].lower()}."
