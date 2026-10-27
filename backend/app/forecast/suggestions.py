"""I due pronostici della pagina partita: il più sicuro e il più spinto (D107).

Si scelgono tra i mercati dei Pronostici (1X2, doppia chance, Under/Over 2.5, Gol/No gol) con le quote dei bookmaker
dell'utente. "Sicuro" vuol dire più probabile, non conveniente: il valore lo dice l'etichetta della quota (principio 1).
"""

from collections.abc import Sequence
from dataclasses import dataclass

from app.forecast.picks import MarketPick, Offer

SAFE_MIN_PRICE = 1.25  # sotto questa quota il "sicuro" non vale la giocata
BOLD_PRICE = (2.0, 4.0)  # il pronostico spinto: quota da 2 a 4 (oltre, la regola delle Occasioni non si fida)
GOOD = ("valore", "sopra la media")


@dataclass(frozen=True)
class Suggestion:
    kind: str  # "sicuro" | "spinto"
    market: str
    selection: str
    probability: float
    source: str
    offer: Offer  # la quota migliore tra i bookmaker dell'utente
    has_value: bool  # la quota batte la probabilità giusta con la regola delle Occasioni (D72)


def _candidates(picks: Sequence[MarketPick]) -> list[tuple[MarketPick, str, float, Offer]]:
    out = []
    for p in picks:
        for selection, offers in p.offers.items():
            if offers:
                best = max(offers, key=lambda o: o.price)
                out.append((p, selection, p.probabilities[selection], best))
    return out


def suggestions(picks: Sequence[MarketPick]) -> list[Suggestion]:
    """Il più sicuro (probabilità più alta con quota almeno 1,25) e il più spinto (quota 2-4: quello con più valore se c'è
    valore, altrimenti il più probabile). Si mostrano anche se la quota "paga poco" (in Serie C il margine dei bookmaker
    italiani è ~6%): l'etichetta della quota lo dice. Lista vuota se mancano le quote."""
    cands = _candidates(picks)
    out = []
    safe = [c for c in cands if c[3].price >= SAFE_MIN_PRICE]
    if safe:
        p, sel, prob, offer = max(safe, key=lambda c: (c[2], c[3].value))
        out.append(Suggestion("sicuro", p.market, sel, prob, p.source, offer, offer.verdict in GOOD))
    bold = [c for c in cands if BOLD_PRICE[0] <= c[3].price <= BOLD_PRICE[1]]
    with_value = [c for c in bold if c[3].verdict in GOOD]
    if with_value:
        p, sel, prob, offer = max(with_value, key=lambda c: c[3].value)
    elif bold:
        p, sel, prob, offer = max(bold, key=lambda c: (c[2], c[3].value))
    else:
        return out
    if not out or (out[0].market, out[0].selection) != (p.market, sel):
        out.append(Suggestion("spinto", p.market, sel, prob, p.source, offer, offer.verdict in GOOD))
    return out
