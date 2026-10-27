"""Pagella settimanale di Archie e correzioni automatiche (D132). Funzioni pure, niente database.

Ogni settimana Archie rifà i conti su sé stesso con le quote delle 10 del mattino del giorno della partita:
- Pronostici: quanto erano giuste le probabilità per famiglia di mercato (favorito atteso contro uscito, log loss
  di Archie contro quella della chiusura);
- multiple: la multipla di ogni livello di rischio su ogni bookmaker, vinte contro attese, guadagno a 1 € e CLV.

Correzioni (regole registrate prima di guardare i dati), per gruppo = famiglia di mercato × fonte della probabilità:
- taratura: p' = σ(a + b·logit p), poi le probabilità del mercato si rinormalizzano. Si attiva se, provata
  settimana per settimana solo sul passato (walk-forward), migliora la log loss oltre 2,5 errori standard (per
  partita) su almeno 4 settimane di prova, con almeno 300 mercati per stimarla;
- panchina: le gambe "giocabili" del gruppo nelle ultime 12 settimane (probabilità ≥ 30%, quota di Sisal o Eurobet
  non sotto il 10% del giusto) vincono meno di quanto Archie dice oltre 2,5 errori standard, con almeno 150 gambe:
  il gruppo esce dalle multiple. Solo per i gruppi senza taratura attiva (prima si prova a correggere).
2,5 e non 2 perché i gruppi sono tanti (più prove, più falsi allarmi). Lo stato di ogni settimana usa solo le
settimane precedenti: la pagella mostra il generatore di base e quello "che impara", senza dati dal futuro.
"""

import math
from collections import defaultdict
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field, replace
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import numpy as np

from app.forecast.history_sim import Estimate, clustered_mean
from app.forecast.multiple import FULL_MARGIN, PROFILES, Leg, Multiple, build_multiple
from app.forecast.picks import double_chance, market_family

ROME = ZoneInfo("Europe/Rome")
SNAPSHOT_HOUR = 10  # quote delle 10 del mattino del giorno della partita (o un'ora prima, se si gioca prima)
REVIEW_LEGS = 4
MIN_FIT = 300  # mercati per stimare una taratura
MIN_EVAL_WEEKS = 4
T_PASS = 2.5
BENCH_WEEKS = 12
BENCH_MIN_LEGS = 150
BENCH_MIN_PROBABILITY = 0.30
EPS = 1e-4


@dataclass(frozen=True)
class Row:
    """Un mercato di una partita: la stima di Archie alla foto delle 10 e come è finita."""

    match_id: int
    kickoff: datetime  # UTC
    competition: str
    market: str
    source: str
    probabilities: dict[str, float]
    winners: frozenset[str] | None  # esiti vinti (la doppia chance può vincerne due); None = esito non noto
    closing: dict[str, float] | None = None  # probabilità giuste alla chiusura
    prices: dict[str, dict[str, float]] = field(default_factory=dict)  # bookmaker → esito → quota alla foto

    @property
    def group(self) -> str:
        return f"{market_family(self.market)} · {self.source}"

    @property
    def exclusive(self) -> bool:
        """Esiti che si escludono e uno vince sempre (non doppia chance né Draw No Bet): servono per log loss e taratura."""
        return self.market not in ("DC", "DNB")


def snapshot_time(kickoff: datetime) -> datetime:
    """Le 10 del mattino (ora italiana) del giorno della partita, o un'ora prima del calcio d'inizio se viene prima."""
    local = kickoff.astimezone(ROME)
    ten = local.replace(hour=SNAPSHOT_HOUR, minute=0, second=0, microsecond=0)
    return min(ten, local - timedelta(hours=1)).astimezone(kickoff.tzinfo)


def day_of(kickoff: datetime) -> date:
    return kickoff.astimezone(ROME).date()


def week_of(day: date) -> date:
    """Lunedì della settimana."""
    return day - timedelta(days=day.weekday())


# --- Taratura -----------------------------------------------------------------------------------------------

def _logit(p: np.ndarray) -> np.ndarray:
    p = np.clip(p, EPS, 1 - EPS)
    return np.log(p / (1 - p))


def _fit(logits: np.ndarray, y: np.ndarray) -> tuple[float, float]:
    """(a, b) di p' = σ(a + b·logit p) per massima verosimiglianza (Newton)."""
    if len(y) == 0:
        return 0.0, 1.0
    x = np.column_stack([np.ones(len(y)), logits])
    beta = np.array([0.0, 1.0])
    for _ in range(50):
        mu = 1 / (1 + np.exp(-(x @ beta)))
        w = np.clip(mu * (1 - mu), 1e-9, None)
        step = np.linalg.solve(x.T @ (x * w[:, None]) + 1e-9 * np.eye(2), x.T @ (y - mu))
        beta = beta + step
        if np.max(np.abs(step)) < 1e-10:
            break
    return float(beta[0]), float(beta[1])


def fit_recalibration(rows: Iterable[Row]) -> tuple[float, float]:
    """Taratura stimata su un insieme di mercati: ogni esito è una prova sì/no."""
    xs, ys = [], []
    for r in rows:
        if r.exclusive and r.winners is not None:
            for s, p in r.probabilities.items():
                xs.append(p)
                ys.append(1.0 if s in r.winners else 0.0)
    return _fit(_logit(np.array(xs, dtype=float)), np.array(ys))


def recalibrate(probabilities: dict[str, float], a: float, b: float) -> dict[str, float]:
    """Applica la taratura a ogni esito e rinormalizza (le probabilità del mercato sommano a 1)."""
    logits = _logit(np.array(list(probabilities.values()), dtype=float))
    raw = 1 / (1 + np.exp(-(a + b * logits)))
    return dict(zip(probabilities, (raw / raw.sum()).tolist()))


def log_loss(probabilities: dict[str, float], winners: frozenset[str]) -> float:
    winner = next(iter(winners))
    return -math.log(max(probabilities.get(winner, 0.0), EPS))


class GroupData:
    """Gli esiti di un gruppo in forma di vettori, con la prova walk-forward calcolata una volta per settimana."""

    def __init__(self, rows: Sequence[Row], group: str):
        markets = [r for r in rows if r.group == group and r.exclusive and r.winners is not None and len(r.winners) == 1]
        self.group = group
        self.m_week = np.array([week_of(day_of(r.kickoff)).toordinal() for r in markets], dtype=int)
        self.m_match = [r.match_id for r in markets]
        p, y, idx, win = [], [], [], []
        for i, r in enumerate(markets):
            for s, v in r.probabilities.items():
                if s in r.winners:
                    win.append(len(p))
                p.append(v)
                y.append(1.0 if s in r.winners else 0.0)
                idx.append(i)
        self.logits = _logit(np.array(p, dtype=float))
        self.y = np.array(y)
        self.idx = np.array(idx, dtype=int)
        self.win = np.array(win, dtype=int)
        self.s_week = self.m_week[self.idx] if len(idx) else np.array([], dtype=int)
        self.raw_loss = -np.log(np.clip(np.array(p, dtype=float)[self.win], EPS, None)) if win else np.array([])
        self._fits: dict[int, tuple[float, float] | None] = {}
        self.gains: dict[int, np.ndarray] = {}  # settimana → miglioramento della log loss di ogni mercato
        self.clusters: dict[int, list[int]] = {}  # settimana → partita di ogni mercato (per l'errore standard)
        for wk in sorted(set(self.m_week.tolist())):
            params = self.fit_before(wk)
            if params is None:
                continue
            mask = self.m_week == wk
            sig = 1 / (1 + np.exp(-(params[0] + params[1] * self.logits)))
            sums = np.bincount(self.idx, weights=sig, minlength=len(self.m_week))
            new_loss = -np.log(np.clip(sig[self.win] / sums, EPS, None))
            self.gains[wk] = (self.raw_loss - new_loss)[mask]
            self.clusters[wk] = [m for m, keep in zip(self.m_match, mask.tolist()) if keep]

    def fit_before(self, week: int) -> tuple[float, float] | None:
        """Taratura stimata sui mercati delle settimane prima di `week` (None se sono meno di MIN_FIT)."""
        if week not in self._fits:
            if int((self.m_week < week).sum()) < MIN_FIT:
                self._fits[week] = None
            else:
                sel = self.s_week < week
                self._fits[week] = _fit(self.logits[sel], self.y[sel])
        return self._fits[week]


@dataclass(frozen=True)
class GroupTest:
    group: str
    estimate: Estimate | None  # miglioramento medio della log loss (positivo = la taratura aiuta)
    eval_weeks: int
    params: tuple[float, float] | None  # (a, b) stimati su tutto il passato, se la prova passa

    @property
    def passed(self) -> bool:
        return self.params is not None


def correction_test(data: GroupData, before: date) -> GroupTest:
    """Prova walk-forward della taratura di un gruppo usando solo le settimane prima di `before`."""
    limit = before.toordinal()
    weeks = [wk for wk in data.gains if wk < limit]
    gains: list[float] = []
    clusters: list[int] = []
    for wk in weeks:
        gains.extend(data.gains[wk].tolist())
        clusters.extend(data.clusters[wk])
    est = clustered_mean(gains, clusters) if len(gains) >= 2 else None
    passed = est is not None and len(weeks) >= MIN_EVAL_WEEKS and est.t > T_PASS
    return GroupTest(data.group, est, len(weeks), data.fit_before(limit) if passed else None)


# --- Panchina -----------------------------------------------------------------------------------------------

def playable(r: Row, selection: str, bookmakers: Sequence[str]) -> float | None:
    """La quota migliore tra i bookmaker dell'utente, se la gamba potrebbe entrare in una multipla."""
    p = r.probabilities[selection]
    prices = [r.prices.get(bm, {}).get(selection) for bm in bookmakers]
    best = max((x for x in prices if x), default=None)
    if best is None or p < BENCH_MIN_PROBABILITY or p * best - 1 < FULL_MARGIN:
        return None
    return best


@dataclass(frozen=True)
class BenchTest:
    group: str
    estimate: Estimate | None  # vinte − attese per gamba (negativo = Archie sopravvaluta)

    @property
    def benched(self) -> bool:
        return self.estimate is not None and self.estimate.n >= BENCH_MIN_LEGS and self.estimate.t < -T_PASS


def bench_test(rows: Sequence[Row], group: str, before: date, bookmakers: Sequence[str]) -> BenchTest:
    start = before - timedelta(weeks=BENCH_WEEKS)
    values, clusters = [], []
    for r in rows:
        if r.group != group or r.winners is None or not (start <= week_of(day_of(r.kickoff)) < before):
            continue
        for s, p in r.probabilities.items():
            if playable(r, s, bookmakers) is not None:
                values.append((1.0 if s in r.winners else 0.0) - p)
                clusters.append(r.match_id)
    return BenchTest(group, clustered_mean(values, clusters) if len(values) >= 2 else None)


# --- Stato che Archie usa in una settimana -------------------------------------------------------------------

@dataclass(frozen=True)
class State:
    corrections: dict[str, tuple[float, float]]  # gruppo → (a, b)
    bench: frozenset[str]

    @property
    def empty(self) -> bool:
        return not self.corrections and not self.bench

    def key(self) -> str:
        return "|".join(sorted(self.corrections)) + "#" + "|".join(sorted(self.bench))


def group_data(rows: Sequence[Row]) -> dict[str, GroupData]:
    return {g: GroupData(rows, g) for g in sorted({r.group for r in rows})}


def state_before(rows: Sequence[Row], before: date, bookmakers: Sequence[str],
                 data: dict[str, GroupData] | None = None) -> tuple[State, list[GroupTest], list[BenchTest]]:
    data = data if data is not None else group_data(rows)
    groups = sorted(data)
    tests = [correction_test(data[g], before) for g in groups]
    corrections = {t.group: t.params for t in tests if t.passed}
    benches = [bench_test(rows, g, before, bookmakers) for g in groups if g not in corrections]
    return State(corrections, frozenset(b.group for b in benches if b.benched)), tests, benches


def apply_state(rows: Sequence[Row], state: State) -> list[Row]:
    """Probabilità corrette dove la taratura è attiva; la doppia chance segue l'1X2 corretto della stessa partita."""
    out = []
    corrected_1x2 = {}
    for r in rows:
        params = state.corrections.get(r.group)
        if params is not None and r.exclusive:
            r = replace(r, probabilities=recalibrate(r.probabilities, *params))
            if r.market == "1X2":
                corrected_1x2[r.match_id] = r.probabilities
        out.append(r)
    return [replace(r, probabilities=double_chance(corrected_1x2[r.match_id])) if r.market == "DC" and r.match_id in corrected_1x2 else r for r in out]


# --- Multiple ricostruite -----------------------------------------------------------------------------------

def legs_of(rows: Iterable[Row], bookmaker: str, bench: frozenset[str] = frozenset()) -> list[Leg]:
    return [
        Leg(r.match_id, r.kickoff, r.market, s, p, price, r.source)
        for r in rows
        if r.group not in bench and r.market != "DNB"  # il rimborso col pareggio non sta nei conti della multipla
        for s, p in r.probabilities.items()
        if (price := r.prices.get(bookmaker, {}).get(s))
    ]


@dataclass(frozen=True)
class Played:
    """Una multipla proposta e come è andata."""

    multiple: Multiple
    won: bool | None  # None = un esito non è noto (angoli senza statistiche): non si conta
    clv: float | None  # media del CLV delle gambe (quota presa / quota giusta di chiusura − 1)


def settle(m: Multiple, rows_by_key: dict[tuple[int, str], Row]) -> Played:
    outcomes, clvs = [], []
    for leg in m.legs:
        r = rows_by_key[(leg.match_id, leg.market)]
        outcomes.append(None if r.winners is None else leg.selection in r.winners)
        if r.closing and r.closing.get(leg.selection):
            clvs.append(leg.price * r.closing[leg.selection] - 1)
    won = False if False in outcomes else None if None in outcomes else True
    return Played(m, won, sum(clvs) / len(clvs) if clvs else None)


@dataclass
class Tally:
    played: int = 0
    won: int = 0
    expected: float = 0.0  # vinte attese (somma delle probabilità)
    profit: float = 0.0  # a 1 € per multipla
    clv_sum: float = 0.0
    clv_n: int = 0

    def add(self, p: Played) -> None:
        if p.won is None:
            return
        self.played += 1
        self.won += p.won
        self.expected += p.multiple.win_probability
        self.profit += (p.multiple.price - 1) if p.won else -1.0
        if p.clv is not None:
            self.clv_sum += p.clv
            self.clv_n += 1

    def merge(self, other: "Tally") -> None:
        for k in ("played", "won", "expected", "profit", "clv_sum", "clv_n"):
            setattr(self, k, getattr(self, k) + getattr(other, k))

    def out(self) -> dict:
        return {"played": self.played, "won": self.won, "expected": round(self.expected, 2), "profit": round(self.profit, 2),
                "clv": round(self.clv_sum / self.clv_n, 4) if self.clv_n else None}  # fmt: skip


# --- La pagella ---------------------------------------------------------------------------------------------

def family_scores(rows: Sequence[Row]) -> list[dict]:
    """Per famiglia: favorito atteso contro uscito, log loss di Archie e della chiusura sugli stessi mercati."""
    by_family: dict[str, list[Row]] = defaultdict(list)
    for r in rows:
        if r.exclusive and r.winners is not None:
            by_family[market_family(r.market)].append(r)
    out = []
    for family in ("esito", "gol", "angoli", "cartellini"):
        rs = by_family.get(family)
        if not rs:
            continue
        fav = [max(r.probabilities.items(), key=lambda kv: kv[1]) for r in rs]
        both = [r for r in rs if r.closing]
        out.append({
            "family": family,
            "markets": len(rs),
            "favorite_expected": round(sum(p for _, p in fav) / len(rs), 4),
            "favorite_actual": round(sum(s in r.winners for (s, _), r in zip(fav, rs)) / len(rs), 4),
            "log_loss": round(sum(log_loss(r.probabilities, r.winners) for r in both) / len(both), 4) if both else None,
            "log_loss_closing": round(sum(log_loss(r.closing, r.winners) for r in both) / len(both), 4) if both else None,
        })  # fmt: skip
    return out


def _build(rows: Sequence[Row], bookmaker: str, profile: str, bench: frozenset[str]) -> Multiple | None:
    return build_multiple(legs_of(rows, bookmaker, bench), REVIEW_LEGS, PROFILES[profile])


def weekly_report(
    rows: Sequence[Row],
    bookmakers: Sequence[str],
    build: Callable[[Sequence[Row], str, str, frozenset[str]], Multiple | None] = _build,
    profiles: Sequence[str] = tuple(PROFILES),
) -> dict:
    """La pagella di tutte le settimane, lo stato attuale (correzioni e panchina) e i totali per profilo."""
    rows_by_key = {(r.match_id, r.market): r for r in rows}
    by_day: dict[date, list[Row]] = defaultdict(list)
    for r in rows:
        by_day[day_of(r.kickoff)].append(r)
    weeks = sorted({week_of(d) for d in by_day})
    data = group_data(rows)
    report, totals = [], {v: defaultdict(Tally) for v in ("base", "impara")}
    for wk in weeks:
        state, _, _ = state_before(rows, wk, bookmakers, data)
        week_rows = [r for d in sorted(by_day) if week_of(d) == wk for r in by_day[d]]
        variants = {"base": defaultdict(Tally), "impara": defaultdict(Tally)}
        for d in sorted(x for x in by_day if week_of(x) == wk):
            day_rows = by_day[d]
            learned = day_rows if state.empty else apply_state(day_rows, state)
            for profile in profiles:
                for bm in bookmakers:
                    base = build(day_rows, bm, profile, frozenset())
                    smart = base if state.empty else build(learned, bm, profile, state.bench)
                    for name, m, source in (("base", base, day_rows), ("impara", smart, learned)):
                        if m is not None:
                            keyed = rows_by_key if source is day_rows else {(r.match_id, r.market): r for r in learned}
                            variants[name][profile].add(settle(m, keyed))
        for name in variants:
            for profile, t in variants[name].items():
                totals[name][profile].merge(t)
        report.append({
            "week": wk.isoformat(),
            "matches": len({r.match_id for r in week_rows}),
            "families": family_scores(week_rows),
            "multiples": {name: {p: t.out() for p, t in v.items()} for name, v in variants.items()},
            "corrections": sorted(state.corrections),
            "bench": sorted(state.bench),
        })  # fmt: skip
    nxt = (weeks[-1] + timedelta(weeks=1)) if weeks else date.today()
    state, tests, benches = state_before(rows, nxt, bookmakers, data)
    return {
        "weeks": report,
        "totals": {name: {p: t.out() for p, t in v.items()} for name, v in totals.items()},
        "state": {
            "corrections": {g: {"a": round(a, 4), "b": round(b, 4)} for g, (a, b) in state.corrections.items()},
            "bench": sorted(state.bench),
            "groups": [
                {"group": t.group, "markets_tested": t.estimate.n if t.estimate else 0, "eval_weeks": t.eval_weeks,
                 "gain": round(t.estimate.mean, 5) if t.estimate else None, "t": round(t.estimate.t, 2) if t.estimate else None,
                 "corrected": t.passed}
                for t in tests
            ],
            "bench_tests": [
                {"group": b.group, "legs": b.estimate.n if b.estimate else 0, "gap": round(b.estimate.mean, 4) if b.estimate else None,
                 "t": round(b.estimate.t, 2) if b.estimate else None, "benched": b.benched}
                for b in benches
            ],
        },  # fmt: skip
    }
