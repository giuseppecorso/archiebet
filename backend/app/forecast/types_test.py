"""D178: quali tipi di giocata sbagliano. Presi contro attesi per tipo e fascia di quota, sugli studi rigiocati alla cieca.

L'errore standard è per partita: i pronostici di una stessa partita (Over 1.5, Over 2.5, Goal…) vincono e perdono insieme,
quindi contarli come indipendenti farebbe sembrare certi degli scarti che non lo sono.
"""

import math
from collections import defaultdict
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass

from app.betting.calc import WON, selection_outcome
from app.forecast import study_backtest as bt
from app.forecast.daily_replay import market_family
from app.forecast.study import playable_price

EXPLORE, CONFIRM = 2023, 2024
BANDS = ((1.40, 1.50), (1.50, 1.80), (1.80, 2.20), (2.20, 3.00))
Z_LIMIT = 2.0
MIN_GAP = 0.02  # scarto minimo tra presi e attesi, in probabilità


def band_label(price: float) -> str | None:
    for low, high in BANDS:
        if low <= price < high:
            return f"{low:.2f}-{high:.2f}"
    return None


def rows(studies: Sequence[dict], games: Sequence[bt.G]) -> list[dict]:
    """Un rigo per pronostico con quota giocabile nelle fasce: tipo, fascia, probabilità, esito, quota vera se c'è."""
    results = {g.id: g for g in games}
    out = []
    for study in studies:
        g = results.get(study["id"])
        if g is None or g.hg is None or g.ag is None:
            continue
        for pick in study["picks"]:
            price = playable_price(pick)
            band = band_label(price)
            if band is None:
                continue
            won = selection_outcome(pick["market"], pick["selection"], g.hg, g.ag, (g.hh, g.ha)) == WON
            out.append({
                "match_id": study["id"], "market": pick["market"], "family": market_family(pick["market"]), "band": band,
                "p": pick["p_archie"], "won": won, "real_price": max(pick["prices"].values(), default=0.0) or None,
            })  # fmt: skip
    return out


def board_rows(slips: Sequence[dict], games: Sequence[bt.G]) -> list[dict]:
    """Gli stessi righi per i soli pronostici scelti dalla bacheca sigillata, ognuno contato una volta."""
    picks: dict[tuple[int, str, str], dict] = {}
    for slip in slips:
        for leg in slip["legs"]:
            prices = {"book": leg["price"]} if leg["real_price"] else {}
            picks.setdefault((leg["match_id"], leg["market"], leg["selection"]), {"market": leg["market"], "selection": leg["selection"], "p_archie": leg["p"], "prices": prices})
    by_match: dict[int, list[dict]] = defaultdict(list)
    for (match_id, _, _), pick in picks.items():
        by_match[match_id].append(pick)
    return rows([{"id": match_id, "picks": found} for match_id, found in by_match.items()], games)


@dataclass(frozen=True)
class Cell:
    label: str
    n: int
    matches: int
    won: int
    expected: float
    gap: float  # (presi − attesi) / n: negativo = Archie troppo ottimista
    z: float  # scarto in errori standard, calcolati per partita
    real_n: int
    real_roi: float | None
    real_se: float | None


def _cluster_se(per_match: Sequence[float]) -> float:
    """Errore standard di una somma di contributi, uno per partita."""
    k = len(per_match)
    if k < 2:
        return 0.0
    mean = sum(per_match) / k
    return math.sqrt(k / (k - 1) * sum((x - mean) ** 2 for x in per_match))


def cells(data: Sequence[dict], key: Callable[[dict], str]) -> dict[str, Cell]:
    groups: dict[str, list[dict]] = defaultdict(list)
    for r in data:
        groups[key(r)].append(r)
    out = {}
    for label, items in groups.items():
        residual: dict[int, float] = defaultdict(float)
        profit: dict[int, float] = defaultdict(float)
        for r in items:
            residual[r["match_id"]] += r["won"] - r["p"]
            if r["real_price"]:
                profit[r["match_id"]] += r["real_price"] - 1 if r["won"] else -1.0
        n, won, expected = len(items), sum(r["won"] for r in items), sum(r["p"] for r in items)
        se = _cluster_se(list(residual.values()))
        real_n = sum(1 for r in items if r["real_price"])
        roi_se = _cluster_se(list(profit.values()))
        out[label] = Cell(
            label, n, len(residual), won, expected, (won - expected) / n, (won - expected) / se if se else 0.0,
            real_n, sum(profit.values()) / real_n if real_n else None, roi_se / real_n if real_n and roi_se else None,
        )  # fmt: skip
    return out


def is_wrong(explore: Cell | None, confirm: Cell | None) -> bool:
    """Il criterio di D178: troppo ottimista in entrambe le stagioni, oltre 2 errori standard e di almeno 2 punti."""
    return all(c is not None and c.z < -Z_LIMIT and c.gap <= -MIN_GAP for c in (explore, confirm))


def family_band(r: dict) -> str:
    return f"{r['family']} · {r['band']}"


def report(by_season: Mapping[int, Sequence[dict]], log: Callable[[str], None] = print) -> list[str]:
    """Stampa le tabelle e restituisce le caselle che il criterio giudica sbagliate."""
    tables: list[tuple[str, Callable[[dict], str]]] = [
        ("Per tipo e fascia di quota (decide)", family_band),
        ("Per fascia di quota", lambda r: r["band"]),
        ("Per tipo", lambda r: r["family"]),
        ("Per mercato", lambda r: r["market"]),
    ]
    wrong: list[str] = []
    for title, key in tables:
        explore, confirm = cells(by_season[EXPLORE], key), cells(by_season[CONFIRM], key)
        log(f"\n{title}")
        log(f"{'gruppo':<40}{'stag.':>6}{'n':>8}{'presi':>8}{'attesi':>9}{'scarto':>8}{'z':>7}{'rend. quota vera':>24}")
        for label in sorted(set(explore) | set(confirm)):
            for season, found in ((EXPLORE, explore), (CONFIRM, confirm)):
                c = found.get(label)
                if c is None:
                    continue
                roi = f"{c.real_roi:+.1%} ±{c.real_se:.1%} ({c.real_n})" if c.real_roi is not None and c.real_se is not None else "-"
                log(f"{label:<40}{season:>6}{c.n:>8}{c.won:>8}{c.expected:>9.1f}{c.gap:>+8.1%}{c.z:>7.1f}{roi:>24}")
            if key is family_band and is_wrong(explore.get(label), confirm.get(label)):
                wrong.append(label)
    log("\nCaselle sbagliate secondo D178: " + (", ".join(wrong) if wrong else "nessuna"))
    return wrong
