"""Comandi da terminale. Uso: python -m app.cli create-user <nome> | set-password <nome> | sync"""

import argparse
import getpass
import sys

from app.adapters.cache import FileCache
from app.adapters.football_data import FIRST_SEASON, FootballDataAdapter
from app.auth.service import create_user, set_password
from app.config import get_settings
from app.db import SessionLocal
from app.ingest.api_football import sync_api_football
from app.ingest.football_data import sync_football_data
from app.ingest.teams import tidy_teams
from app.jobs import api_football_adapter
from app.usage import record_usage


def _ask_password() -> str | None:
    password = getpass.getpass("Password (non viene mostrata mentre scrivi): ")
    if password != getpass.getpass("Ripeti la password: "):
        print("Le due password non coincidono. Nessuna modifica: riprova.", file=sys.stderr)
        return None
    return password


def _create_user(username: str, admin: bool) -> int:
    if (password := _ask_password()) is None:
        return 1
    try:
        with SessionLocal() as db:
            user = create_user(db, username, password, is_admin=admin)
    except ValueError as error:
        print(error, file=sys.stderr)
        return 1
    print(f"Utente '{user.username}' creato.")
    return 0


def _set_password(username: str) -> int:
    if (password := _ask_password()) is None:
        return 1
    try:
        with SessionLocal() as db:
            user = set_password(db, username, password)
    except ValueError as error:
        print(error, file=sys.stderr)
        return 1
    print(f"Password di '{user.username}' cambiata. Rifai il login nel browser.")
    return 0


def _sync(source: str, first_season: int) -> int:
    settings = get_settings()
    with SessionLocal() as db:
        if source in ("all", "football-data"):
            adapter = FootballDataAdapter(
                FileCache(settings.data_cache_dir, "football-data"),
                on_call=lambda name: record_usage(db, name),
            )
            report = sync_football_data(db, adapter, first_season=first_season)
            print(f"football-data: {report.created} partite nuove, {report.updated} aggiornate, {report.odds} quote.")
        if source in ("all", "api-football"):
            if not settings.api_football_key:
                print("API-Football: manca API_FOOTBALL_KEY in backend/.env, salto.")
            else:
                report = sync_api_football(
                    db, api_football_adapter(db, settings), settings.api_football_league_ids, settings.api_football_season_years
                )
                print(f"API-Football: {report.created} partite nuove, {report.updated} aggiornate.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    commands = parser.add_subparsers(dest="command", required=True)
    create = commands.add_parser("create-user", help="crea un utente")
    create.add_argument("username")
    create.add_argument("--admin", action="store_true", help="può vedere la pagina di amministrazione")
    reset = commands.add_parser("set-password", help="cambia la password di un utente esistente")
    reset.add_argument("username")
    sync = commands.add_parser("sync", help="scarica e aggiorna partite e quote")
    sync.add_argument("--source", choices=["all", "football-data", "api-football"], default="all")
    sync.add_argument("--from", dest="first_season", type=int, default=FIRST_SEASON, help="prima stagione (anno di inizio)")
    commands.add_parser("tidy-teams", help="applica le regole di nomi e unioni alle squadre già salvate")
    args = parser.parse_args()
    if args.command == "create-user":
        return _create_user(args.username, args.admin)
    if args.command == "set-password":
        return _set_password(args.username)
    if args.command == "tidy-teams":
        with SessionLocal() as db:
            print(f"Modifiche: {tidy_teams(db)}")
        return 0
    if args.command == "sync":
        return _sync(args.source, args.first_season)
    return 1


if __name__ == "__main__":
    sys.exit(main())
