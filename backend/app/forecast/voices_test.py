"""Prova D174: tre voci sul prezzo giusto e quante partite assemblare. Funzioni pure.

Mette insieme studi che di solito restano separati:
- consenso dei bookmaker come probabilità (Kaunitz, Zhong e Kreiner 2017) accanto a Pinnacle;
- una stima con errori indipendenti dal mercato: lo studio di Archie senza quote (Hubáček e Šír 2023);
- incertezza nella decisione (lacuna indicata da Galekwa e colleghi 2026): si gioca solo se tutte le voci dicono che la
  quota è alta, cioè se la stima più prudente la giudica comunque conveniente;
- quante partite assemblare in base alla probabilità di ciascuna (Whelan 2026) e solo tra pronostici con vantaggio (Long 2026).

I candidati non contengono risultati: si sigillano e i risultati entrano in `open_candidates`, in un passo separato.
"""

import math
from collections import defaultdict
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime

from app.betting.calc import WON, selection_outcome
from app.forecast import study_backtest as bt
from app.forecast.daily_replay import HISTORICAL_BOOK, ROME, Fixture, Vault, _pure_goals, fixture_of, season_label, seal, week_start
from app.forecast.radar import BookOdds, fair_reference
from app.forecast.study import model_probabilities

MARKETS = ("1X2", "OU2.5")
ZONES = {"da 1,40": (1.4, 6.0), "da 2": (2.0, 6.0)}
RULES = ("base", "due_voci", "studio_si", "tre_voci", "contro")
SHARP = ("pinnacle",)
CONSENSUS = ("market_avg",)
WHELAN_TWO_LEGS = 1 / 3  # sotto questa probabilità media conviene giocarle separate
NEUTRAL_SHARE = 0.45  # il primo tempo non entra nei mercati provati qui
PASS_Z = 2.39  # verifica D175: tre sguardi, soglia corretta con Bonferroni
ARCHIVE_SEASONS = tuple(range(2012, 2023))  # D175: Pinnacle d'apertura e di chiusura, mai usate con queste regole
MIN_POSITIVE_SEASONS = 8


def candidates(studies: Sequence[dict], books: Mapping[int, BookOdds]) -> list[dict]:
    """Ogni esito di 1X2 e Under/Over 2.5 con la quota giocabile e le tre voci sulla probabilità giusta. Nessun risultato."""
    out = []
    for study in studies:
        book = books.get(study["id"], {})
        pure = study.get("pure")
        if pure is None or HISTORICAL_BOOK not in book:
            continue
        probs = model_probabilities(pure["lam"], pure["mu"], pure["rho"], NEUTRAL_SHARE, NEUTRAL_SHARE)
        for market in MARKETS:
            sharp, consensus = fair_reference(book, market, SHARP), fair_reference(book, market, CONSENSUS)
            if sharp is None or consensus is None:
                continue
            for selection, price in book[HISTORICAL_BOOK].get(market, {}).items():
                if selection in sharp[1] and selection in consensus[1]:
                    out.append({
                        "match_id": study["id"], "when": study["when"], "market": market, "selection": selection, "price": price,
                        "sharp": round(sharp[1][selection], 5), "consensus": round(consensus[1][selection], 5), "study": round(probs[market][selection], 5),
                    })  # fmt: skip
    return out


def archive_games(db, seasons: Sequence[int]) -> list[bt.G]:
    """Le partite finite delle stagioni chieste, dal database (D175): per quegli anni non ci sono xG né schede."""
    from sqlalchemy import select

    from app.models import Match, MatchStatus

    labels = [season_label(s) for s in seasons]
    rows = db.execute(
        select(Match.id, Match.kickoff_at, Match.competition_id, Match.season, Match.home_team_id, Match.away_team_id,
               Match.home_goals, Match.away_goals, Match.ht_home_goals, Match.ht_away_goals)
        .where(Match.season.in_(labels), Match.status == MatchStatus.FINISHED, Match.home_goals.is_not(None), Match.away_goals.is_not(None))
    ).all()  # fmt: skip
    return [bt.G(mid, when, league, int(label[:4]), home, away, hg, ag, hh or 0, ha or 0, None, None)
            for mid, when, league, label, home, away, hg, ag, hh, ha in rows]  # fmt: skip


def archive_studies(games: Sequence[bt.G], season: int, log: Callable[[str], None] = print) -> list[dict]:
    """La voce senza quote per una stagione d'archivio: Dixon-Coles sui gol, ristimato il lunedì, un modello per campionato."""
    vault = Vault(games)
    weeks: dict[datetime, list[Fixture]] = defaultdict(list)
    for g in games:
        if g.season == season:
            weeks[week_start(g.date)].append(fixture_of(g))
    out = []
    for monday in sorted(weeks):
        by_league: dict[int, list[Fixture]] = defaultdict(list)
        for f in weeks[monday]:
            by_league[f.league].append(f)
        for league, todo in by_league.items():
            fit = bt._fit(vault.before(monday, league), monday)
            if fit is None:
                continue
            for f in todo:
                pure = _pure_goals(fit, f, None)
                if pure is not None:
                    out.append({"id": f.id, "when": f.when.isoformat(), "pure": pure})
    log(f"{season}: {len(out)} studi senza quote")
    return out


def value(row: dict, voice: str = "sharp") -> float:
    return row["price"] * row[voice] - 1


def passes(row: dict, rule: str) -> bool:
    if rule == "base":
        return value(row) > 0
    if rule == "due_voci":
        return value(row) > 0 and value(row, "consensus") > 0
    if rule == "studio_si":  # Pinnacle e lo studio senza quote d'accordo
        return value(row) > 0 and value(row, "study") > 0
    if rule == "tre_voci":  # anche la voce più prudente trova la quota conveniente
        return min(value(row), value(row, "consensus"), value(row, "study")) > 0
    if rule == "contro":  # controllo: Pinnacle dice sì, lo studio dice no
        return value(row) > 0 and value(row, "study") <= 0
    raise ValueError(rule)


def picks(rows: Sequence[dict], rule: str, zone: str) -> list[dict]:
    """Un pronostico per partita: quello più conveniente secondo Pinnacle, tra quelli che rispettano la regola."""
    low, high = ZONES[zone]
    best: dict[int, dict] = {}
    for row in rows:
        if low <= row["price"] < high and passes(row, rule) and (row["match_id"] not in best or value(row) > value(best[row["match_id"]])):
            best[row["match_id"]] = row
    return sorted(best.values(), key=lambda r: r["when"])


def open_candidates(sealed: Sequence[dict], fingerprint: str, games: Sequence[bt.G], closing: Mapping[int, BookOdds]) -> list[dict]:
    """Solo adesso i risultati e la chiusura. Rifiuta un sigillo cambiato."""
    if seal(list(sealed)) != fingerprint:
        raise ValueError("Il sigillo non corrisponde: i candidati sono cambiati dopo la chiusura")
    results = {g.id: g for g in games}
    out = []
    for row in sealed:
        g = results.get(row["match_id"])
        if g is None:
            continue
        ref = fair_reference(closing.get(row["match_id"], {}), row["market"], SHARP)
        clv = row["price"] * ref[1][row["selection"]] - 1 if ref is not None and row["selection"] in ref[1] else None
        out.append({**row, "won": selection_outcome(row["market"], row["selection"], g.hg, g.ag, (g.hh, g.ha)) == WON, "clv": clv})
    return out


@dataclass(frozen=True)
class Summary:
    n: int
    won: int
    expected: float
    roi: float | None
    roi_se: float | None
    clv: float | None
    clv_se: float | None
    clv_n: int


def _mean_se(values: Sequence[float]) -> tuple[float | None, float | None]:
    n = len(values)
    if n < 2:
        return None, None
    m = sum(values) / n
    return m, math.sqrt(sum((v - m) ** 2 for v in values) / (n - 1) / n)


def summarize(rows: Sequence[dict]) -> Summary:
    roi, roi_se = _mean_se([r["price"] - 1 if r["won"] else -1.0 for r in rows])
    clvs = [r["clv"] for r in rows if r["clv"] is not None]
    clv, clv_se = _mean_se(clvs)
    return Summary(len(rows), sum(r["won"] for r in rows), round(sum(r["sharp"] for r in rows), 1), roi, roi_se, clv, clv_se, len(clvs))


def doubles(rows: Sequence[dict]) -> list[tuple[dict, dict]]:
    """Ogni giorno le due più convenienti, se la loro probabilità media (geometrica) non scende sotto un terzo (Whelan 2026)."""
    per_day: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        per_day[datetime.fromisoformat(row["when"]).astimezone(ROME).date().isoformat()].append(row)
    out = []
    for day in sorted(per_day):
        top = sorted(per_day[day], key=value, reverse=True)[:2]
        if len(top) == 2 and math.sqrt(top[0]["sharp"] * top[1]["sharp"]) >= WHELAN_TWO_LEGS:
            out.append((top[0], top[1]))
    return out


def pair_returns(pairs: Sequence[tuple[dict, dict]]) -> tuple[list[float], list[float]]:
    """Rendimento delle doppie e degli stessi pronostici giocati singoli (metà puntata ciascuno)."""
    together = [a["price"] * b["price"] - 1 if a["won"] and b["won"] else -1.0 for a, b in pairs]
    apart = [((a["price"] - 1 if a["won"] else -1.0) + (b["price"] - 1 if b["won"] else -1.0)) / 2 for a, b in pairs]
    return together, apart


def season_of(row: dict) -> int:
    local = datetime.fromisoformat(row["when"]).astimezone(ROME)
    return local.year if local.month >= 7 else local.year - 1


def verdict(rows: Sequence[dict], rule: str, zone: str = "da 1,40") -> dict:
    """I cinque criteri di D175 per una regola."""
    chosen = picks(rows, rule, zone)
    s, base = summarize(chosen), summarize(picks(rows, "base", zone))
    per_season = [summarize([r for r in chosen if season_of(r) == y]).clv for y in sorted({season_of(r) for r in rows})]
    checks = {
        "almeno 100 giocate": s.n >= 100,
        "CLV oltre la soglia": s.clv is not None and bool(s.clv_se) and s.clv / s.clv_se > PASS_Z,
        "rendimento non negativo": s.roi is not None and s.roi >= 0,
        f"CLV positivo in almeno {MIN_POSITIVE_SEASONS} stagioni": sum(c is not None and c > 0 for c in per_season) >= MIN_POSITIVE_SEASONS,
        "CLV sopra la regola base": s.clv is not None and base.clv is not None and s.clv > base.clv,
    }
    return {"rule": rule, "checks": checks, "passed": all(checks.values())}


def report(rows: Sequence[dict], log: Callable[[str], None] = print) -> None:
    def show(values: tuple[float | None, float | None]) -> str:
        return f"{values[0]:+.1%} ± {values[1]:.1%}" if values[0] is not None and values[1] is not None else "-"

    seasons = sorted({season_of(r) for r in rows})
    log(f"esiti candidati: {len(rows)}, stagioni che iniziano nel {seasons}")
    for zone in ZONES:
        log(f"\nZona {zone}")
        log(f"{'regola':<11}{'n':>6}{'presi':>7}{'attesi':>8}{'rendimento':>18}{'CLV':>16}{'z CLV':>7}")
        for rule in RULES:
            s = summarize(picks(rows, rule, zone))
            z = s.clv / s.clv_se if s.clv is not None and s.clv_se else 0.0
            log(f"{rule:<11}{s.n:>6}{s.won:>7}{s.expected:>8.1f}{show((s.roi, s.roi_se)):>18}{show((s.clv, s.clv_se)):>16}{z:>7.1f}")
    for rule in ("due_voci", "studio_si"):
        per_season = {y: summarize([r for r in picks(rows, rule, "da 1,40") if season_of(r) == y]) for y in seasons}
        log(f"\n{rule}, stagione per stagione (zona da 1,40): " + "  ".join(f"{y}: n {s.n}, CLV {s.clv:+.1%}" if s.clv is not None else f"{y}: n {s.n}, CLV -" for y, s in per_season.items()))
    log("\nDoppie nella zona da 2 (solo se la probabilità media è almeno un terzo), contro gli stessi pronostici giocati singoli")
    for rule in ("base", "tre_voci"):
        together, apart = pair_returns(doubles(picks(rows, rule, "da 2")))
        log(f"{rule:<11}{len(together):>6} doppie   doppia {show(_mean_se(together)):>18}   singole {show(_mean_se(apart)):>18}")
