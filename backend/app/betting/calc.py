"""Calcoli delle giocate (principio 4: i numeri li calcola il codice). Funzioni pure, tutte testate.

Mercati gestiti e loro esiti:
- "1X2": "1", "X", "2"
- "DC" (doppia chance): "1X", "X2", "12"
- "OU0.5" … "OU4.5": "over", "under" (Under/Over sulla linea dei gol indicata, D130-D131)
- "GG" (Goal/NoGoal): "yes", "no"
- angoli e cartellini (D131): "COR9.5", "CORH4.5", "CRDA1.5", ... con "over", "under" (nomi in radar_markets)
- gol di una squadra (D135): "TGH1.5" (casa), "TGA0.5" (ospite) con "over", "under"
- "DNB" (Draw No Bet, D135): "1", "2"; col pareggio la puntata torna (selezione annullata)
- dallo studio (D137): primo tempo ("1T_OU0.5", "1T_TGH0.5", ...), multigol ("MG2-4") e combo ("CB_1X_O1.5") con "yes"
"""

from collections.abc import Iterable, Sequence
from decimal import ROUND_HALF_UP, Decimal

from app.forecast.study import MARKETS as STUDY_MARKETS
from app.forecast.radar_markets import DNB, DNB_SELECTIONS, OVER_UNDER, is_secondary, is_team_goals, parse_secondary, parse_team_goals, secondary_won

MARKETS: dict[str, tuple[str, ...]] = {
    "1X2": ("1", "X", "2"),
    "DC": ("1X", "X2", "12"),
    "OU0.5": ("over", "under"),
    "OU1.5": ("over", "under"),
    "OU2.5": ("over", "under"),
    "OU3.5": ("over", "under"),
    "OU4.5": ("over", "under"),
    "GG": ("yes", "no"),
}


def is_study_only(market: str) -> bool:
    """Mercati che esistono solo nello studio di Archie: primo tempo, multigol, combo (D137)."""
    return market.startswith(("1T_", "2T_", "MG", "CB_")) and market in STUDY_MARKETS


def needs_half_time(market: str) -> bool:
    return market.startswith(("1T_", "2T_"))


def ou_line(market: str) -> float | None:
    """Linea dei gol di un mercato Under/Over ("OU2.5" → 2.5), None per gli altri mercati."""
    return float(market[2:]) if market.startswith("OU") else None

WON, LOST, VOID, OPEN = "won", "lost", "void", "open"
CENT = Decimal("0.01")


def selections_of(market: str) -> tuple[str, ...]:
    """Esiti ammessi di un mercato (vuoto se il mercato non è gestito)."""
    if market == DNB:
        return DNB_SELECTIONS
    if is_study_only(market):
        return tuple(STUDY_MARKETS[market].selections)
    return MARKETS.get(market) or (OVER_UNDER if is_secondary(market) or is_team_goals(market) else ())


def is_valid_pick(market: str, pick: str) -> bool:
    return pick in selections_of(market)


SHORT_NAMES = {"1X2": "1X2", "DC": "doppia chance", "GG": "Gol/No gol", DNB: "Draw No Bet"}


def market_name(market: str) -> str:
    """Nome breve in italiano: "Under/Over 2.5", "angoli casa Under/Over 4.5", ..."""
    if (line := ou_line(market)) is not None:
        return f"Under/Over {line:g}"
    if (team := parse_team_goals(market)) is not None:
        return f"gol {team[0]} Under/Over {team[1]:g}"
    if market.startswith(("1T_", "2T_")):
        inner = market_name(market[3:])
        return f"{inner} {'primo' if market.startswith('1T_') else 'secondo'} tempo"
    if market.startswith("MG"):
        return f"multigol {market[2:]}"
    if market.startswith("CB_"):
        _, res, goals = market.split("_")
        return f"combo {res} + {'Over' if goals[0] == 'O' else 'Under'} {goals[1:]}"
    if (parsed := parse_secondary(market)) is not None:
        family, side, line = parsed
        who = "" if side == "totale" else f" {side}"
        return f"{family}{who} Under/Over {line:g}"
    return SHORT_NAMES.get(market, market)


def is_settled_by_goals(market: str) -> bool:
    """True se basta il risultato per chiudere la selezione (angoli e cartellini aspettano le statistiche)."""
    return not is_secondary(market)


def secondary_outcome(market: str, pick: str, corners: tuple[int | None, int | None],
                      yellow: tuple[int | None, int | None], red: tuple[int | None, int | None]) -> str | None:
    """Vinta o persa una selezione di angoli o cartellini; None se le statistiche della partita non ci sono ancora."""
    if not is_valid_pick(market, pick):
        raise ValueError(f"Esito '{pick}' non valido per il mercato '{market}'")
    hit = secondary_won(market, pick, corners, yellow, red)
    return None if hit is None else WON if hit else LOST


def selection_outcome(market: str, pick: str, home_goals: int, away_goals: int, ht: tuple[int, int] | None = None) -> str:
    """Vinta o persa una selezione, dato il risultato finale (e del primo tempo per i mercati del primo tempo)."""
    if is_study_only(market):
        if pick not in STUDY_MARKETS[market].selections:
            raise ValueError(f"Esito '{pick}' non valido per il mercato '{market}'")
        if needs_half_time(market) and ht is None:
            raise ValueError("Serve il risultato del primo tempo")
        x, y = ht or (0, 0)
        return WON if STUDY_MARKETS[market].selections[pick](home_goals, away_goals, x, y) else LOST
    if not is_valid_pick(market, pick) or is_secondary(market):  # angoli e cartellini: secondary_outcome
        raise ValueError(f"Esito '{pick}' non valido per il mercato '{market}'")
    result = "1" if home_goals > away_goals else "X" if home_goals == away_goals else "2"
    if market == DNB:
        return VOID if result == "X" else WON if pick == result else LOST
    if (team := parse_team_goals(market)) is not None:
        goals = home_goals if team[0] == "casa" else away_goals
        return WON if (goals > team[1]) == (pick == "over") else LOST
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
    if market in ("1X2", "DC", DNB) and closing_1x2 and len(closing_1x2) == 3:
        fair = fair_odds(closing_1x2)
        if market == DNB:  # col pareggio si riprende la puntata: conta solo 1 contro 2
            p1, p2 = 1 / fair["1"], 1 / fair["2"]
            return (p1 + p2) / (p1 if pick == "1" else p2)
        if market == "1X2":
            return fair[pick]
        probability = sum(1 / fair[p] for p in pick)  # es. "1X" = P(1) + P(X)
        return 1 / probability
    if (ou_line(market) is not None or is_secondary(market) or is_team_goals(market) or market == "GG") and closing_ou and len(closing_ou) == 2:  # closing_ou: chiusura dello stesso mercato
        return fair_odds(closing_ou)[pick]
    return None


def clv(taken_odds: Decimal, fair_closing: Decimal | None) -> Decimal | None:
    """Closing Line Value: quanto la quota presa batte la quota giusta di chiusura (0.05 = +5%)."""
    if fair_closing is None:
        return None
    return (taken_odds / fair_closing - 1).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
