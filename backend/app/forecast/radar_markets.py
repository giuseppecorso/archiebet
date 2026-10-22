"""Mercati del radar: principali (1X2, Under/Over 2.5, Goal/NoGoal) e secondari (angoli e cartellini, D94).

Nomi dei mercati secondari: famiglia + lato + soglia. "COR9.5" = angoli totali sopra/sotto 9,5;
"CORH4.5" = angoli della squadra di casa; "CRDA1.5" = cartellini dell'ospite. Esiti: "over" e "under".
"""

import re

from app.forecast.data import EXTRA_GOAL_MARKETS, ODDS_MARKETS

FAMILIES = {"COR": "angoli", "CRD": "cartellini"}
SIDES = {"": "totale", "H": "casa", "A": "ospite"}
OVER_UNDER = ("over", "under")
_SECONDARY = re.compile(r"^(COR|CRD)([HA]?)(\d+\.5)$")
# Gol di una sola squadra (D135): "TGH1.5" = gol della squadra di casa sopra/sotto 1,5. Non sono nel radar delle Occasioni.
_TEAM_GOALS = re.compile(r"^TG([HA])(\d\.5)$")
DNB = "DNB"  # Draw No Bet: pareggio = puntata restituita (D135)
DNB_SELECTIONS = ("1", "2")


def secondary_name(family: str, side: str, line: float) -> str:
    """("angoli", "casa", 4.5) → "CORH4.5"."""
    family_code = next(code for code, name in FAMILIES.items() if name == family)
    side_code = next(code for code, name in SIDES.items() if name == side)
    return f"{family_code}{side_code}{line:.1f}"


def parse_secondary(market: str) -> tuple[str, str, float] | None:
    """"CORH4.5" → ("angoli", "casa", 4.5); None se non è un mercato secondario."""
    m = _SECONDARY.match(market)
    return (FAMILIES[m.group(1)], SIDES[m.group(2)], float(m.group(3))) if m else None


def is_secondary(market: str) -> bool:
    return _SECONDARY.match(market) is not None


def team_goals_name(side: str, line: float) -> str:
    """("casa", 1.5) → "TGH1.5"."""
    return f"TG{'H' if side == 'casa' else 'A'}{line:.1f}"


def parse_team_goals(market: str) -> tuple[str, float] | None:
    """"TGA0.5" → ("ospite", 0.5); None se non è un mercato di gol di una squadra."""
    m = _TEAM_GOALS.match(market)
    return ("casa" if m.group(1) == "H" else "ospite", float(m.group(2))) if m else None


def is_team_goals(market: str) -> bool:
    return _TEAM_GOALS.match(market) is not None


def selections(market: str) -> tuple[str, ...]:
    """Esiti di un mercato del radar (vuoto se il mercato non è seguito)."""
    if market in ODDS_MARKETS:
        return tuple(ODDS_MARKETS[market])
    if market in EXTRA_GOAL_MARKETS:
        return tuple(EXTRA_GOAL_MARKETS[market])
    if market == DNB:
        return DNB_SELECTIONS
    return OVER_UNDER if is_secondary(market) or is_team_goals(market) else ()


def secondary_won(market: str, selection: str, corners: tuple[int | None, int | None],
                  yellow: tuple[int | None, int | None], red: tuple[int | None, int | None]) -> bool | None:
    """L'Over/Under di angoli o cartellini è uscito? Cartellini: giallo 1, rosso 1 (regola verificata in D82).
    None se mancano i dati della partita (angoli e cartellini arrivano solo per i campionati di football-data)."""
    parsed = parse_secondary(market)
    if parsed is None:
        raise ValueError(market)
    family, side, line = parsed
    if family == "angoli":
        home, away = corners
    else:
        if None in (*yellow, *red):
            return None
        home, away = yellow[0] + red[0], yellow[1] + red[1]
    if home is None or away is None:
        return None
    count = home + away if side == "totale" else home if side == "casa" else away
    return (count > line) == (selection == "over")
