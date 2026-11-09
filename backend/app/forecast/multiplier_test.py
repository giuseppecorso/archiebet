"""Prova D176: come arrivare a un moltiplicatore da 6 a 10. Funzioni pure.

Per ogni giorno si costruisce una schedina per composizione (quante partite, come sceglierle) usando solo quote e
probabilità di Pinnacle prima della partita; i risultati entrano dopo, in `settle`. Si guardano solo 1X2 e Under/Over 2.5,
gli unici mercati con quote storiche vere (bet365 d'apertura).
"""

import math
from collections import defaultdict
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime

from app.forecast.daily_replay import ROME
from app.forecast.multiplier import BAND, CENTER, HIGH, LOW, TOP, best_slip, score  # noqa: F401

LEGS = (1, 2, 3, 4)
MODES = ("vicine", "valore")  # vicine alla quota che serve (scelta neutra) / le più convenienti rispetto a Pinnacle
TUNING = tuple(range(2012, 2019))
CONFIRMATION = tuple(range(2019, 2025))


def _day(row: dict) -> str:
    return datetime.fromisoformat(row["when"]).astimezone(ROME).date().isoformat()


def daily_slips(candidates: Sequence[dict], legs: int, mode: str) -> dict[str, list[dict]]:
    """Una schedina al giorno per composizione, scelta alla cieca."""
    per_day: dict[str, list[dict]] = defaultdict(list)
    for row in candidates:
        per_day[_day(row)].append(row)
    out = {}
    for day in sorted(per_day):
        slip = best_slip(per_day[day], legs, mode)
        if slip is not None:
            out[day] = slip
    return out


Results = Mapping[tuple[int, str, str], bool]


def payoff(slip: Sequence[dict], results: Results) -> float | None:
    """Guadagno di 1 €; None se manca il risultato di una partita."""
    outcomes = [results.get((r["match_id"], r["market"], r["selection"])) for r in slip]
    if None in outcomes:
        return None
    return math.prod(r["price"] for r in slip) - 1 if all(outcomes) else -1.0


@dataclass(frozen=True)
class Line:
    n: int
    won: int
    expected: float  # schedine attese secondo Pinnacle
    avg_multiplier: float
    fair_return: float  # quanto renderebbe se Pinnacle avesse ragione: il margine pagato
    roi: float | None
    se: float | None


def _mean_se(values: Sequence[float]) -> tuple[float | None, float | None]:
    n = len(values)
    if n < 2:
        return None, None
    m = sum(values) / n
    return m, math.sqrt(sum((v - m) ** 2 for v in values) / (n - 1) / n)


def summarize(slips: Mapping[str, list[dict]], results: Results) -> Line:
    settled = [(s, p) for s in slips.values() if (p := payoff(s, results)) is not None]
    roi, se = _mean_se([p for _, p in settled])
    n = len(settled)
    return Line(
        n, sum(p > 0 for _, p in settled), round(sum(math.prod(r["sharp"] for r in s) for s, _ in settled), 1),
        round(sum(math.prod(r["price"] for r in s) for s, _ in settled) / n, 2) if n else 0.0,
        round(sum(math.prod(r["price"] * r["sharp"] for r in s) for s, _ in settled) / n - 1, 4) if n else 0.0, roi, se,
    )  # fmt: skip


def paired_difference(a: Mapping[str, list[dict]], b: Mapping[str, list[dict]], results: Results) -> tuple[float | None, float | None, int]:
    """Differenza di rendimento tra due composizioni nei giorni in cui esistono entrambe."""
    diffs = []
    for day in a.keys() & b.keys():
        x, y = payoff(a[day], results), payoff(b[day], results)
        if x is not None and y is not None:
            diffs.append(x - y)
    m, se = _mean_se(diffs)
    return m, se, len(diffs)


def report(candidates: Mapping[int, Sequence[dict]], results: Results, log: Callable[[str], None] = print) -> tuple[int, str]:
    """Prima la taratura, poi la conferma della sola composizione migliore. Restituisce quella scelta."""
    groups = {"taratura": [r for s in TUNING for r in candidates[s]], "conferma": [r for s in CONFIRMATION for r in candidates[s]]}
    slips = {(group, n, mode): daily_slips(rows, n, mode) for group, rows in groups.items() for n in LEGS for mode in MODES}
    for group in groups:
        log(f"\n{group}")
        log(f"{'partite':>7} {'scelta':<8}{'schedine':>9}{'vinte':>7}{'attese':>8}{'molt. medio':>12}{'margine pagato':>16}{'rendimento':>20}")
        for n in LEGS:
            for mode in MODES:
                x = summarize(slips[(group, n, mode)], results)
                shown = f"{x.roi:+.1%} ± {x.se:.1%}" if x.roi is not None and x.se is not None else "-"
                log(f"{n:>7} {mode:<8}{x.n:>9}{x.won:>7}{x.expected:>8.1f}{x.avg_multiplier:>12.2f}{x.fair_return:>+16.1%}{shown:>20}")
    tuned = {(n, mode): summarize(slips[("taratura", n, mode)], results) for n in LEGS for mode in MODES}
    best = max((k for k, v in tuned.items() if v.roi is not None and v.n >= 100), key=lambda k: tuned[k].roi)
    log(f"\nMigliore in taratura: {best[0]} partite, scelta '{best[1]}'")
    if best[1] == "valore":
        m, se, days = paired_difference(slips[("conferma", best[0], "valore")], slips[("conferma", best[0], "vicine")], results)
        log(f"Conferma, contro la scelta neutra con le stesse partite: differenza {m:+.1%} ± {se:.1%} su {days} giorni" if m is not None and se is not None else "Conferma: giorni insufficienti")
    return best
