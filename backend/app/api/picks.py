"""Pronostici (D67): la stima migliore per ogni partita in programma, con le quote di Sisal ed Eurobet."""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from typing import Any, Literal
from zoneinfo import ZoneInfo

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app.api.football import BOOKMAKER_LABELS, MatchCard, match_cards
from app.auth.deps import CurrentUser, DbSession
from app.config import get_settings
from app.forecast.clv import SUSPICIOUS_VALUE
from app.forecast.data import ODDS_MARKETS
from app.forecast.multiple import LEGS, PROFILES, build_multiple, custom_profile, why_none
from app.forecast.picks import MODEL_SOURCE, MarketPick, favorite, market_family, off_line
from app.forecast.picks_service import legs_for, match_market_picks, upcoming_picks
from app.forecast.suggestions import suggestions
from app.models import Match
from app.ingest.teams import competition_sort_key

router = APIRouter(prefix="/api/picks", tags=["pronostici"])

SOURCE_LABELS = BOOKMAKER_LABELS | {"archie": "Modello di Archie", "consenso": "Media dei bookmaker italiani"}


class OfferOut(BaseModel):
    bookmaker: str
    price: float
    value: float
    verdict: str  # "valore" | "nella norma" | "paga poco"


class MarketOut(BaseModel):
    market: str
    source: str  # etichetta della fonte della probabilità
    from_model: bool
    probabilities: dict[str, float]
    offers: dict[str, list[OfferOut]]


class PickOut(BaseModel):
    match: MatchCard
    favorite: str | None  # esito 1X2 più probabile
    favorite_probability: float | None
    markets: list[MarketOut]
    signals: int  # occasioni del radar su questa partita


class PicksOut(BaseModel):
    bookmakers: list[str]
    picks: list[PickOut]


@router.get("")
def picks(_: CurrentUser, db: DbSession, days: int = Query(7, ge=1, le=14)) -> PicksOut:
    now = datetime.now(UTC)
    bookmakers = get_settings().radar_bookmaker_list
    upcoming = upcoming_picks(db, now, now + timedelta(days=days), bookmakers)
    matches = [m for m, _ in upcoming]
    # Occasioni sui bookmaker di Giuse: esiti dei mercati del radar con almeno una quota "valore" (stessa regola, D72/D74)
    signals = {
        m.id: len({(p.market, sel) for p in mp if p.market in ODDS_MARKETS for sel, offers in p.offers.items() if any(o.verdict == "valore" for o in offers)})
        for m, mp in upcoming
    }

    cards = {c.id: c for c in match_cards(db, matches, now)}
    out = []
    for m, market_picks in sorted(upcoming, key=lambda mp: (mp[0].kickoff_at, competition_sort_key(mp[0].competition))):
        fav = favorite(market_picks)
        out.append(
            PickOut(
                match=cards[m.id],
                favorite=fav[0] if fav else None,
                favorite_probability=fav[1] if fav else None,
                markets=[market_out(p) for p in market_picks],
                signals=signals.get(m.id, 0),
            )
        )
    return PicksOut(bookmakers=[BOOKMAKER_LABELS.get(b, b) for b in bookmakers], picks=out)


def offer_out(o) -> OfferOut:
    return OfferOut(bookmaker=BOOKMAKER_LABELS.get(o.bookmaker, o.bookmaker), price=o.price, value=o.value, verdict=o.verdict)


def market_out(p: MarketPick) -> MarketOut:
    return MarketOut(
        market=p.market,
        source=SOURCE_LABELS.get(p.source, p.source) + (" · corretta da Archie" if p.corrected else ""),
        from_model=p.source == MODEL_SOURCE,
        probabilities=p.probabilities,
        offers={sel: [offer_out(o) for o in offers] for sel, offers in p.offers.items()},
    )


# ---------- I due pronostici della pagina partita (D107) ----------


class SuggestionOut(BaseModel):
    kind: str  # "sicuro" | "spinto"
    market: str
    selection: str
    probability: float
    source: str
    offer: OfferOut
    has_value: bool


class MatchPicksOut(BaseModel):
    suggestions: list[SuggestionOut]
    markets: list[MarketOut]


@router.get("/match/{match_id}")
def match_picks_out(match_id: int, _: CurrentUser, db: DbSession) -> MatchPicksOut:
    match = db.get(Match, match_id)
    if match is None:
        raise HTTPException(404, "Partita non trovata")
    picks = match_market_picks(db, match, get_settings().radar_bookmaker_list) if match.status == "scheduled" else []
    return MatchPicksOut(
        suggestions=[SuggestionOut(kind=s.kind, market=s.market, selection=s.selection, probability=s.probability,
                                   source=SOURCE_LABELS.get(s.source, s.source), offer=offer_out(s.offer), has_value=s.has_value)
                     for s in suggestions(picks)],  # fmt: skip
        markets=[market_out(p) for p in picks],
    )


# ---------- Numeri attesi della partita: tiri, angoli, cartellini (D109) ----------

STAT_LABELS = {"shots": "Tiri", "corners": "Angoli", "cards": "Cartellini"}
STAT_MARKETS = {"corners": "COR", "cards": "CRD"}  # mercati del radar con le quote vere (D94); i tiri non li quota nessuno


class LineOut(BaseModel):
    side: str  # "totale" | "casa" | "ospite"
    line: float
    p_over: float
    fair_over: float
    fair_under: float
    offers: dict[str, dict[str, float]]  # bookmaker → {"over": quota, "under": quota}, se quotato


class NumbersOut(BaseModel):
    stat: str
    label: str
    home: float
    away: float
    lines: list[LineOut]


@router.get("/match/{match_id}/numbers")
def match_numbers(match_id: int, _: CurrentUser, db: DbSession) -> list[NumbersOut]:
    """Tiri, angoli e cartellini attesi con le quote giuste di Archie (modello D108-D109, non messo alla prova contro il mercato)."""
    from sqlalchemy import select

    from app.forecast.counts import CountGame, expected_counts
    from app.forecast.radar_markets import secondary_name
    from app.forecast.radar_service import load_book_odds

    match = db.get(Match, match_id)
    if match is None:
        raise HTTPException(404, "Partita non trovata")
    start_year = int(match.season[:4])
    seasons = [match.season, f"{start_year - 1}/{str(start_year)[-2:]}"]
    past = db.scalars(select(Match).where(Match.competition_id == match.competition_id, Match.season.in_(seasons),
                                          Match.status == "finished", Match.kickoff_at < match.kickoff_at)).all()  # fmt: skip
    games = []
    for m in past:
        vals = (m.home_shots, m.away_shots, m.home_corners, m.away_corners, m.home_yellow, m.away_yellow, m.home_red, m.away_red)
        if all(v is not None for v in vals):
            games.append(CountGame(m.id, match.competition.code, m.season, m.kickoff_at, m.home_team_id, m.away_team_id,
                                   {"shots": (m.home_shots, m.away_shots), "corners": (m.home_corners, m.away_corners),
                                    "cards": (m.home_yellow + m.home_red, m.away_yellow + m.away_red)}))  # fmt: skip
    if not any(g.season == match.season for g in games):
        return []  # niente statistiche nel campionato (es. Serie C): nessun numero
    target = CountGame(match.id, match.competition.code, match.season, match.kickoff_at, match.home_team_id, match.away_team_id,
                       {"shots": (0, 0), "corners": (0, 0), "cards": (0, 0)})  # fmt: skip
    book = load_book_odds(db, [match.id], closing=False).get(match.id, {})
    out = []
    for e in expected_counts(games, target):
        lines = []
        for side, probs in (("totale", e.total_over), ("casa", e.home_over), ("ospite", e.away_over)):
            for line, p in probs.items():
                offers = {}
                if e.stat in STAT_MARKETS:
                    family = "angoli" if e.stat == "corners" else "cartellini"
                    market = secondary_name(family, side, line)
                    offers = {BOOKMAKER_LABELS.get(bm, bm): prices[market] for bm, prices in book.items() if market in prices}
                lines.append(LineOut(side=side, line=line, p_over=p, fair_over=1 / max(p, 1e-6), fair_under=1 / max(1 - p, 1e-6), offers=offers))
        out.append(NumbersOut(stat=e.stat, label=STAT_LABELS[e.stat], home=e.home, away=e.away, lines=lines))
    return out


# ---------- Tiri dei giocatori (D110-D111) ----------


class PlayerOut(BaseModel):
    side: str  # "casa" | "ospite"
    name: str
    position: str
    exp_shots: float
    exp_on: float
    p_shot: float
    p_two: float
    p_on: float
    absent: str | None = None  # assente o squalificato secondo le notizie (Archie tifoso): il dettaglio


def news_absences(facts: Sequence) -> dict[str, str]:
    """Cognome (minuscolo) → dettaglio, per i giocatori con un'assenza o squalifica non seguita da un rientro."""
    out: dict[str, str] = {}
    for f in sorted(facts, key=lambda x: x.published_at):
        if not f.player:
            continue
        key = f.player.split()[-1].lower()
        if f.kind in ("assente", "squalifica"):
            out[key] = f.detail
        elif f.kind == "rientro":
            out.pop(key, None)
    return out


@dataclass(frozen=True)
class _AfContext:
    """Partita di Serie A o B vista da API-Football: dati dei giocatori in cache e assenti secondo le notizie."""

    fixture: Any  # AFFixture
    league: int
    season: int
    games: list
    absent: dict[str, dict[str, str]]  # "casa" / "ospite" → cognome → dettaglio


def _af_context(db, match: Match) -> _AfContext | None:
    from sqlalchemy import select

    from app.adapters.cache import FileCache
    from app.ingest.af_stats import STATS_LEAGUES, load_player_games, season_fixtures
    from app.ingest.news import FACTS_WINDOW
    from app.models import MatchSource, TeamFact

    source = db.scalar(select(MatchSource).where(MatchSource.match_id == match.id, MatchSource.source == "api-football"))
    if source is None:
        return None
    cache = FileCache(get_settings().data_cache_dir, "api-football")
    season = int(match.season[:4])
    for league in STATS_LEAGUES:
        fx = next((f for f in season_fixtures(cache, league, season) if str(f.id) == source.external_id), None)
        if fx is None:
            continue
        facts = db.scalars(select(TeamFact).where(TeamFact.team_id.in_([match.home_team_id, match.away_team_id]),
                                                  TeamFact.published_at >= match.kickoff_at - FACTS_WINDOW)).all()  # fmt: skip
        absent = {side: news_absences([f for f in facts if f.team_id == team]) for side, team in (("casa", match.home_team_id), ("ospite", match.away_team_id))}
        return _AfContext(fx, league, season, load_player_games(cache, league, season), absent)
    return None


def _absence_note(absent: dict[str, str], name: str) -> str | None:
    return next((d for k, d in absent.items() if k in name.lower().split()), None)


@router.get("/match/{match_id}/players")
def match_players(match_id: int, _: CurrentUser, db: DbSession) -> list[PlayerOut]:
    """Tiri attesi dei giocatori e probabilità di Over 0,5 / 1,5 tiri e Over 0,5 in porta (solo Serie A e B, dalla cache)."""
    from app.forecast.player_props import outlook

    match = db.get(Match, match_id)
    if match is None:
        raise HTTPException(404, "Partita non trovata")
    ctx = _af_context(db, match) if match.status == "scheduled" else None
    if ctx is None:
        return []
    fx = ctx.fixture
    out = []
    for o in outlook(ctx.games, fx.id, ctx.league, ctx.season, fx.kickoff_at, fx.home.id, fx.away.id):
        side = "casa" if o.team == fx.home.id else "ospite"
        out.append(PlayerOut(side=side, name=o.name, position=o.position, exp_shots=o.exp_shots, exp_on=o.exp_on,
                             p_shot=o.p_shot, p_two=o.p_two, p_on=o.p_on, absent=_absence_note(ctx.absent[side], o.name)))  # fmt: skip
    return sorted(out, key=lambda p: (p.absent is not None, -p.exp_shots))


# ---------- Formazioni (D123) e piano partita live (D124) ----------

OFFICIAL_BEFORE = timedelta(minutes=90)  # le formazioni ufficiali escono circa un'ora prima
OFFICIAL_REFRESH = timedelta(minutes=10)


class LineupPlayer(BaseModel):
    name: str
    position: str
    p_start: float | None  # titolare (pesato) nelle ultime 5 partite
    absent: str | None = None


class TeamLineup(BaseModel):
    side: str  # "casa" | "ospite"
    official: bool
    eleven: list[LineupPlayer]
    doubtful: list[LineupPlayer]
    out: list[LineupPlayer]  # assenti secondo le notizie tra i titolari abituali
    based_on: int


@router.get("/match/{match_id}/lineups")
def match_lineups(match_id: int, _: CurrentUser, db: DbSession) -> list[TeamLineup]:
    """Formazioni previste (l'ultima, senza gli assenti delle notizie: D123) o ufficiali se già uscite. Serie A e B."""
    from app.adapters.api_football import ApiFootballAdapter
    from app.adapters.cache import FileCache
    from app.forecast.lineups import predicted_lineup, recent_starts

    match = db.get(Match, match_id)
    if match is None:
        raise HTTPException(404, "Partita non trovata")
    ctx = _af_context(db, match) if match.status == "scheduled" else None
    if ctx is None:
        return []
    fx = ctx.fixture
    now = datetime.now(UTC)
    official = {}
    settings = get_settings()
    if settings.api_football_key and fx.kickoff_at - now <= OFFICIAL_BEFORE:
        af = ApiFootballAdapter(FileCache(settings.data_cache_dir, "api-football"), settings.api_football_key)
        try:
            official = {lu.team_id: lu.starters for lu in af.lineups(fx.id, OFFICIAL_REFRESH)}
        except Exception:  # API non raggiungibile: restano le previste
            official = {}
    out = []
    for side, team in (("casa", fx.home.id), ("ospite", fx.away.id)):
        ranked, recent = recent_starts(ctx.games, team, fx.kickoff_at)
        info = {p.player: p for p in ranked}
        absent_ids = {p.player for p in ranked if _absence_note(ctx.absent[side], p.name)}

        def row(pid: int) -> LineupPlayer:
            p = info.get(pid)
            if p is None:
                return LineupPlayer(name=f"giocatore {pid}", position="?", p_start=None)
            return LineupPlayer(name=p.name, position=p.position, p_start=p.p_start, absent=_absence_note(ctx.absent[side], p.name))

        missing = [row(pid) for pid in absent_ids if info[pid].p_start >= 0.3]
        if team in official and official[team]:
            order = {"G": 0, "D": 1, "M": 2, "F": 3}
            eleven = sorted((row(pid) for pid in official[team]), key=lambda r: order.get(r.position, 9))
            out.append(TeamLineup(side=side, official=True, eleven=eleven, doubtful=[], out=missing, based_on=len(recent)))
            continue
        lineup = predicted_lineup(ctx.games, team, fx.kickoff_at, absent_ids)
        if lineup is None:
            continue
        out.append(TeamLineup(side=side, official=False, eleven=[row(p.player) for p in lineup.eleven],
                              doubtful=[row(p.player) for p in lineup.doubtful], out=missing, based_on=lineup.based_on))  # fmt: skip
    return out


# ---------- Multipla del giorno (D68) ----------

ROME = ZoneInfo("Europe/Rome")


class LegOut(BaseModel):
    match: MatchCard
    market: str
    selection: str
    probability: float
    price: float
    value: float
    source: str = "pinnacle"  # da dove viene la probabilità: "consenso" = media dei bookmaker italiani (Serie C, D130)


class MultipleOut(BaseModel):
    bookmaker: str
    legs: list[LegOut]
    with_value: bool
    quality: str = "valore"  # "valore" | "nella norma" | "paga poco" (D130)
    price: float
    win_probability: float
    one_in: float
    alive_before_last: float
    expected_value: float


# Oggi, domani, oggi+domani, prossimi 3 giorni, 7 giorni, oppure dal giorno al giorno (D83)
Horizon = Literal["today", "tomorrow", "2days", "3days", "week", "range"]
MAX_DAYS_AHEAD = 7  # oltre non ci sono ancora quote


class MultiplesOut(BaseModel):
    horizon: Horizon
    profile: str
    legs: int
    multiples: list[MultipleOut]  # una per bookmaker di Giuse
    missing: list[str]  # bookmaker per cui oggi non c'è una multipla sensata
    hint: str | None = None  # se non c'è nessuna multipla: perché, e cosa provare (D134)


def _midnight(day: date) -> datetime:
    """Mezzanotte italiana all'inizio del giorno, in UTC."""
    return datetime.combine(day, time(0), ROME).astimezone(UTC)


def horizon_window(now: datetime, horizon: str, date_from: date | None = None, date_to: date | None = None) -> tuple[datetime, datetime]:
    """Da quando a quando cercare le partite: i giorni sono quelli italiani (finiscono a mezzanotte)."""
    today = now.astimezone(ROME).date()
    days = {"today": 1, "2days": 2, "3days": 3}
    if horizon in days:
        return now, _midnight(today + timedelta(days=days[horizon]))
    if horizon == "tomorrow":
        return _midnight(today + timedelta(days=1)), _midnight(today + timedelta(days=2))
    if horizon == "range":
        if date_from is None or date_to is None or date_to < date_from:
            raise ValueError("servono date_from e date_to, con date_to non prima di date_from")
        return max(now, _midnight(date_from)), min(_midnight(date_to + timedelta(days=1)), now + timedelta(days=MAX_DAYS_AHEAD))
    return now, now + timedelta(days=MAX_DAYS_AHEAD)


def horizon_end(now: datetime, horizon: str) -> datetime:
    """Fine dell'orizzonte (mezzanotte italiana di oggi, oppure tra 7 giorni, ...)."""
    return horizon_window(now, horizon)[1]


@router.get("/multiple")
def multiple(
    _: CurrentUser,
    db: DbSession,
    horizon: Horizon = "today",
    date_from: date | None = Query(None, description="Con horizon=range: primo giorno, AAAA-MM-GG"),
    date_to: date | None = Query(None, description="Con horizon=range: ultimo giorno, AAAA-MM-GG"),
    profile: Literal["molto tranquilla", "tranquilla", "equilibrata", "coraggiosa", "spericolata", "caccia al clv", "personalizzata"] = "equilibrata",
    legs: int = Query(LEGS, ge=2, le=6),
    min_probability: float = Query(0.6, ge=0.2, le=0.95, description="Profilo personalizzato: probabilità minima di ogni partita"),
    min_total: float = Query(2.0, ge=1.2, le=200, description="Profilo personalizzato: quota totale minima"),
    max_total: float = Query(6.0, ge=1.2, le=200, description="Profilo personalizzato: quota totale massima"),
    by: Literal["probabilita", "valore"] = Query("probabilita", description="Profilo personalizzato: cosa privilegiare"),
    markets: str | None = Query(None, description="Mercati separati da virgola, es. 1X2,DC,OU2.5,angoli,cartellini"),
    competitions: str | None = Query(None, description="Codici dei campionati separati da virgola, es. ITA-A,ENG-1"),
) -> MultiplesOut:
    """Multipla del giorno (senza parametri) o generatore "Archie, fammi una multipla"."""
    now = datetime.now(UTC)
    bookmakers = get_settings().radar_bookmaker_list
    try:
        start, end = horizon_window(now, horizon, date_from, date_to)
    except ValueError as error:
        raise HTTPException(422, str(error)) from error
    upcoming = upcoming_picks(db, start, end, bookmakers)
    if competitions:
        wanted = set(competitions.split(","))
        upcoming = [(m, mp) for m, mp in upcoming if m.competition.code in wanted]
    if markets:
        allowed = set(markets.split(","))
        upcoming = [(m, [p for p in mp if p.market in allowed or market_family(p.market) in allowed]) for m, mp in upcoming]
    cards = {c.id: c for c in match_cards(db, [m for m, _ in upcoming], now)}
    multiples, missing = [], []
    chosen = custom_profile(min_probability, min_total, max_total, by == "valore") if profile == "personalizzata" else PROFILES[profile]
    hint = None
    for bm in bookmakers:
        label = BOOKMAKER_LABELS.get(bm, bm)
        bm_legs = legs_for(upcoming, bm)
        best = build_multiple(bm_legs, legs, chosen)
        if best is None and hint is None:
            hint = why_none(bm_legs, legs, chosen)
        if best is None:
            missing.append(label)
            continue
        multiples.append(
            MultipleOut(
                bookmaker=label,
                legs=[
                    LegOut(match=cards[leg.match_id], market=leg.market, selection=leg.selection,
                           probability=leg.probability, price=leg.price, value=leg.value, source=leg.source)
                    for leg in best.legs
                ],
                with_value=best.with_value,
                quality=best.quality,
                price=best.price,
                win_probability=best.win_probability,
                one_in=best.one_in,
                alive_before_last=best.alive_before_last,
                expected_value=best.expected_value,
            )
        )
    return MultiplesOut(horizon=horizon, profile=profile, legs=legs, multiples=multiples, missing=missing, hint=None if multiples else hint)


# ---------- Quote fuori linea oggi (D70) ----------


class OffLineOut(BaseModel):
    match: MatchCard
    market: str
    selection: str
    probability: float
    bookmaker: str
    price: float
    value: float
    suspicious: bool  # sopra il 15%: probabile errore, rischio annullamento (regola 4)


@router.get("/off-line")
def off_line_today(_: CurrentUser, db: DbSession) -> list[OffLineOut]:
    """Quote di Sisal ed Eurobet di oggi molto sopra il giusto (≥ 8%)."""
    now = datetime.now(UTC)
    upcoming = upcoming_picks(db, now, horizon_end(now, "today"), get_settings().radar_bookmaker_list)
    cards = {c.id: c for c in match_cards(db, [m for m, _ in upcoming], now)}
    rows = [
        OffLineOut(
            match=cards[m.id], market=x.market, selection=x.selection, probability=x.probability,
            bookmaker=BOOKMAKER_LABELS.get(x.offer.bookmaker, x.offer.bookmaker), price=x.offer.price,
            value=x.offer.value, suspicious=x.offer.value > SUSPICIOUS_VALUE,
        )
        for m, market_picks in upcoming
        for x in off_line(market_picks)
    ]  # fmt: skip
    return sorted(rows, key=lambda r: r.value, reverse=True)
