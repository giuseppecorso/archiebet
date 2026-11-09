"""Macchina del tempo (D171): la bacheca rigiocata sul passato, alla cieca.

Stesso codice dal vivo per lo studio di una partita e per la scelta dei pronostici. Tre barriere contro i risultati:
1. la partita da prevedere è un `Fixture`, che non ha campi con il risultato;
2. lo storico si ottiene solo da `Vault.before(data)`: le partite da quella data in poi non escono;
3. le schedine si sigillano (SHA-256) prima di aprire i risultati, in un passo separato.

I modelli si ristimano il lunedì e schede e storico restano fermi a quel lunedì: la schedina della settimana esce il
lunedì e nessuna schedina deve poter vedere una partita giocata dopo.
"""

import hashlib
import json
import math
from bisect import bisect_left
from collections import defaultdict
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from app.betting.calc import LOST, WON, selection_outcome
from app.forecast import study_backtest as bt
from app.forecast.daily import KINDS, OPEN, PUBLISH_AT, Kind, due, leg_status, slip_status, stats
from app.forecast.daily_service import best_value, choose_study_legs, slip_totals
from app.forecast.multiplier import best_slip, price_rows
from app.forecast.radar import BookOdds, fair_reference
from app.forecast.study import ASSUMED_MARGIN, leg_price
from app.forecast.study_service import XG_WEIGHT, study_match

ROME = ZoneInfo("Europe/Rome")
DEVELOPMENT = (2023, 2024)  # qui si itera
VERIFICATION = (2025,)  # ogni apertura si conta
HISTORICAL_BOOK = "bet365"  # d'apertura: il bookmaker storico che fa le veci di quelli italiani (come D86)
LIVE_BOOK = "sisal"  # il nome con cui lo studio dal vivo cerca le quote giocabili

Chooser = Callable[[Kind, Sequence[tuple[int, list[dict]]]], list[tuple[int, dict]]]


@dataclass(frozen=True)
class Fixture:
    """Una partita da prevedere: squadre e calendario, niente risultato."""

    id: int
    when: datetime
    league: int
    season: int
    home: int
    away: int


def fixture_of(g: bt.G) -> Fixture:
    return Fixture(g.id, g.date, g.league, g.season, g.home, g.away)


class Vault:
    """Le partite giocate: consegna solo quelle precedenti alla data chiesta."""

    def __init__(self, games: Sequence[bt.G]) -> None:
        self._by_league: dict[int, list[bt.G]] = defaultdict(list)
        for g in sorted(games, key=lambda x: x.date):
            self._by_league[g.league].append(g)
        self._dates = {league: [g.date for g in items] for league, items in self._by_league.items()}

    def before(self, moment: datetime, league: int) -> list[bt.G]:
        """Le partite del campionato giocate prima di `moment`, dalla più vecchia alla più recente."""
        return self._by_league[league][: bisect_left(self._dates.get(league, []), moment)]


def season_label(season: int) -> str:
    return f"{season}/{(season + 1) % 100:02d}"


def week_start(moment: datetime) -> datetime:
    """Il lunedì (ora italiana, mezzanotte) della settimana della partita."""
    local = moment.astimezone(ROME).date()
    return datetime.combine(local - timedelta(days=local.weekday()), time(0), ROME)


def _past(g: bt.G) -> SimpleNamespace:
    """Una partita giocata con i nomi dei campi di Match, per riusare lo studio dal vivo."""
    return SimpleNamespace(home_team_id=g.home, away_team_id=g.away, home_goals=g.hg, away_goals=g.ag, ht_home_goals=g.hh, ht_away_goals=g.ha, season=season_label(g.season))


def _match(f: Fixture) -> SimpleNamespace:
    return SimpleNamespace(home_team_id=f.home, away_team_id=f.away, season=season_label(f.season), home_team=SimpleNamespace(name="casa"), away_team=SimpleNamespace(name="ospite"))


def live_book(book: BookOdds) -> BookOdds:
    """Le quote storiche con il bookmaker storico al posto di quelli italiani (lo studio dal vivo cerca quelli)."""
    return {**book, LIVE_BOOK: book[HISTORICAL_BOOK]} if HISTORICAL_BOOK in book else book


def _pure_goals(fit, f: Fixture, xg: tuple[float, float] | None) -> dict | None:
    """I gol attesi dello studio senza guardare le quote: la voce indipendente dal mercato (D174)."""
    if not (fit.has_team(f.home) and fit.has_team(f.away)):
        return None
    lam, mu = fit.expected_goals(f.home, f.away)
    if xg is not None:
        lam, mu = (1 - XG_WEIGHT) * lam + XG_WEIGHT * xg[0], (1 - XG_WEIGHT) * mu + XG_WEIGHT * xg[1]
    return {"lam": round(float(lam), 4), "mu": round(float(mu), 4), "rho": round(float(fit.rho), 4)}


def replay_studies(vault: Vault, fixtures: Sequence[Fixture], books: Mapping[int, BookOdds], log: Callable[[str], None] = print) -> list[dict]:
    """Lo studio di ogni partita con le sole informazioni fino al lunedì della sua settimana."""
    weeks: dict[datetime, list[Fixture]] = defaultdict(list)
    for f in fixtures:
        weeks[week_start(f.when)].append(f)
    out = []
    for monday in sorted(weeks):
        by_league: dict[int, list[Fixture]] = defaultdict(list)
        for f in weeks[monday]:
            by_league[f.league].append(f)
        for league, todo in by_league.items():
            past = vault.before(monday, league)
            fit, fit_xg = bt._fit(past, monday), bt._fit(past, monday, use_xg=True)
            if fit is None:
                continue
            for f in todo:
                recent = [_past(g) for g in reversed(past) if g.season >= f.season - 1]
                xg = None
                if fit_xg is not None and fit_xg.has_team(f.home) and fit_xg.has_team(f.away) and XG_WEIGHT:
                    xg = fit_xg.expected_goals(f.home, f.away)
                pure = _pure_goals(fit, f, xg)
                data = study_match(_match(f), fit, recent, live_book(books.get(f.id, {})), xg=xg)
                if data is None or not data["picks"]:
                    continue
                picks = [{k: v for k, v in p.items() if k not in ("reasons", "event")} for p in data["picks"]]
                out.append({"id": f.id, "when": f.when.isoformat(), "league": f.league, "season": f.season, "lam": data["lam"], "mu": data["mu"], "pure": pure, "picks": picks})
        log(f"settimana del {monday.date()}: {len(out)} studi")
    return out


def _study_leg(study: dict, pick: dict) -> dict:
    return {
        "match_id": study["id"], "league": study["league"], "market": pick["market"], "selection": pick["selection"], "level": pick["level"],
        "p": pick["p_archie"], "price": round(leg_price(pick), 2), "real_price": bool(pick["prices"]), "from_market": bool(pick.get("from_market")), "status": OPEN,
    }  # fmt: skip


def _value_legs(kind: Kind, pool: Sequence[dict], books: Mapping[int, BookOdds]) -> list[dict]:
    """Le schedine fatte sui prezzi: stessa regola dal vivo, con il bookmaker storico come bookmaker giocabile."""
    if kind.multiplier_legs:
        by_id = {s["id"]: s for s in pool}
        rows = [r for s in pool for r in price_rows(s["id"], s["when"], books.get(s["id"], {}), (HISTORICAL_BOOK,))]
        return [{"match_id": r["match_id"], "league": by_id[r["match_id"]]["league"], "market": r["market"], "selection": r["selection"], "level": kind.key,
                 "p": r["sharp"], "price": r["price"], "real_price": True, "from_market": True, "status": OPEN}
                for r in sorted(best_slip(rows, kind.multiplier_legs, "valore") or [], key=lambda r: r["when"])]  # fmt: skip
    chosen = sorted(best_value(kind, [(s, books.get(s["id"], {})) for s in pool], (HISTORICAL_BOOK,)), key=lambda x: x[0]["when"])
    return [{"match_id": s["id"], "league": s["league"], "market": c.market, "selection": c.selection, "level": kind.key,
             "p": c.fair_probability, "price": c.price, "real_price": True, "from_market": True, "status": OPEN}
            for s, c in chosen]  # fmt: skip


def replay_board(studies: Sequence[dict], books: Mapping[int, BookOdds], first: date, last: date, chooser: Chooser = choose_study_legs) -> list[dict]:
    """Le schedine che la bacheca avrebbe pubblicato ogni giorno alle 10, senza alcun esito."""
    ordered = sorted(studies, key=lambda s: s["when"])
    moments = [datetime.fromisoformat(s["when"]) for s in ordered]
    slips = []
    day = first
    while day <= last:
        for kind, period, start, end in due(datetime.combine(day, PUBLISH_AT, ROME)):
            pool = ordered[bisect_left(moments, start + timedelta(seconds=1)) : bisect_left(moments, end + timedelta(seconds=1))]
            if not pool:
                continue
            if kind.level:
                by_id = {s["id"]: s for s in pool}
                chosen = chooser(kind, [(s["id"], s["picks"]) for s in pool])
                chosen.sort(key=lambda c: by_id[c[0]]["when"])
                legs = [_study_leg(by_id[mid], p) for mid, p in chosen]
            else:
                legs = _value_legs(kind, pool, books)
            totals = slip_totals(kind, legs) if legs else None
            if totals is None:
                continue
            slips.append({"kind": kind.key, "period": period, "legs": legs, "total_odds": round(totals[0], 2), "win_probability": round(totals[1], 4), "status": OPEN})
        day += timedelta(days=1)
    return slips


def seal(slips: Sequence[dict]) -> str:
    """L'impronta delle schedine: se ne cambia anche una virgola, cambia tutta."""
    return hashlib.sha256(json.dumps(slips, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()


def open_seal(slips: Sequence[dict], fingerprint: str, games: Sequence[bt.G]) -> list[dict]:
    """Solo adesso i risultati: esito di ogni pronostico e di ogni schedina. Rifiuta un sigillo cambiato."""
    if seal(slips) != fingerprint:
        raise ValueError("Il sigillo non corrisponde: le schedine sono cambiate dopo la chiusura")
    results = {g.id: g for g in games}
    settled = []
    for slip in slips:
        if slip["kind"] not in KINDS:  # sigilli vecchi: la schedina non esiste più
            continue
        legs = []
        for leg in slip["legs"]:
            g = results.get(leg["match_id"])
            outcome = selection_outcome(leg["market"], leg["selection"], g.hg, g.ag, (g.hh, g.ha)) if g is not None else None
            legs.append({**leg, "status": leg_status("finished", outcome)})
        kind = KINDS[slip["kind"]]
        settled.append({**slip, "legs": legs, "status": slip_status(legs, kind.singles, kind.system)})
    return settled


@dataclass(frozen=True)
class Line:
    """Una riga del confronto: pronostici chiusi, azzeccati contro attesi, e quanto rendono dove la quota è vera."""

    label: str
    n: int
    won: int
    expected: float
    z: float  # scarto da quanto atteso, in errori standard: oltre ±2 le probabilità non sono giuste
    real_n: int
    real_roi: float | None
    real_se: float | None


def leg_lines(settled: Sequence[dict], key: Callable[[dict, dict], str]) -> list[Line]:
    groups: dict[str, list[dict]] = defaultdict(list)
    for slip in settled:
        for leg in slip["legs"]:
            if leg["status"] in (WON, LOST):
                groups[key(slip, leg)].append(leg)
    out = []
    for label, legs in groups.items():
        won = sum(leg["status"] == WON for leg in legs)
        expected = sum(leg["p"] for leg in legs)
        variance = sum(leg["p"] * (1 - leg["p"]) for leg in legs)
        returns = [leg["price"] - 1 if leg["status"] == WON else -1.0 for leg in legs if leg["real_price"]]
        roi, se = None, None
        if len(returns) >= 2:
            roi = sum(returns) / len(returns)
            se = math.sqrt(sum((r - roi) ** 2 for r in returns) / (len(returns) - 1) / len(returns))
        out.append(Line(label, len(legs), won, expected, (won - expected) / math.sqrt(variance) if variance else 0.0, len(returns), roi, se))
    return sorted(out, key=lambda x: -x.n)


def priced_roi(slip: dict, margin: float = ASSUMED_MARGIN) -> float:
    """Guadagno di 1 € sulla schedina, togliendo il margine ipotizzato dove la quota non è vera (multipla: gamba per gamba)."""
    kind = KINDS[slip["kind"]]
    legs = [{**leg, "price": leg["price"] if leg["real_price"] else max(1.0, leg["price"] * (1 - margin))} for leg in slip["legs"]]
    from app.forecast.daily import profit

    total = 1.0
    for leg in legs:
        total *= leg["price"]
    return profit(legs, slip["status"], total, kind.singles, kind.system)


@dataclass(frozen=True)
class KindLine:
    key: str
    published: int
    won: int
    expected: float
    stake: float
    fair_profit: float  # alle quote scritte sulla schedina (dove non c'è una vera è la quota giusta: troppo generosa)
    priced_profit: float  # togliendo il margine ipotizzato dove la quota non è vera
    real_share: float  # quota di pronostici con una quota vera


def kind_lines(settled: Sequence[dict]) -> list[KindLine]:
    summary = stats([SimpleNamespace(**s) for s in settled])
    out = []
    for key, st in summary.items():
        mine = [s for s in settled if s["kind"] == key]
        if not mine:
            continue
        legs = [leg for s in mine for leg in s["legs"]]
        stake = float(sum(len(s["legs"]) if KINDS[key].singles else 1 for s in mine))
        out.append(KindLine(key, st.published, st.won, st.expected, stake, st.profit, sum(priced_roi(s) for s in mine), sum(leg["real_price"] for leg in legs) / len(legs) if legs else 0.0))
    return out


def market_family(market: str) -> str:
    if market in ("1X2", "DC", "DNB"):
        return "esito (1X2, doppia, DNB)"
    if market.startswith(("1T", "2T")):
        return "primo o secondo tempo"
    if market.startswith(("OU", "GG")):
        return "gol della partita"
    if market.startswith("TG"):
        return "gol di una squadra"
    if market.startswith("MG"):
        return "multigol"
    if market.startswith("CB"):
        return "combo"
    return market


def closing_value(leg: dict, closing: Mapping[int, BookOdds]) -> float | None:
    """CLV di un pronostico: quota presa × probabilità giusta alla chiusura di Pinnacle − 1."""
    ref = fair_reference(closing.get(leg["match_id"], {}), leg["market"])
    if ref is None or leg["selection"] not in ref[1] or not leg["real_price"]:
        return None
    return leg["price"] * ref[1][leg["selection"]] - 1


def load_books(db, games: Sequence[bt.G], closing: bool) -> dict[int, BookOdds]:
    """Le quote (d'apertura o di chiusura) delle partite, con gli id di API-Football usati dalle schede."""
    from sqlalchemy import select

    from app.forecast.radar_service import load_book_odds
    from app.models import Match, MatchStatus, TeamAlias

    af = {a.team_id: int(a.alias) for a in db.scalars(select(TeamAlias).where(TeamAlias.source == "api-football")) if a.alias.isdigit()}
    wanted = {(g.date.date().isoformat(), g.home, g.away): g.id for g in games}
    seasons = sorted({season_label(g.season) for g in games})
    db_to_game = {}
    rows = db.execute(select(Match.id, Match.kickoff_at, Match.home_team_id, Match.away_team_id).where(Match.season.in_(seasons), Match.status == MatchStatus.FINISHED))
    for mid, kickoff, home, away in rows:
        game = wanted.get((kickoff.date().isoformat(), af.get(home), af.get(away)))
        if game is not None:
            db_to_game[mid] = game
    return {db_to_game[mid]: book for mid, book in load_book_odds(db, list(db_to_game), closing=closing).items()}


def write_report(settled: Sequence[dict], closing: Mapping[int, BookOdds], log: Callable[[str], None] = print) -> None:
    log(f"{'schedina':<10}{'uscite':>7}{'vinte':>7}{'attese':>8}{'puntato':>9}{'utile*':>9}{'utile**':>9}{'quote vere':>12}")
    for k in kind_lines(settled):
        log(f"{k.key:<10}{k.published:>7}{k.won:>7}{k.expected:>8.1f}{k.stake:>9.0f}{k.fair_profit:>9.1f}{k.priced_profit:>9.1f}{k.real_share:>12.0%}")
    log(f"* alle quote scritte (dove manca una quota vera è la quota giusta: troppo generosa)   ** con margine {ASSUMED_MARGIN:.0%} dove manca la quota vera")
    tables: list[tuple[str, Callable[[dict, dict], str]]] = [
        ("Per schedina", lambda slip, _: slip["kind"]),
        ("Per livello", lambda _, leg: leg["level"]),
        ("Per tipo di mercato", lambda _, leg: market_family(leg["market"])),
        ("Per mercato", lambda _, leg: leg["market"]),
        ("Con o senza i gol del mercato", lambda _, leg: "con" if leg["from_market"] else "senza"),
        ("Per campionato", lambda _, leg: str(leg["league"])),
    ]
    for title, key in tables:
        log(f"\n{title}")
        log(f"{'gruppo':<28}{'n':>6}{'prese':>7}{'attese':>8}{'z':>7}{'n quota vera':>14}{'rend. vero':>16}")
        for line in leg_lines(settled, key)[:18]:
            roi = f"{line.real_roi:+.1%} ±{line.real_se:.1%}" if line.real_roi is not None and line.real_se is not None else "-"
            log(f"{line.label:<28}{line.n:>6}{line.won:>7}{line.expected:>8.1f}{line.z:>7.1f}{line.real_n:>14}{roi:>16}")
    log("")
    for key in KINDS:
        clvs = [v for s in settled if s["kind"] == key for leg in s["legs"] if (v := closing_value(leg, closing)) is not None]
        if clvs:
            log(f"CLV medio con quota vera, {key}: {sum(clvs) / len(clvs):+.2%} su {len(clvs)}")
