"""Calcoli delle giocate (principio 4: i numeri li calcola il codice). Funzioni pure, tutte testate.

Mercati gestiti e loro esiti:
- "1X2": "1", "X", "2"
- "DC" (doppia chance): "1X", "X2", "12"
- "OU1.5", "OU2.5", "OU3.5": "over", "under" (Under/Over sulla linea dei gol indicata, D130)
- "GG" (Goal/NoGoal): "yes", "no"
"""

from collections.abc import Iterable, Sequence
from decimal import ROUND_HALF_UP, Decimal

MARKETS: dict[str, tuple[str, ...]] = {
    "1X2": ("1", "X", "2"),
    "DC": ("1X", "X2", "12"),
    "OU1.5": ("over", "under"),
    "OU2.5": ("over", "under"),
    "OU3.5": ("over", "under"),
    "GG": ("yes", "no"),
}


def ou_line(market: str) -> float | None:
    """Linea dei gol di un mercato Under/Over ("OU2.5" → 2.5), None per gli altri mercati."""
    return float(market[2:]) if market.startswith("OU") else None

WON, LOST, VOID, OPEN = "won", "lost", "void", "open"
CENT = Decimal("0.01")


def is_valid_pick(market: str, pick: str) -> bool:
    return pick in MARKETS.get(market, ())


def selection_outcome(market: str, pick: str, home_goals: int, away_goals: int) -> str:
    """Vinta o persa una selezione, dato il risultato finale."""
    if not is_valid_pick(market, pick):
        raise ValueError(f"Esito '{pick}' non valido per il mercato '{market}'")
    result = "1" if home_goals > away_goals else "X" if home_goals == away_goals else "2"
    if market == "1X2":
        hit = pick == result
    elif market == "DC":
        hit = result in pick
    elif (line := ou_line(market)) is not None:
        hit = (home_goals + away_goals > line) == (pick == "over")
    else:  # GG
        hit = (home_goals > 0 and away_goals > 0) == (pick == "yes")
    return WON if hit else LOST


def total_odds(odds: Iterable[Decimal]) -> Decimal:
    """Quota della schedina = prodotto delle quote (4 decimali, come si arrotonda alla fine)."""
    product = Decimal(1)
    for o in odds:
        if o <= 1:
            raise ValueError("Una quota deve essere maggiore di 1")
        product *= o
    return product.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)


def potential_payout(stake: Decimal, odds: Decimal) -> Decimal:
    return (stake * odds).quantize(CENT, rounding=ROUND_HALF_UP)


def bet_status(selection_statuses: Sequence[str]) -> str:
    """Stato della schedina dalle sue selezioni.

    Una persa → persa. Altrimenti, se ne resta una aperta → aperta.
    Altrimenti vinta; se sono tutte annullate → annullata (si rimborsa la puntata).
    """
    if LOST in selection_statuses:
        return LOST
    if OPEN in selection_statuses:
        return OPEN
    if all(s == VOID for s in selection_statuses):
        return VOID
    return WON


def settled_payout(stake: Decimal, selections: Sequence[tuple[str, Decimal]]) -> Decimal:
    """Quanto torna una schedina chiusa: le selezioni annullate valgono quota 1."""
    status = bet_status([s for s, _ in selections])
    if status == LOST:
        return Decimal(0)
    if status == VOID:
        return stake.quantize(CENT)
    if status == OPEN:
        raise ValueError("La schedina non è ancora chiusa")
    return potential_payout(stake, _won_odds(selections))


def _won_odds(selections: Sequence[tuple[str, Decimal]]) -> Decimal:
    """Prodotto delle quote delle sole selezioni vinte (le annullate valgono 1)."""
    product = Decimal(1)
    for status, odds in selections:
        if status == WON:
            product *= odds
    return product


def fair_odds(prices: dict[str, Decimal]) -> dict[str, Decimal]:
    """Quote "giuste" senza il margine del bookmaker (metodo proporzionale).

    Probabilità implicite 1/quota, normalizzate perché sommino a 1; quota giusta = 1 / probabilità.
    """
    implied = {k: 1 / v for k, v in prices.items()}
    total = sum(implied.values())
    return {k: total / p for k, p in implied.items()}


def fair_closing_odds(market: str, pick: str, closing_1x2: dict[str, Decimal] | None, closing_ou: dict[str, Decimal] | None) -> Decimal | None:
    """Quota giusta di chiusura per la selezione, se abbiamo le quote di chiusura del mercato."""
    if market in ("1X2", "DC") and closing_1x2 and len(closing_1x2) == 3:
        fair = fair_odds(closing_1x2)
        if market == "1X2":
            return fair[pick]
        probability = sum(1 / fair[p] for p in pick)  # es. "1X" = P(1) + P(X)
        return 1 / probability
    if ou_line(market) is not None and closing_ou and len(closing_ou) == 2:  # closing_ou: chiusura della stessa linea
        return fair_odds(closing_ou)[pick]
    return None


def clv(taken_odds: Decimal, fair_closing: Decimal | None) -> Decimal | None:
    """Closing Line Value: quanto la quota presa batte la quota giusta di chiusura (0.05 = +5%)."""
    if fair_closing is None:
        return None
    return (taken_odds / fair_closing - 1).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
