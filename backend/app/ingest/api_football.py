"""Importa le partite di API-Football nel database (calendario, risultati, stadi, giornate)."""

from collections.abc import Iterable
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.adapters.api_football import LEAGUES, SOURCE, AFFixture, ApiFootballAdapter, ApiFootballError, QuotaExhausted
from app.adapters.football_data import season_label, season_of
from app.ingest.football_data import ImportReport
from app.ingest.teams import TeamResolver, ensure_competitions
from app.models import Match, MatchSource


def import_fixtures(db: Session, fixtures: Iterable[AFFixture]) -> ImportReport:
    competitions = ensure_competitions(db)
    teams = TeamResolver(db, SOURCE)
    report = ImportReport()
    sources = {s.external_id: s for s in db.scalars(select(MatchSource).where(MatchSource.source == SOURCE))}

    for fx in fixtures:
        if fx.league_id not in LEAGUES:
            continue
        competition = competitions[LEAGUES[fx.league_id]]
        season = season_label(fx.season)
        home = teams.resolve(str(fx.home.id), fx.home.name)
        away = teams.resolve(str(fx.away.id), fx.away.name)

        link = sources.get(str(fx.id))
        match = db.get(Match, link.match_id) if link else None
        if match is None:
            match = db.scalar(
                select(Match).where(
                    Match.competition_id == competition.id,
                    Match.season == season,
                    Match.home_team_id == home.id,
                    Match.away_team_id == away.id,
                )
            )
        if match is None:
            match = Match(competition_id=competition.id, season=season, home_team_id=home.id, away_team_id=away.id)
            db.add(match)
            report.created += 1
        else:
            report.updated += 1

        match.kickoff_at = fx.kickoff_at
        match.kickoff_has_time = True
        match.status = fx.status
        match.matchday = fx.matchday
        match.venue_name = fx.venue_name
        match.venue_city = fx.venue_city
        match.referee = fx.referee or match.referee
        match.home_goals, match.away_goals = fx.home_goals, fx.away_goals
        match.ht_home_goals, match.ht_away_goals = fx.ht_home_goals, fx.ht_away_goals

        if link is None:
            db.flush()
            link = MatchSource(match_id=match.id, source=SOURCE, external_id=str(fx.id))
            db.add(link)
            sources[str(fx.id)] = link

    db.commit()
    return report


def sync_api_football(
    db: Session,
    adapter: ApiFootballAdapter,
    leagues: Iterable[int],
    seasons: Iterable[int],
    now: datetime | None = None,
    log=print,
) -> ImportReport:
    """Scarica (o legge dalla cache) le partite dei campionati e delle stagioni richieste.

    Stagioni concluse: cache per sempre. Stagione in corso: 6 ore (servirà il piano a pagamento).
    Si ferma con un messaggio se il piano non copre una stagione o se le richieste del giorno finiscono.
    """
    current = season_of((now or datetime.now(UTC)).date())
    total = ImportReport()
    for season in seasons:
        for league in leagues:
            max_age = timedelta(hours=6) if season >= current else timedelta(days=36500)
            try:
                report = import_fixtures(db, adapter.fixtures(league, season, max_age))
            except QuotaExhausted as error:
                log(f"Mi fermo: {error}. Riprendo al prossimo giro, il resto è già in cache.")
                return total
            except ApiFootballError as error:
                log(f"{LEAGUES.get(league, league)} {season_label(season)}: saltato ({error})")
                continue
            log(f"{LEAGUES.get(league, league)} {season_label(season)}: {report.created} nuove, {report.updated} aggiornate")
            total.add(report)
    if adapter.remaining_today is not None:
        log(f"Richieste API-Football rimaste oggi: {adapter.remaining_today}")
    return total
