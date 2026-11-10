"""D189: le strategie famose del mercato messe alla prova sull'archivio.

Ogni strategia è una regola fissata prima di guardare i dati: dice quali esiti giocare e a che quota. Si misura il
rendimento (quanto torna per ogni euro giocato) e il CLV contro la chiusura di Pinnacle senza margine, separatamente
in taratura e in conferma. Errori standard per partita (per giornata nella multipla dei favoriti).
"""

import math
from collections import defaultdict
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import date

from app.forecast.history_sim import RULES, Estimate, clustered_mean

Prices = dict[str, dict[str, float]]  # mercato → esito → quota o probabilità

TUNING_FIRST, CONFIRM_FIRST, CONFIRM_LAST = "2012/13", "2020/21", "2024/25"
MIN_CONFIRM = 100
T_PASS = 2.0
LATE = "ultime 6 giornate"
D72 = RULES[0]


@dataclass(frozen=True)
class Game:
    match_id: int
    season: str
    league: str
    day: date
    moment: str | None  # "prime 5 giornate", "ultime 6 giornate" o None
    home_goals: int
    away_goals: int
    b365: Prices  # bet365 d'apertura
    b365_close: Prices  # bet365 di chiusura (dal 2019/20, altrimenti vuoto)
    avg: Prices  # media del mercato d'apertura
    best: Prices  # quota massima del mercato d'apertura
    fair_open: Prices  # Pinnacle d'apertura senza margine
    fair_close: Prices  # Pinnacle di chiusura senza margine


def won(g: Game, market: str, selection: str) -> bool:
    if market == "1X2":
        result = "1" if g.home_goals > g.away_goals else "2" if g.home_goals < g.away_goals else "X"
        return selection == result
    if market == "OU2.5":
        return (g.home_goals + g.away_goals > 2.5) == (selection == "over")
    raise ValueError(market)


@dataclass(frozen=True)
class Bet:
    cluster: int  # partita (o giornata per le multiple): le giocate dello stesso gruppo non sono indipendenti
    season: str
    price: float
    won: bool
    clv: float | None  # quota × probabilità giusta di chiusura − 1

    @property
    def profit(self) -> float:
        return self.price - 1.0 if self.won else -1.0


def single(g: Game, market: str, selection: str, price: float) -> Bet:
    p_close = g.fair_close.get(market, {}).get(selection)
    return Bet(g.match_id, g.season, price, won(g, market, selection), price * p_close - 1.0 if p_close else None)


def _price(prices: Prices, market: str, selection: str) -> float | None:
    p = prices.get(market, {}).get(selection)
    return p if p and p > 1 else None


# --- Le strategie --------------------------------------------------------------------------------------------

def always(market: str, selection: str) -> Callable[[Sequence[Game]], list[Bet]]:
    def rule(games: Sequence[Game]) -> list[Bet]:
        return [single(g, market, selection, p) for g in games if (p := _price(g.b365, market, selection))]
    return rule


def price_band(low: float, high: float) -> Callable[[Sequence[Game]], list[Bet]]:
    """Ogni esito 1X2 con quota bet365 in [low, high)."""
    def rule(games: Sequence[Game]) -> list[Bet]:
        return [single(g, "1X2", s, p) for g in games for s, p in g.b365.get("1X2", {}).items() if p > 1 and low <= p < high]
    return rule


def even_draws(games: Sequence[Game]) -> list[Bet]:
    """Il pareggio quando le due squadre sono alla pari: quote del 1 e del 2 entrambe tra 2,30 e 3,50."""
    out = []
    for g in games:
        h, a, x = (_price(g.b365, "1X2", s) for s in ("1", "2", "X"))
        if h and a and x and 2.30 <= h <= 3.50 and 2.30 <= a <= 3.50:
            out.append(single(g, "1X2", "X", x))
    return out


def late_draws(games: Sequence[Game]) -> list[Bet]:
    """Il pareggio nelle ultime 6 giornate (il "biscotto")."""
    return [single(g, "1X2", "X", p) for g in games if g.moment == LATE and (p := _price(g.b365, "1X2", "X"))]


def favourites_treble(games: Sequence[Game], legs: int = 3, max_price: float = 1.60) -> list[Bet]:
    """Ogni giorno la multipla dei 3 favoriti con la quota bet365 più bassa (fino a 1,60), una per giornata."""
    by_day: dict[date, list[tuple[float, Game, str]]] = defaultdict(list)
    for g in games:
        prices = {s: p for s, p in g.b365.get("1X2", {}).items() if p > 1}
        if not prices:
            continue
        sel = min(prices, key=prices.__getitem__)
        if prices[sel] <= max_price:
            by_day[g.day].append((prices[sel], g, sel))
    out = []
    for day, cands in by_day.items():
        if len(cands) < legs:
            continue
        chosen = sorted(cands, key=lambda c: (c[0], c[1].match_id))[:legs]
        price = math.prod(c[0] for c in chosen)
        closes = [c[1].fair_close.get("1X2", {}).get(c[2]) for c in chosen]
        clv = math.prod(c[0] * pc for c, pc in zip(chosen, closes)) - 1.0 if all(closes) else None
        out.append(Bet(day.toordinal(), chosen[0][1].season, price, all(won(c[1], "1X2", c[2]) for c in chosen), clv))
    return out


def follow_move(games: Sequence[Game], threshold: float = 0.04) -> list[Bet]:
    """Seguire la quota che scende: l'esito 1X2 la cui probabilità Pinnacle sale di più, se almeno 0,04, alla bet365 di chiusura."""
    out = []
    for g in games:
        o, c = g.fair_open.get("1X2"), g.fair_close.get("1X2")
        if not o or not c or not g.b365_close.get("1X2"):
            continue
        sel = max(c, key=lambda s: c[s] - o.get(s, c[s]))
        p = _price(g.b365_close, "1X2", sel)
        if p and c[sel] - o.get(sel, c[sel]) >= threshold - 1e-12:
            out.append(single(g, "1X2", sel, p))
    return out


def value_bets(games: Sequence[Game]) -> list[Bet]:
    """Value betting = regola delle Occasioni D72: bet365 d'apertura paga più del giusto di Pinnacle d'apertura."""
    out = []
    for g in games:
        for market, prices in g.b365.items():
            fair = g.fair_open.get(market, {})
            for sel, p in prices.items():
                if p > 1 and sel in fair and D72.qualifies(p, fair[sel] * p - 1.0):
                    out.append(single(g, market, sel, p))
    return out


def consensus(games: Sequence[Game], alpha: float = 0.05) -> list[Bet]:
    """Kaunitz e altri (2017): si gioca alla quota massima quando supera 1 / (1/quota media − alpha)."""
    out = []
    for g in games:
        for market, avg in g.avg.items():
            for sel, a in avg.items():
                best = _price(g.best, market, sel)
                p = 1.0 / a - alpha if a > 1 else 0.0
                if best and p > 0 and best > 1.0 / p:
                    out.append(single(g, market, sel, best))
    return out


@dataclass(frozen=True)
class Strategy:
    key: str
    name: str
    how: str  # come si gioca, a parole
    price: str  # a che quota si misura
    rule: Callable[[Sequence[Game]], list[Bet]]


STRATEGIES: tuple[Strategy, ...] = (
    Strategy("home", "Sempre la squadra di casa", "Si gioca il 1 in ogni partita.", "bet365 d'apertura", always("1X2", "1")),
    Strategy("draw", "Sempre il pareggio", "Si gioca la X in ogni partita.", "bet365 d'apertura", always("1X2", "X")),
    Strategy("away", "Sempre la squadra in trasferta", "Si gioca il 2 in ogni partita.", "bet365 d'apertura", always("1X2", "2")),
    Strategy("short", "Favoriti sicuri", "Ogni esito 1X2 sotto quota 1,50.", "bet365 d'apertura", price_band(1.0, 1.50)),
    Strategy("long", "Sfavoriti a quota alta", "Ogni esito 1X2 da quota 5 in su.", "bet365 d'apertura", price_band(5.0, 1000.0)),
    Strategy("even_draw", "Pareggio tra squadre alla pari", "La X quando 1 e 2 sono entrambe tra 2,30 e 3,50.", "bet365 d'apertura", even_draws),
    Strategy("over", "Sempre Over 2.5", "Più di 2,5 gol in ogni partita.", "bet365 d'apertura", always("OU2.5", "over")),
    Strategy("under", "Sempre Under 2.5", "Meno di 2,5 gol in ogni partita.", "bet365 d'apertura", always("OU2.5", "under")),
    Strategy("late_draw", "Pareggio a fine stagione", "La X nelle ultime 6 giornate.", "bet365 d'apertura", late_draws),
    Strategy("treble", "Multipla dei favoriti", "Ogni giorno i 3 favoriti con la quota più bassa (fino a 1,60) in una multipla.", "bet365 d'apertura", favourites_treble),
    Strategy("steam", "Seguire la quota che scende", "L'esito che Pinnacle abbassa di più tra apertura e chiusura (almeno 4 punti di probabilità).", "bet365 di chiusura (dal 2019/20)", follow_move),
    Strategy("value", "Value betting (le Occasioni di Archie)", "Quando bet365 paga più del prezzo giusto di Pinnacle (regola D72).", "bet365 d'apertura", value_bets),
    Strategy("consensus", "Consenso dei bookmaker", "Quando la quota più alta del mercato supera di molto la media (Kaunitz e altri, 2017).", "la quota più alta del mercato (spesso non giocabile in Italia)", consensus),
)


@dataclass(frozen=True)
class Part:
    n: int
    roi: Estimate | None
    clv: Estimate | None
    won: int = 0  # giocate vinte
    avg_price: float | None = None  # quota media

    @property
    def hit_rate(self) -> float | None:
        return self.won / self.n if self.n else None


def part(bets: Sequence[Bet]) -> Part:
    if not bets:
        return Part(0, None, None)
    roi = clustered_mean([b.profit for b in bets], [b.cluster for b in bets])
    with_clv = [b for b in bets if b.clv is not None]
    clv = clustered_mean([b.clv for b in with_clv], [b.cluster for b in with_clv]) if with_clv else None  # type: ignore[misc]
    return Part(len(bets), roi, clv, sum(b.won for b in bets), sum(b.price for b in bets) / len(bets))


def passed(tuning: Part, confirm: Part) -> bool:
    return bool(tuning.roi and tuning.roi.mean > 0 and confirm.roi and confirm.n >= MIN_CONFIRM and confirm.roi.mean > 0 and confirm.roi.t >= T_PASS)


def beats_close(tuning: Part, confirm: Part) -> bool:
    """Solo descrittivo (non decide il verdetto): CLV positivo oltre 2 errori standard sia in taratura sia in conferma."""
    return all(p.clv is not None and p.clv.mean > 0 and p.clv.t >= T_PASS for p in (tuning, confirm))


def _est(e: Estimate | None) -> dict | None:
    if e is None:
        return None
    return {"mean": round(e.mean, 5), "se": round(e.std_error, 5) if math.isfinite(e.std_error) else None, "t": round(e.t, 2)}


def _part_dict(p: Part) -> dict:
    return {"n": p.n, "won": p.won, "hit_rate": round(p.hit_rate, 4) if p.hit_rate is not None else None,
            "avg_price": round(p.avg_price, 3) if p.avg_price else None, "roi": _est(p.roi), "clv": _est(p.clv)}  # fmt: skip


def evaluate(games: Sequence[Game]) -> list[dict]:
    """Ogni strategia in taratura e in conferma, pronta da salvare in JSON."""
    tune = [g for g in games if g.season < CONFIRM_FIRST]
    conf = [g for g in games if CONFIRM_FIRST <= g.season <= CONFIRM_LAST]
    out = []
    for s in STRATEGIES:
        a, b = part(s.rule(tune)), part(s.rule(conf))
        out.append({
            "key": s.key, "name": s.name, "how": s.how, "price": s.price, "passed": passed(a, b), "beats_close": beats_close(a, b),
            "tuning": _part_dict(a),
            "confirm": _part_dict(b),
        })  # fmt: skip
    return out
