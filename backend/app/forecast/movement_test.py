"""D187: il movimento delle quote di Pinnacle tra apertura e chiusura dice ancora qualcosa sul risultato?

Parte 1: pendenza di (vinto − probabilità di chiusura) sul movimento (chiusura − apertura). Positiva = la chiusura
reagisce poco (conviene seguire il movimento), negativa = esagera (conviene andargli contro).
Parte 2: la giocata nella direzione trovata in taratura, alla quota Pinnacle di chiusura e alla bet365 di chiusura.
Errori standard per partita: gli esiti di una partita (1, X, 2, Under, Over) vincono e perdono insieme.
"""

import math
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass

from app.forecast.history_sim import Estimate, clustered_mean

THRESHOLDS = (0.02, 0.04, 0.06)
MIN_PLAYS = 300
T_SCREEN = 3.0
T_CONFIRM = 2.0
MARKETS = ("1X2", "OU2.5")


@dataclass(frozen=True)
class Obs:
    """Un esito di una partita: probabilità giuste d'apertura e chiusura, risultato e quote di chiusura."""

    match_id: int
    season: str
    market: str
    selection: str
    p_open: float
    p_close: float
    won: bool
    pin_price: float  # Pinnacle di chiusura, con il suo margine
    b365_price: float | None  # bet365 di chiusura (dal 2019/20)

    @property
    def move(self) -> float:
        return self.p_close - self.p_open


@dataclass(frozen=True)
class Slope:
    beta: float
    std_error: float
    n: int
    clusters: int

    @property
    def t(self) -> float:
        return self.beta / self.std_error if self.std_error > 0 else 0.0


def slope(obs: Sequence[Obs]) -> Slope | None:
    """Pendenza di (vinto − p di chiusura) sul movimento, con errore standard robusto per partita."""
    n = len(obs)
    if n < 3:
        return None
    xs = [o.move for o in obs]
    ys = [(1.0 if o.won else 0.0) - o.p_close for o in obs]
    mx, my = sum(xs) / n, sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    if sxx <= 0:
        return None
    beta = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sxx
    groups: dict[int, float] = defaultdict(float)
    for o, x, y in zip(obs, xs, ys):
        groups[o.match_id] += (x - mx) * (y - my - beta * (x - mx))
    g = len(groups)
    if g < 2:
        return Slope(beta, float("inf"), n, g)
    var = g / (g - 1) * sum(s * s for s in groups.values()) / sxx**2
    return Slope(beta, math.sqrt(var), n, g)


def plays(obs: Sequence[Obs], direction: int, threshold: float) -> list[Obs]:
    """Per ogni partita e mercato, l'esito con il movimento più grande nella direzione data (+1 seguire, −1 contro),
    se almeno pari alla soglia. Al massimo una giocata per partita e mercato."""
    by_market: dict[tuple[int, str], list[Obs]] = defaultdict(list)
    for o in obs:
        by_market[(o.match_id, o.market)].append(o)
    out = []
    for group in by_market.values():
        best = max(group, key=lambda o: direction * o.move)
        if direction * best.move >= threshold - 1e-12:
            out.append(best)
    return out


def profit(o: Obs, price: float) -> float:
    return price - 1.0 if o.won else -1.0


def roi(chosen: Sequence[Obs], book: str = "pinnacle") -> Estimate | None:
    """Rendimento medio a giocata alla quota di chiusura del bookmaker indicato (solo dove c'è)."""
    picked = [(o, o.pin_price if book == "pinnacle" else o.b365_price) for o in chosen]
    picked = [(o, p) for o, p in picked if p]
    if not picked:
        return None
    return clustered_mean([profit(o, p) for o, p in picked], [o.match_id for o, _ in picked])


@dataclass(frozen=True)
class MarketResult:
    market: str
    tuning_slope: Slope | None
    confirm_slope: Slope | None
    direction: int  # +1 seguire, −1 andare contro (dal segno in taratura)
    threshold: float | None  # scelta in taratura
    tuning_roi: Estimate | None
    confirm_roi: Estimate | None
    confirm_roi_b365: Estimate | None

    @property
    def slope_passed(self) -> bool:
        a, b = self.tuning_slope, self.confirm_slope
        return bool(a and b and abs(a.t) >= T_SCREEN and a.beta * b.beta > 0 and abs(b.t) >= T_CONFIRM)

    @property
    def play_passed(self) -> bool:
        c, b = self.confirm_roi, self.confirm_roi_b365
        return bool(c and c.n >= MIN_PLAYS and c.mean > 0 and c.t >= T_CONFIRM and b and b.mean > 0)


def choose_threshold(tuning: Sequence[Obs], direction: int) -> tuple[float | None, Estimate | None]:
    """La soglia con il t più alto del rendimento Pinnacle in taratura, tra quelle con almeno MIN_PLAYS giocate."""
    best: tuple[float | None, Estimate | None] = (None, None)
    for threshold in THRESHOLDS:
        r = roi(plays(tuning, direction, threshold))
        if r and r.n >= MIN_PLAYS and (best[1] is None or r.t > best[1].t):
            best = (threshold, r)
    return best


def run(tuning: Sequence[Obs], confirm: Sequence[Obs]) -> list[MarketResult]:
    out = []
    for market in MARKETS:
        tune = [o for o in tuning if o.market == market]
        conf = [o for o in confirm if o.market == market]
        s_tune, s_conf = slope(tune), slope(conf)
        direction = 1 if s_tune is None or s_tune.beta >= 0 else -1
        threshold, tune_roi = choose_threshold(tune, direction)
        chosen = plays(conf, direction, threshold) if threshold is not None else []
        out.append(MarketResult(market, s_tune, s_conf, direction, threshold, tune_roi, roi(chosen), roi(chosen, "bet365")))
    return out
