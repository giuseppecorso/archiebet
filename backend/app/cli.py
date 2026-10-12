"""Comandi da terminale. Uso: python -m app.cli create-user <nome> | set-password <nome> | sync | backtest | open-vault"""

import argparse
import getpass
import sys
from datetime import UTC, datetime

from app.adapters.cache import FileCache
from app.adapters.football_data import FIRST_SEASON, FootballDataAdapter
from app.auth.service import create_user, set_password
from app.config import get_settings
from app.db import SessionLocal
from app.forecast.backtest import ModelConfig, Scores, score, score_by, walk_forward
from app.forecast.data import load_games, load_reference_closing_1x2
from app.forecast.vault import VAULT_FIRST_SEASON, open_vault, vault_is_open
from app.ingest.api_football import sync_api_football
from app.ingest.football_data import sync_football_data
from app.ingest.teams import tidy_teams
from app.jobs import api_football_adapter
from app.models.football import Competition
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


def _print_scores(label: str, s: Scores) -> None:
    market = ""
    if s.n_market:
        market = f"  | su {s.n_market} con mercato: modello {s.model_log_loss_on_market:.4f} vs mercato {s.market_log_loss:.4f}"
    print(f"{label:<22} {s.n:>6}  log loss {s.log_loss:.4f}  Brier {s.brier:.4f}  RPS {s.rps:.4f}  calibr. {s.ece:.3f}{market}")


def _backtest(first: str, last: str, config: ModelConfig) -> int:
    with SessionLocal() as db:
        games = load_games(db)
        market = load_reference_closing_1x2(db)
        names = {c.id: c.name for c in db.query(Competition).all()}
    seasons = sorted({g.season for g in games if first <= g.season <= last})
    print(f"Backtest {seasons[0]} - {seasons[-1]} con {config}")
    res = walk_forward(games, seasons, config, progress=lambda i, n: print(f"\r  {i}/{n} partite", end="", flush=True))
    print(f"\n{res.fits} stime del modello, {len(res.predictions)} previsioni, {res.skipped} saltate (squadra senza storia)")
    _print_scores("TOTALE", score(res.predictions, market))
    for comp, s in score_by(res.predictions, market, lambda p: p.competition_id).items():
        _print_scores(names[comp], s)
    for season, s in score_by(res.predictions, market, lambda p: p.season).items():
        _print_scores(season, s)
    return 0


def _open_vault() -> int:
    if vault_is_open():
        print("La cassaforte è già aperta.")
        return 0
    print(f"Aprire la cassaforte rende valutabili le stagioni dal {VAULT_FIRST_SEASON} in poi. Si fa UNA volta, per il verdetto.")
    if input('Scrivi "apri cassaforte" per confermare: ').strip().lower() != "apri cassaforte":
        print("Annullato.")
        return 1
    open_vault(datetime.now(UTC))
    print("Cassaforte aperta.")
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
    bt = commands.add_parser("backtest", help="backtest walk-forward del modello (stagioni fuori dalla cassaforte)")
    bt.add_argument("--from", dest="first", default="2012/13", help='prima stagione valutata, es. "2012/13"')
    bt.add_argument("--to", dest="last", default="2024/25", help="ultima stagione valutata")
    bt.add_argument("--xi", type=float, default=ModelConfig.xi_per_day, help="peso nel tempo (per giorno)")
    bt.add_argument("--ridge", type=float, default=ModelConfig.ridge, help="spinta verso la media (partite equivalenti)")
    bt.add_argument("--window", type=int, default=ModelConfig.window_days, help="giorni di storia usati")
    bt.add_argument("--no-elo", dest="elo", action="store_false", help="senza Elo come punto di partenza delle squadre")
    commands.add_parser("open-vault", help="apre la cassaforte 2025/26 per il verdetto (irreversibile)")
    args = parser.parse_args()
    if args.command == "create-user":
        return _create_user(args.username, args.admin)
    if args.command == "set-password":
        return _set_password(args.username)
    if args.command == "tidy-teams":
        with SessionLocal() as db:
            print(f"Modifiche: {tidy_teams(db)}")
        return 0
    if args.command == "backtest":
        return _backtest(args.first, args.last, ModelConfig(xi_per_day=args.xi, ridge=args.ridge, window_days=args.window, elo_prior=args.elo))
    if args.command == "open-vault":
        return _open_vault()
    if args.command == "sync":
        return _sync(args.source, args.first_season)
    return 1


if __name__ == "__main__":
    sys.exit(main())
