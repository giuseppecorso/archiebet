"""Sfortuna o errore? (Fase 6, D113): l'autopsia di ogni selezione chiusa, calcolata dal codice.

Il metro è la quota giusta di chiusura (il mercato al calcio d'inizio, la stima migliore della probabilità vera):
- CLV ≥ 0 = il prezzo era buono (nessun errore), anche se poi è andata male;
- CLV < 0 = il prezzo era sotto il giusto: anche vincendo, alla lunga è una giocata in perdita.
Per i pronostici sul risultato si guardano anche i tiri in porta: chi ha tirato di più "meritava".
"""

from dataclasses import dataclass

GOOD, LUCKY, UNLUCKY, FAIR_LOSS, PRICE_ERROR, VOID, UNKNOWN = (
    "giocata giusta", "fortuna", "sfortuna", "ci sta", "errore di prezzo", "rimborsata", "senza chiusura",
)  # fmt: skip
DOMINANCE = 0.6  # quota dei tiri in porta della partita oltre cui una squadra "meritava"


@dataclass(frozen=True)
class SelectionFacts:
    market: str  # 1X2 | DC | OU2.5 | GG
    pick: str
    odds: float
    status: str  # won | lost | void
    fair_closing_odds: float | None
    home_sot: int | None
    away_sot: int | None
    home_goals: int | None
    away_goals: int | None
    closing_note: str | None = None  # perché manca la chiusura: "in arrivo" o "senza riferimento"


@dataclass(frozen=True)
class Autopsy:
    verdict: str
    probability: float | None  # probabilità giusta al calcio d'inizio
    clv: float | None
    text: str


def _pct(x: float) -> str:
    return f"{x * 100:.0f}%"


def deserved(f: SelectionFacts) -> bool | None:
    """Per 1X2 e doppia chance: la squadra (o le squadre) scelte hanno dominato i tiri in porta? None se non si sa."""
    if f.market not in ("1X2", "DC") or f.home_sot is None or f.away_sot is None or f.home_sot + f.away_sot == 0:
        return None
    share_home = f.home_sot / (f.home_sot + f.away_sot)
    if f.pick in ("1", "1X"):
        return share_home >= DOMINANCE
    if f.pick in ("2", "X2"):
        return 1 - share_home >= DOMINANCE
    return None  # pareggio o "12": i tiri non dicono chi meritava


def autopsy(f: SelectionFacts) -> Autopsy:
    if f.status == "void":
        return Autopsy(VOID, None, None, "Partita annullata o rinviata: la giocata è stata rimborsata.")
    if not f.fair_closing_odds:
        won = f.status == "won"
        why = {
            "in arrivo": "la quota di chiusura arriva qualche ora dopo la partita: il giudizio sul prezzo comparirà da solo.",
            "senza riferimento": "per questo campionato non c'è una quota di chiusura affidabile (Pinnacle non lo quota), quindi non si può dire se il prezzo era buono.",
        }.get(f.closing_note or "", "manca la quota di chiusura, quindi non si può dire se il prezzo era buono.")
        return Autopsy(UNKNOWN, None, None, ("Vinta" if won else "Persa") + ": " + why)
    p = 1 / f.fair_closing_odds
    clv = f.odds / f.fair_closing_odds - 1
    shots = f" Tiri in porta {f.home_sot}-{f.away_sot}." if f.home_sot is not None and f.away_sot is not None else ""
    if f.status == "won":
        if clv >= 0:
            return Autopsy(GOOD, p, clv, f"Vinta con un prezzo migliore della chiusura (CLV {clv:+.1%}): è il modo giusto di vincere.")
        return Autopsy(LUCKY, p, clv, f"Vinta, ma la quota era sotto il giusto (CLV {clv:+.1%}): alla lunga giocate così fanno perdere.")
    merit = deserved(f)
    if clv < 0:
        return Autopsy(PRICE_ERROR, p, clv, f"Persa, e il prezzo era sotto il giusto (CLV {clv:+.1%}): l'errore era nella quota, non nel risultato.{shots}")
    if merit:
        return Autopsy(UNLUCKY, p, clv, f"Sfortuna: il prezzo era buono (CLV {clv:+.1%}) e la tua squadra ha dominato i tiri in porta, ma non è bastato.{shots}")
    return Autopsy(FAIR_LOSS, p, clv, f"Ci sta: prezzo buono (CLV {clv:+.1%}), ma con il {_pct(p)} di probabilità si perde {_pct(1 - p)} delle volte.{shots}")
