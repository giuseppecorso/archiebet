"""Quote e calendario di OddsPapi nel database.

- Calendario (D71): le partite di A, B e top 5 che non abbiamo ancora vengono create da OddsPapi (fino a ~10 giorni
  prima); football-data, quando arriva, aggiorna le stesse partite (stesso campionato, stagione e squadre).

- Elenco delle partite in programma: una volta al giorno (2 richieste: massimo 5 campionati per richiesta).
- Partite dei prossimi 7 giorni: quote attuali di Pinnacle e dei bookmaker dell'utente (Sisal, Eurobet)
  dallo storico gratuito (1 chiamata per partita fino a 3 bookmaker, 5,5 secondi), salvate come "non di chiusura".
- Partite iniziate da almeno 2 ore: quota di chiusura di Pinnacle = ultimo prezzo prima del calcio d'inizio,
  il riferimento per il CLV (D48).
"""

from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy import delete, insert, select
from sqlalchemy.orm import Session

from app.adapters.football_data import season_label, season_of
from app.adapters.oddspapi import ITALIAN, SHARP, SOURCE, TOURNAMENTS, OddsPapiAdapter, OPFixture, Prices, prices_at
from app.ingest.teams import CUP_COUNTRY, normalize_team_name
from app.models import Competition, Match, MatchOdds, MatchSource, MatchStatus, Team, TeamAlias

ROME = ZoneInfo("Europe/Rome")
LINK_WINDOW = timedelta(hours=48)  # stessa partita se il calcio d'inizio differisce al massimo di tanto
HORIZON = timedelta(days=7)  # quote attuali solo per le partite dei prossimi giorni
UPCOMING_MAX_AGE = timedelta(hours=23)  # elenco partite una volta al giorno: ~62 richieste al mese
HISTORY_MAX_AGE = timedelta(hours=5)  # "Aggiorna ora" subito dopo un giro automatico non riscarica
NEAR = timedelta(days=3)  # le quote si muovono soprattutto negli ultimi giorni: oltre, basta una volta al giorno
FAR_HISTORY_MAX_AGE = timedelta(hours=23)


def history_max_age(kickoff: datetime, now: datetime) -> timedelta:
    """Ogni quanto riscaricare le quote di una partita: a ogni giro se è vicina, una volta al giorno se è lontana."""
    return HISTORY_MAX_AGE if kickoff - now <= NEAR else FAR_HISTORY_MAX_AGE
DEFAULT_BOOKMAKERS = ("sisal", "eurobet")  # D66


def current_slugs(bookmakers: Sequence[str]) -> list[str]:
    """Slug OddsPapi da chiedere allo storico: Pinnacle (riferimento) + i bookmaker dove si gioca."""
    slug_of = {name: slug for slug, name in ITALIAN.items()}
    return list(SHARP) + [slug_of[b] for b in bookmakers if b in slug_of]
CLOSING_DELAY = timedelta(hours=2)  # la chiusura si chiede a partita iniziata da un po'
CLOSING_LOOKBACK = timedelta(days=14)  # oltre, se manca la chiusura, si rinuncia
CLOSING_SLUGS = ["pinnacle"]


@dataclass
class OddsPapiReport:
    linked: int = 0  # partite collegate in questo giro
    created: int = 0  # partite messe in calendario da OddsPapi (D71)
    not_in_calendar: int = 0  # partite di OddsPapi che non si possono aggiungere (già iniziate)
    unknown_teams: list[str] = field(default_factory=list)
    current: int = 0  # partite con quote attuali aggiornate
    closing: int = 0  # partite con chiusura salvata


def _team_index(db: Session) -> tuple[dict[str, int], dict[tuple[str, str], int]]:
    """(id OddsPapi → squadra, (paese, nome ripulito) → squadra) con i nomi di tutte le fonti."""
    by_alias = {a.alias: a.team_id for a in db.scalars(select(TeamAlias).where(TeamAlias.source == SOURCE))}
    by_name: dict[tuple[str, str], int] = {}
    for team in db.scalars(select(Team)):
        by_name.setdefault((team.country, normalize_team_name(team.name)), team.id)
    for alias, country, team_id in db.execute(select(TeamAlias.alias, Team.country, Team.id).join(Team, TeamAlias.team_id == Team.id)):
        by_name.setdefault((country, normalize_team_name(alias)), team_id)
    return by_alias, by_name


CUP_WINDOW = timedelta(hours=3)  # coppe: la partita del nostro calendario alla stessa ora


def similar_names(a: str, b: str) -> bool:
    """Stessa squadra con nomi diversi? "Ajax Amsterdam" ~ "Ajax", "SL Benfica" ~ "Benfica", "GNK Dinamo Zagreb" ~ "Dinamo Zagreb"."""
    na, nb = normalize_team_name(a), normalize_team_name(b)
    if not na or not nb:
        return False
    if na == nb or na in nb or nb in na:
        return True
    return bool({w for w in na.split() if len(w) >= 4} & {w for w in nb.split() if len(w) >= 4})


def loosely_similar(a: str, b: str) -> bool:
    """Somiglianza debole, solo come conferma: stesse prime 4 lettere ("Lillestroem" ~ "Lillestrom")
    oppure sigla ("Kuopion Palloseura" ~ "KuPS": le iniziali compaiono in ordine nella sigla)."""
    na, nb = normalize_team_name(a), normalize_team_name(b)
    if not na or not nb:
        return False
    if na.replace(" ", "")[:4] == nb.replace(" ", "")[:4]:
        return True
    for long, short in ((na, nb), (nb, na)):
        letters = "".join(w[0] for w in long.split())
        if len(letters) >= 2 and " " not in short and _in_order(letters, short):
            return True
    return False


def _in_order(letters: str, word: str) -> bool:
    it = iter(word)
    return all(ch in it for ch in letters)


def _cup_match(db: Session, fx: OPFixture, names: dict[str, str], competition_id: int, by_alias: dict[str, int]) -> Match | None:
    """Partita di coppa del nostro calendario (messa da API-Football) che corrisponde a quella di OddsPapi.

    Si cercano le partite della stessa coppa alla stessa ora; per ogni lato basta il codice OddsPapi già noto o un nome
    simile. Vale solo se la candidata è una sola.
    """
    candidates = db.scalars(
        select(Match).where(
            Match.competition_id == competition_id,
            Match.kickoff_at.between(fx.start_time - CUP_WINDOW, fx.start_time + CUP_WINDOW),
        )
    ).all()

    def side_ok(pid: int, team: Team) -> bool:
        known = by_alias.get(str(pid))
        return known == team.id if known is not None else similar_names(names.get(str(pid), ""), team.name)

    found = [m for m in candidates if side_ok(fx.home_id, m.home_team) and side_ok(fx.away_id, m.away_team)]
    if not found:
        # Un solo lato riconosciuto (es. "Kuopion Palloseura" contro "KuPS"): basta se all'ora esatta la partita è una sola
        def loose(pid: int, team: Team) -> bool:
            return side_ok(pid, team) or loosely_similar(names.get(str(pid), ""), team.name)

        found = [m for m in candidates if abs(m.kickoff_at - fx.start_time) <= timedelta(minutes=15)
                 and ((side_ok(fx.home_id, m.home_team) and loose(fx.away_id, m.away_team))
                      or (side_ok(fx.away_id, m.away_team) and loose(fx.home_id, m.home_team)))]
    return found[0] if len(found) == 1 else None


def link_fixtures(
    db: Session, fixtures: Iterable[OPFixture], names: dict[str, str], report: OddsPapiReport, now: datetime
) -> dict[str, Match]:
    """Collega le partite di OddsPapi alle nostre (stesso campionato, stesse squadre, data vicina).

    Se la partita non c'è e deve ancora giocarsi, la mette in calendario (D71). Squadre sconosciute: mai create,
    per non duplicare l'anagrafica (si aggiunge la regola del nome in teams.py).
    """
    competitions = {c.code: c for c in db.scalars(select(Competition))}
    links = {s.external_id: s.match_id for s in db.scalars(select(MatchSource).where(MatchSource.source == SOURCE))}
    linked_matches = set(links.values())
    by_alias, by_name = _team_index(db)
    out: dict[str, Match] = {}
    for fx in fixtures:
        if fx.tournament_id not in TOURNAMENTS:
            continue
        if fx.id in links:
            match = db.get(Match, links[fx.id])
            if match.status == MatchStatus.SCHEDULED and match.kickoff_at > now and fx.start_time > now:
                match.kickoff_at = fx.start_time  # orario aggiornato (anticipi e posticipi)
            out[fx.id] = match
            continue
        competition = competitions.get(TOURNAMENTS[fx.tournament_id])
        if competition is None:
            continue
        is_cup = competition.country == CUP_COUNTRY
        if is_cup:
            cup_match = _cup_match(db, fx, names, competition.id, by_alias)
            if cup_match is None:
                report.unknown_teams += [names.get(str(p), f"id {p}") for p in (fx.home_id, fx.away_id) if str(p) not in by_alias]
                continue
        teams = []
        for pid in (fx.home_id, fx.away_id):
            name = names.get(str(pid), "")
            team = by_alias.get(str(pid))
            if is_cup:
                team = cup_match.home_team_id if pid == fx.home_id else cup_match.away_team_id
            elif team is None and name:
                team = by_name.get((competition.country, normalize_team_name(name)))
            if team is None:
                report.unknown_teams.append(name or f"id {pid}")
            teams.append(team)
        if None in teams:
            continue
        match = cup_match if is_cup else db.scalar(
            select(Match).where(
                Match.competition_id == competition.id,
                Match.home_team_id == teams[0],
                Match.away_team_id == teams[1],
                Match.kickoff_at.between(fx.start_time - LINK_WINDOW, fx.start_time + LINK_WINDOW),
            )
        )
        season = season_label(season_of(fx.start_time.astimezone(ROME).date()))
        if match is None and not is_cup:
            # Stessa accoppiata nella stessa stagione con data lontana (rinvio): è la stessa partita
            match = db.scalar(
                select(Match).where(
                    Match.competition_id == competition.id,
                    Match.season == season,
                    Match.home_team_id == teams[0],
                    Match.away_team_id == teams[1],
                )
            )
        if match is None:
            if is_cup:  # il calendario delle coppe lo dà API-Football (la stessa sfida può tornare in stagione)
                continue
            if fx.start_time <= now:
                report.not_in_calendar += 1
                continue
            match = Match(
                competition_id=competition.id,
                season=season,
                kickoff_at=fx.start_time,
                kickoff_has_time=True,
                status=MatchStatus.SCHEDULED,
                home_team_id=teams[0],
                away_team_id=teams[1],
            )
            db.add(match)
            db.flush()
            report.created += 1
        if match.id in linked_matches:
            # Stessa partita con un altro codice OddsPapi (capita dopo i rinvii): si usano le sue quote, il collegamento resta il primo
            out[fx.id] = match
            continue
        db.add(MatchSource(match_id=match.id, source=SOURCE, external_id=fx.id))
        for pid, team in zip((fx.home_id, fx.away_id), teams):
            if str(pid) not in by_alias:
                db.add(TeamAlias(team_id=team, source=SOURCE, alias=str(pid)))
                by_alias[str(pid)] = team
        links[fx.id] = match.id
        linked_matches.add(match.id)
        out[fx.id] = match
        report.linked += 1
    db.flush()
    return out


def replace_odds(db: Session, match_id: int, prices: Prices, closing: bool) -> int:
    """Sostituisce le quote OddsPapi della partita (attuali o di chiusura). Restituisce quante ne ha scritte."""
    db.execute(delete(MatchOdds).where(MatchOdds.match_id == match_id, MatchOdds.source == SOURCE, MatchOdds.is_closing.is_(closing)))
    rows = [
        {"match_id": match_id, "source": SOURCE, "bookmaker": bookmaker, "market": market, "selection": selection,
         "price": Decimal(str(price)), "is_closing": closing}
        for bookmaker, markets in prices.items()
        for market, selections in markets.items()
        for selection, price in selections.items()
        if price > 1
    ]  # fmt: skip
    if rows:
        db.execute(insert(MatchOdds), rows)
    return len(rows)


def sync_oddspapi(
    db: Session,
    adapter: OddsPapiAdapter,
    now: datetime,
    log: Callable[[str], None] = print,
    bookmakers: Sequence[str] = DEFAULT_BOOKMAKERS,
) -> OddsPapiReport:
    report = OddsPapiReport()
    adapter.markets()  # definizioni dei mercati (angoli e cartellini, D94): dalla cache, una richiesta ogni 3 mesi
    slugs = current_slugs(bookmakers)
    fixtures, current = adapter.upcoming(UPCOMING_MAX_AGE)
    names = adapter.participants()
    if any(str(p) not in names for fx in fixtures for p in (fx.home_id, fx.away_id)):
        names = adapter.participants(max_age=timedelta(0))  # squadra nuova: rinfresco i nomi
    links = link_fixtures(db, fixtures, names, report, now)
    db.commit()

    # Quote attuali delle partite in programma
    for fixture_id, match in links.items():
        if match.status != MatchStatus.SCHEDULED or not (now < match.kickoff_at <= now + HORIZON):
            continue
        prices = prices_at(adapter.history(fixture_id, slugs, history_max_age(match.kickoff_at, now)), now)
        for bookmaker, markets in current.get(fixture_id, {}).items():  # elenco del giorno: solo se lo storico non li ha
            for market, selections in markets.items():
                prices.setdefault(bookmaker, {}).setdefault(market, selections)
        if replace_odds(db, match.id, prices, closing=False):
            report.current += 1
        db.commit()

    # Chiusura di Pinnacle per le partite iniziate
    with_closing = select(MatchOdds.match_id).where(MatchOdds.source == SOURCE, MatchOdds.is_closing.is_(True))
    pending = db.execute(
        select(MatchSource.external_id, Match)
        .join(Match, MatchSource.match_id == Match.id)
        .where(
            MatchSource.source == SOURCE,
            Match.kickoff_at < now - CLOSING_DELAY,
            Match.kickoff_at > now - CLOSING_LOOKBACK,
            Match.status != MatchStatus.CANCELLED,
            Match.id.not_in(with_closing),
        )
    ).all()
    for fixture_id, match in pending:
        prices = prices_at(adapter.history(fixture_id, CLOSING_SLUGS, timedelta(days=365)), match.kickoff_at)
        if replace_odds(db, match.id, prices, closing=True):
            report.closing += 1
        db.commit()

    if report.unknown_teams:
        log(f"OddsPapi: squadre non riconosciute {sorted(set(report.unknown_teams))}")
    return report
