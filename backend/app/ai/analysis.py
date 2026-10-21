"""Analisi della partita scritta da Archie (D107): spiega in italiano semplice i numeri che gli passa il codice."""

from pydantic import BaseModel

from app.ai.client import Ai


class Analysis(BaseModel):
    summary: str  # 3-4 frasi: la partita in breve
    points: list[str]  # 4-6 punti: forma, numeri, notizie, quote
    verdict: str  # 1-2 frasi sui due pronostici


ANALYSIS_SYSTEM = """Sei Archie, l'analista di ArchieBet: un tifoso esperto che spiega le partite a un amico in italiano semplice.
Ricevi una scheda con numeri calcolati dal programma (probabilità, classifica, forma, statistiche, quote) e i fatti
dalle notizie. Scrivi l'analisi della partita.

Regole:
- Usa SOLO numeri e fatti presenti nella scheda: non inventare statistiche, giocatori o notizie. Se un dato manca, non citarlo.
- Le probabilità sono già calcolate: puoi citarle, non ricalcolarle e non crearne di nuove.
- summary: 3-4 frasi sulla partita (chi arriva meglio e perché).
- points: da 4 a 6 punti brevi (una frase ciascuno): forma, numeri di stagione, notizie, cosa dicono le quote.
- verdict: 1-2 frasi sui due pronostici della scheda. "Più sicuro" vuol dire più probabile, non conveniente: di' se la
  quota ha valore solo se la scheda lo dice. Mai promettere vincite; niente toni da venditore."""


def write_analysis(ai: Ai, model: str, brief: str) -> Analysis:
    return ai.parse("match-analysis", model, ANALYSIS_SYSTEM, brief, Analysis, effort="medium")
