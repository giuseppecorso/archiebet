"""Studio delle partite in programma (D137): dati dal database, modello per paese, salvataggio in `match_studies`."""

from collections import defaultdict
from collections.abc import Iterable, Sequence
from datetime import UTC, datetime, timedelta

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.forecast.data import MODEL_COUNTRY, load_games
from app.forecast.dixon_coles import DixonColesFit
from app.forecast.elo import EloTimeline, run_elo
from app.forecast.model import ModelConfig, fit_at
from app.forecast.radar_service import load_book_odds
from app.forecast.study import (
    MIN_SAMPLE,
    Adjustment,
    Played,
    TableSpot,
    first_half_share,
    model_probabilities,
    motivation_adjustment,
    news_adjustment,
    study_picks,
    weather_adjustment,
)
from app.ingest.teams import CUP_COUNTRY
from app.models import Competition, Match, MatchInsight, MatchStatus, MatchStudy

STUDY_DAYS = 8  # partite dei prossimi giorni
WEATHER_DAYS = 3  # meteo previsto solo per le partite dei prossimi 3 giorni
SAMPLE = 10  # ultime partite in casa (o in trasferta) guardate per i fatti
PLAYABLE = ("sisal", "eurobet")


def season_before(season: str) -> str:
    """"2026/27" → "2025/26"."""
    start = int(season[:4]) - 1
    return f"{start}/{str(start + 1)[-2:]}"


def country_fit(db: Session, country: str, now: datetime, upcoming: Sequence[Match]) -> DixonColesFit | None:
    """Gol attesi del paese. In Italia il modello di Archie con l'Elo (D50-D51), altrove Dixon-Coles con pesi nel tempo."""
    games = load_games(db, country)
    if not games:
        return None
    kickoffs = [g.kickoff_at for g in games]
    if country != MODEL_COUNTRY:
        return fit_at(games, kickoffs, now, ModelConfig(elo_prior=False))
    config = ModelConfig()
    timeline = EloTimeline(games, run_elo(games, config.elo))
    tier_of = {t: m.competition.tier for m in upcoming for t in (m.home_team_id, m.away_team_id)}

    def rating(team: int) -> float:
        r = timeline.rating_at(team, now)
        return r if r is not None else config.elo.tier_base[tier_of[team]] - config.elo.newcomer_penalty

    return fit_at(games, kickoffs, now, config, extra_teams=tier_of, rating_at=rating)


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


def study_match(m: Match, fit: DixonColesFit, games: Sequence[Match], book: dict, adjustment: Adjustment = Adjustment()) -> dict | None:
    """Lo studio completo di una partita, pronto da salvare (None se mancano i dati)."""
    if not (fit.has_team(m.home_team_id) and fit.has_team(m.away_team_id)):
        return None
    lam, mu = fit.expected_goals(m.home_team_id, m.away_team_id)
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
    picks = []
    for p in study_picks(probs, home_games, away_games, home, away):
        prices = {bm: price for bm in PLAYABLE if (price := book.get(bm, {}).get(p.market, {}).get(p.selection))}
        picks.append({
            "market": p.market, "selection": p.selection, "level": p.level, "event": p.event,
            "p_model": round(p.p_model, 4), "p_archie": round(p.p_archie, 4),
            "evidence": [p.evidence.home_hits, p.evidence.home_n, p.evidence.away_hits, p.evidence.away_n],
            "reasons": [*p.reasons, *context], "prices": prices,
        })  # fmt: skip
    return {
        "lam": round(lam, 3), "mu": round(mu, 3), "rho": round(fit.rho, 4),
        "share_home": round(share_home, 3), "share_away": round(share_away, 3),
        "form_home": form_home, "form_away": form_away, "notes": list(adjustment.reasons), "picks": picks,
    }  # fmt: skip


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
    done = 0
    for country, matches in by_country.items():
        fit = country_fit(db, country, now, matches)
        if fit is None:
            continue
        history: dict[tuple[int, str], list[Match]] = {}
        for m in matches:
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
            data = study_match(m, fit, history[key], books.get(m.id, {}), adj)
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
