"""Studio delle partite in programma (D137): dati dal database, modello per paese, salvataggio in `match_studies`."""

from collections import defaultdict
from collections.abc import Iterable, Sequence
from datetime import UTC, datetime, timedelta

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.forecast.data import load_games
from app.forecast.dixon_coles import DixonColesFit
from app.forecast.model import ModelConfig, fit_at
from app.forecast.radar_service import load_book_odds
from app.forecast.study import (
    MIN_SAMPLE,
    Adjustment,
    Played,
    TableSpot,
    BOOK_GAP,
    book_probability,
    favored_side,
    first_half_share,
    half_of,
    half_trait,
    model_probabilities,
    trait_text,
    motivation_adjustment,
    news_adjustment,
    study_picks,
    weather_adjustment,
)
from app.ingest.teams import CUP_COUNTRY
from app.models import Competition, Match, MatchInsight, MatchStatus, MatchStudy

STUDY_DAYS = 8  # partite dei prossimi giorni
XG_WEIGHT = 0.75  # gol attesi = 25% modello sui gol + 75% modello sugli xG (prova D140, dove gli xG ci sono)
XG_SEASONS = 3  # stagioni di schede (xG) per il modello sugli xG
WEATHER_DAYS = 3  # meteo previsto solo per le partite dei prossimi 3 giorni
SAMPLE = 10  # ultime partite in casa (o in trasferta) guardate per i fatti
PLAYABLE = ("sisal", "eurobet")


def season_before(season: str) -> str:
    """"2026/27" → "2025/26"."""
    start = int(season[:4]) - 1
    return f"{start}/{str(start + 1)[-2:]}"


def league_fit(games: Sequence, now: datetime) -> DixonColesFit | None:
    """Gol attesi di un campionato: Dixon-Coles con pesi nel tempo, un modello per campionato (prova D140)."""
    if not games:
        return None
    return fit_at(games, [g.kickoff_at for g in games], now, ModelConfig(elo_prior=False))


def xg_fit(adapter, af_league: int, season_start: int, now: datetime) -> DixonColesFit | None:
    """Modello sugli xG del campionato dalle schede di API-Football (D140), con gli id delle squadre di API-Football."""
    from app.forecast.dixon_coles import fit_dixon_coles, time_decay_weights
    from app.ingest.af_detail import FOREVER, load_details

    rows = []
    for season in range(season_start - XG_SEASONS + 1, season_start + 1):
        try:
            fixtures = adapter.fixtures(af_league, season, FOREVER)
        except Exception:  # calendario non in cache e fonte non raggiungibile: niente xG
            continue
        for d in load_details(adapter.cache, [f.id for f in fixtures]):
            stats = d.get("stats") or {}
            xh, xa = (stats.get("home") or {}).get("xg"), (stats.get("away") or {}).get("xg")
            when = datetime.fromisoformat(d["date"])
            if xh is not None and xa is not None and when < now:
                rows.append((d["home"], d["away"], xh, xa, when))
    if len(rows) < 50:
        return None
    fit = fit_dixon_coles([r[0] for r in rows], [r[1] for r in rows], [r[2] for r in rows], [r[3] for r in rows],
                          weights=time_decay_weights([r[4] for r in rows], now, ModelConfig().xi_per_day), ridge=ModelConfig().ridge)  # fmt: skip
    return fit


def _finished(db: Session, competition_id: int, seasons: Iterable[str], before: datetime) -> list[Match]:
    return list(db.scalars(
        select(Match).where(Match.competition_id == competition_id, Match.season.in_(list(seasons)), Match.status == MatchStatus.FINISHED,
                            Match.home_goals.is_not(None), Match.ht_home_goals.is_not(None), Match.kickoff_at < before)
        .order_by(Match.kickoff_at.desc())
    ))  # fmt: skip


def played(games: Sequence[Match], team_id: int, at_home: bool, season: str) -> list[Played]:
    """Le ultime partite della squadra in casa (o in trasferta): questa stagione, e la scorsa se sono poche."""
    def view(m: Match) -> Played:
        if at_home:
            return Played(m.home_goals, m.away_goals, m.ht_home_goals, m.ht_away_goals)
        return Played(m.away_goals, m.home_goals, m.ht_away_goals, m.ht_home_goals)

    mine = [m for m in games if (m.home_team_id if at_home else m.away_team_id) == team_id]
    this = [view(m) for m in mine if m.season == season][:SAMPLE]
    if len(this) >= MIN_SAMPLE + 2:
        return this
    return (this + [view(m) for m in mine if m.season != season])[:SAMPLE]


def form(games: Sequence[Match], team_id: int, n: int = 5) -> str:
    """Ultime n partite del campionato: "VVNPV" (dalla più vecchia alla più recente)."""
    out = []
    for m in games:
        if team_id not in (m.home_team_id, m.away_team_id):
            continue
        mine, theirs = (m.home_goals, m.away_goals) if m.home_team_id == team_id else (m.away_goals, m.home_goals)
        out.append("V" if mine > theirs else "N" if mine == theirs else "P")
        if len(out) == n:
            break
    return "".join(reversed(out))


def shares(games: Sequence[Match], home_id: int, away_id: int) -> tuple[float, float]:
    """Parte dei gol nel primo tempo per i gol di casa e per quelli dell'ospite (attacco di chi segna e difesa di chi subisce)."""
    goals = sum(m.home_goals + m.away_goals for m in games)
    league = sum(m.ht_home_goals + m.ht_away_goals for m in games) / goals if goals else 0.45
    scored, scored_1h, conceded, conceded_1h = defaultdict(int), defaultdict(int), defaultdict(int), defaultdict(int)
    for m in games:
        for team, s, s1, c, c1 in ((m.home_team_id, m.home_goals, m.ht_home_goals, m.away_goals, m.ht_away_goals),
                                   (m.away_team_id, m.away_goals, m.ht_away_goals, m.home_goals, m.ht_home_goals)):  # fmt: skip
            scored[team] += s
            scored_1h[team] += s1
            conceded[team] += c
            conceded_1h[team] += c1

    def mix(attacker: int, defender: int) -> float:
        return (first_half_share(scored_1h[attacker], scored[attacker], league) + first_half_share(conceded_1h[defender], conceded[defender], league)) / 2

    return mix(home_id, away_id), mix(away_id, home_id)


def table(games: Sequence[Match], season: str) -> dict[int, TableSpot]:
    """Classifica della stagione dai risultati (punti, poi differenza reti), con i riferimenti di vertice e salvezza."""
    pts, played, diff = defaultdict(int), defaultdict(int), defaultdict(int)
    for m in games:
        if m.season != season:
            continue
        for team, mine, theirs in ((m.home_team_id, m.home_goals, m.away_goals), (m.away_team_id, m.away_goals, m.home_goals)):
            played[team] += 1
            diff[team] += mine - theirs
            pts[team] += 3 if mine > theirs else 1 if mine == theirs else 0
    order = sorted(played, key=lambda t: (pts[t], diff[t]), reverse=True)
    if len(order) < 6:
        return {}
    n = len(order)
    top, safe = pts[order[1]], pts[order[n - 4]]  # seconda in classifica; prima fuori dalle ultime tre
    return {t: TableSpot(i + 1, n, pts[t], played[t], top, safe) for i, t in enumerate(order)}


def traits(games: Sequence[Match], team_id: int, name: str) -> list[tuple[str, str, bool]]:
    """Tratti per tempo della squadra che non sono un caso (D143): (tempo, testo, riguarda i gol fatti)."""
    goals = sum(m.home_goals + m.away_goals for m in games)
    league = sum(m.ht_home_goals + m.ht_away_goals for m in games) / goals if goals else 0.45
    s = s1 = c = c1 = 0
    for m in games:
        if m.home_team_id == team_id:
            s, s1, c, c1 = s + m.home_goals, s1 + m.ht_home_goals, c + m.away_goals, c1 + m.ht_away_goals
        elif m.away_team_id == team_id:
            s, s1, c, c1 = s + m.away_goals, s1 + m.ht_away_goals, c + m.home_goals, c1 + m.ht_home_goals
    out = []
    for scored, total, first in ((True, s, s1), (False, c, c1)):
        found = half_trait(first, total, league)
        if found:
            out.append((found[0], trait_text(name, scored, found[0], found[1], league), scored))
    return out


def caution_for(db: Session, m: Match, team_id: int, name: str, insight: MatchInsight | None, side: str) -> list[str]:
    """Segnali di prudenza su una squadra (D143): partita ravvicinata, assenze annunciate, notizie contro."""
    from app.ingest.news import FACTS_WINDOW
    from app.models import TeamFact

    out = []
    kickoff = m.kickoff_at if m.kickoff_at.tzinfo else m.kickoff_at.replace(tzinfo=UTC)
    last = db.scalar(select(Match).where(or_(Match.home_team_id == team_id, Match.away_team_id == team_id), Match.status == MatchStatus.FINISHED,
                                         Match.kickoff_at < kickoff).order_by(Match.kickoff_at.desc()).limit(1))  # fmt: skip
    if last is not None:
        last_at = last.kickoff_at if last.kickoff_at.tzinfo else last.kickoff_at.replace(tzinfo=UTC)
        days = (kickoff - last_at).total_seconds() / 86400
        if days <= 3.5:
            europe = last.competition.country == CUP_COUNTRY
            away = last.away_team_id == team_id
            where = f"in trasferta in {last.competition.name}" if europe and away else f"in {last.competition.name}"
            out.append(f"⚠ Prudenza: {name} ha giocato {where} {days:.0f} giorni prima.")
    since = kickoff - min(FACTS_WINDOW, timedelta(days=7))
    absent = {f.player for f in db.scalars(select(TeamFact).where(TeamFact.team_id == team_id, TeamFact.kind.in_(("assente", "squalifica")),
                                                                     TeamFact.published_at >= since, TeamFact.published_at <= kickoff)) if f.player}  # fmt: skip
    if len(absent) >= 2:
        out.append(f"⚠ Prudenza: {name} ha assenze annunciate ({', '.join(sorted(absent)[:4])}).")
    if insight is not None and insight.strength == "netta" and insight.side in ("home", "away") and insight.side != side:
        out.append(f"⚠ Prudenza: le notizie favoriscono nettamente l'avversaria di {name}.")
    return out


def study_match(m: Match, fit: DixonColesFit, games: Sequence[Match], book: dict, adjustment: Adjustment = Adjustment(),
                xg: tuple[float, float] | None = None, caution: dict[str, list[str]] | None = None) -> dict | None:
    """Lo studio completo di una partita, pronto da salvare (None se mancano i dati).
    `xg`: gol attesi dal modello sugli xG, se il campionato li ha (si mescolano con quelli sui gol, D140)."""
    if not (fit.has_team(m.home_team_id) and fit.has_team(m.away_team_id)):
        return None
    lam, mu = fit.expected_goals(m.home_team_id, m.away_team_id)
    if xg is not None:
        lam, mu = (1 - XG_WEIGHT) * lam + XG_WEIGHT * xg[0], (1 - XG_WEIGHT) * mu + XG_WEIGHT * xg[1]
    lam, mu = lam * adjustment.home, mu * adjustment.away
    share_home, share_away = shares(games, m.home_team_id, m.away_team_id)
    probs = model_probabilities(lam, mu, fit.rho, share_home, share_away)
    home_games = played(games, m.home_team_id, True, m.season)
    away_games = played(games, m.away_team_id, False, m.season)
    home, away = m.home_team.name, m.away_team.name
    form_home, form_away = form(games, m.home_team_id), form(games, m.away_team_id)
    context = [f"Forma nelle ultime 5 di campionato: {home} {form_home or '—'}, {away} {form_away or '—'}.", *adjustment.reasons]
    if (adjustment.home, adjustment.away) != (1.0, 1.0):
        context.append("Notizie, classifica e meteo correggono di poco i gol attesi: correzioni prudenti, non ancora verificate sul passato.")
    caution = caution or {}
    team_traits = {"home": traits(games, m.home_team_id, home), "away": traits(games, m.away_team_id, away)}
    picks = []
    for p in study_picks(probs, home_games, away_games, home, away):
        prices = {bm: price for bm in PLAYABLE if (price := book.get(bm, {}).get(p.market, {}).get(p.selection))}
        half = half_of(p.market)
        supporting = []
        if half and p.selection == "over":  # un tratto vero del tempo giusto sostiene un "segna"/"almeno un gol" in quel tempo
            for side, items in team_traits.items():
                for trait_half, text, scored in items:
                    concerns = ("TGH" in p.market and (side, scored) in (("home", True), ("away", False))) or \
                               ("TGA" in p.market and (side, scored) in (("away", True), ("home", False))) or "OU" in p.market
                    if trait_half == half and concerns:
                        supporting.append(text)
        warned = list(caution.get(favored_side(p.market, p.selection) or "", []))
        p_book = book_probability(book, p.market, p.selection, PLAYABLE)
        if p_book is not None and p.p_archie - p_book >= BOOK_GAP:
            warned.append(f"⚠ Il bookmaker non è d'accordo: la quota dice {p_book:.0%}. Sul passato, in questi casi ha avuto ragione quasi sempre lui.")
        picks.append({
            "market": p.market, "selection": p.selection, "level": p.level, "event": p.event,
            "p_model": round(p.p_model, 4), "p_archie": round(p.p_archie, 4),
            "evidence": [p.evidence.home_hits, p.evidence.home_n, p.evidence.away_hits, p.evidence.away_n],
            "reasons": [*p.reasons, *supporting, *warned, *context], "prices": prices,
            "traits": supporting, "caution": warned, "p_book": round(p_book, 4) if p_book is not None else None,
        })  # fmt: skip
    return {
        "lam": round(lam, 3), "mu": round(mu, 3), "rho": round(fit.rho, 4), "xg": xg is not None,
        "share_home": round(share_home, 3), "share_away": round(share_away, 3),
        "form_home": form_home, "form_away": form_away, "notes": list(adjustment.reasons), "picks": picks,
    }  # fmt: skip


def _api_football(db: Session):
    """Adattatore di API-Football (solo cache, se possibile), id API-Football di ogni squadra, id dei campionati."""
    from app.adapters.api_football import LEAGUES
    from app.config import get_settings
    from app.models import TeamAlias

    settings = get_settings()
    if not settings.api_football_key:
        return None, {}, {}
    from app.jobs import api_football_adapter

    af_of_team = {a.team_id: int(a.alias) for a in db.scalars(select(TeamAlias).where(TeamAlias.source == "api-football")) if a.alias.isdigit()}
    return api_football_adapter(db, settings), af_of_team, {code: af for af, code in LEAGUES.items()}


def weather_reader():
    """Pioggia e vento previsti nelle due ore di gioco allo stadio della squadra di casa; (None, None) se non si sa."""
    from app.adapters.cache import FileCache
    from app.adapters.open_meteo import OpenMeteoAdapter
    from app.config import get_settings
    from app.forecast.weather import raw_weather

    adapter = OpenMeteoAdapter(FileCache(get_settings().data_cache_dir, "open-meteo"))

    def read(m: Match) -> tuple[float | None, float | None]:
        team = m.home_team
        if team.latitude is None or team.longitude is None:
            return None, None
        kickoff = m.kickoff_at if m.kickoff_at.tzinfo else m.kickoff_at.replace(tzinfo=UTC)
        try:
            raw = raw_weather(adapter.forecast_hourly(team.latitude, team.longitude, kickoff.date()), kickoff)
        except Exception:  # servizio non raggiungibile: lo studio va avanti senza meteo
            return None, None
        return (raw[0], raw[1]) if raw else (None, None)

    return read


def refresh_studies(db: Session, now: datetime, log=print) -> int:
    """Studia tutte le partite dei prossimi giorni (coppe europee escluse: squadre di paesi diversi)."""
    upcoming = list(db.scalars(
        select(Match).join(Competition, Competition.id == Match.competition_id)
        .where(Match.status == MatchStatus.SCHEDULED, Match.kickoff_at > now, Match.kickoff_at <= now + timedelta(days=STUDY_DAYS),
               Competition.country != CUP_COUNTRY)
    ))  # fmt: skip
    by_country: dict[str, list[Match]] = defaultdict(list)
    for m in upcoming:
        by_country[m.competition.country].append(m)
    books = load_book_odds(db, [m.id for m in upcoming], closing=False)
    insights: dict[int, MatchInsight] = {}
    for ins in db.scalars(select(MatchInsight).where(MatchInsight.match_id.in_([m.id for m in upcoming])).order_by(MatchInsight.created_at)):
        insights[ins.match_id] = ins  # resta l'ultimo giudizio sulle notizie
    weather = weather_reader()
    adapter, af_of_team, af_league_of = _api_football(db)
    done = 0
    for country, matches in by_country.items():
        country_games = load_games(db, country)
        fits: dict[int, DixonColesFit | None] = {}
        xg_fits: dict[int, DixonColesFit | None] = {}
        history: dict[tuple[int, str], list[Match]] = {}
        for m in matches:
            if m.competition_id not in fits:  # un modello per campionato (D140)
                fits[m.competition_id] = league_fit([g for g in country_games if g.competition_id == m.competition_id], now)
                af_league = af_league_of.get(m.competition.code)
                xg_fits[m.competition_id] = xg_fit(adapter, af_league, int(m.season[:4]), now) if adapter is not None and af_league else None
            fit = fits[m.competition_id]
            if fit is None:
                continue
            fx = xg_fits[m.competition_id]
            ah, aa = af_of_team.get(m.home_team_id), af_of_team.get(m.away_team_id)
            xg = fx.expected_goals(ah, aa) if fx is not None and ah is not None and aa is not None and fx.has_team(ah) and fx.has_team(aa) else None
            key = (m.competition_id, m.season)
            if key not in history:
                history[key] = _finished(db, m.competition_id, (m.season, season_before(m.season)), now)
            spots = table(history[key], m.season)
            home, away = m.home_team.name, m.away_team.name
            adj = motivation_adjustment(spots.get(m.home_team_id), spots.get(m.away_team_id), home, away)
            if (ins := insights.get(m.id)) is not None:
                adj = news_adjustment(ins.side, ins.strength, ins.reason, home, away).then(adj)
            if m.kickoff_at.replace(tzinfo=m.kickoff_at.tzinfo or UTC) <= now + timedelta(days=WEATHER_DAYS):
                adj = adj.then(weather_adjustment(*weather(m)))
            insight = insights.get(m.id)
            caution = {"home": caution_for(db, m, m.home_team_id, home, insight, "home"), "away": caution_for(db, m, m.away_team_id, away, insight, "away")}
            data = study_match(m, fit, history[key], books.get(m.id, {}), adj, xg, caution)
            if data is None:
                continue
            row = db.get(MatchStudy, m.id) or MatchStudy(match_id=m.id)
            row.computed_at, row.data = now, data
            db.add(row)
            done += 1
        db.commit()
        log(f"studio {country}: {len(matches)} partite")
    return done


def load_studies(db: Session, start: datetime, end: datetime, competitions: Sequence[str] | None = None) -> list[tuple[Match, dict]]:
    query = (
        select(Match, MatchStudy).join(MatchStudy, MatchStudy.match_id == Match.id).join(Competition, Competition.id == Match.competition_id)
        .where(Match.status == MatchStatus.SCHEDULED, Match.kickoff_at > start, Match.kickoff_at <= end)
        .order_by(Match.kickoff_at)
    )  # fmt: skip
    if competitions:
        query = query.where(or_(*(Competition.code == c for c in competitions)))
    return [(m, s.data) for m, s in db.execute(query).all()]
