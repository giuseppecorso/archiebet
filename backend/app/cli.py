"""Comandi da terminale. Uso: python -m app.cli create-user <nome> | set-password <nome> | sync | predict | backtest | open-vault"""

import argparse
import getpass
import sys
from datetime import UTC, datetime

from app.adapters.cache import FileCache
from app.adapters.football_data import FIRST_SEASON, FootballDataAdapter
from app.auth.service import create_user, set_password
from app.config import get_settings
from app.db import SessionLocal
from app.forecast import factor_test
from app.forecast.backtest import Scores, score, score_by, walk_forward
from app.forecast.clv import SUSPICIOUS_VALUE, summarize, value_bets
from app.forecast.data import REFERENCE_BOOKMAKERS, fair_odds_probabilities, load_games, load_odds, reference_1x2
from app.forecast.factors import nothing_to_play_for, rest_difference
from app.forecast.model import ModelConfig
from app.forecast.service import refresh_predictions
from app.forecast.vault import VAULT_FIRST_SEASON, open_vault, vault_is_open
from app.forecast.verdict import compute as compute_verdict
from app.forecast.verdict import sharp_opening
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
        closing_fair = fair_odds_probabilities(load_odds(db, REFERENCE_BOOKMAKERS, closing=True))
        offered = load_odds(db, ["bet365"], closing=False)
        market = reference_1x2(closing_fair)
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
    print("\nGiocate di valore (quota bet365 di apertura) e CLV contro la chiusura Pinnacle/Betfair:")
    bets = value_bets(res.predictions, offered, closing_fair, threshold=0.05)
    groups = [("valore 5-15%", [b for b in bets if b.value < SUSPICIOUS_VALUE]), ("valore >15% (sospetto)", [b for b in bets if b.value >= SUSPICIOUS_VALUE])]
    groups += [(f"{names[c]}", [b for b in bets if b.competition_id == c]) for c in sorted({b.competition_id for b in bets})]
    groups += [(m, [b for b in bets if b.market == m]) for m in ("1X2", "OU2.5")]
    for label, group in [("TUTTE", bets), *groups]:
        if s := summarize(group):
            print(f"{label:<24} {s.n:>5} giocate  CLV medio {s.mean_clv:+.2%} ± {s.clv_std_error:.2%}  CLV>0 nel {s.share_positive:.0%}  (ROI {s.roi:+.1%})")
    return 0


def _factor_test(first: str, last: str) -> int:
    with SessionLocal() as db:
        games = load_games(db)
        closing_fair = fair_odds_probabilities(load_odds(db, REFERENCE_BOOKMAKERS, closing=True))
        opening_fair = fair_odds_probabilities(load_odds(db, ["pinnacle"], closing=False))
        offered_pinnacle = load_odds(db, ["pinnacle"], closing=False)
        offered_bet365 = load_odds(db, ["bet365"], closing=False)
    rows = factor_test.market_rows(games, opening_fair, closing_fair)
    seasons = sorted({r.season for r in rows if first <= r.season <= last})
    print(f"Prova del nove contro il mercato: {len(rows)} partite di A e B con apertura Pinnacle, valutate {seasons[0]} - {seasons[-1]}")
    print("Calcolo le previsioni del modello di Archie (walk-forward)...")
    model = walk_forward(games, sorted({r.season for r in rows if r.season <= last}), ModelConfig()).predictions
    factors = {
        "+ riposo (giorni, casa - fuori)": factor_test.as_features(rest_difference(games)),
        "+ motivazione (salve e senza obiettivo)": factor_test.as_features(nothing_to_play_for(games)),
        "+ modello di Archie (Dixon-Coles + Elo)": factor_test.model_disagreement(rows, model),
    }
    results = factor_test.run(rows, factors, seasons, offered_pinnacle, offered_bet365, closing_fair)
    for r in results:
        cmp = "" if r.vs_baseline is None else f"  vs ricalibrato {r.vs_baseline.mean_diff:+.4f} ± {r.vs_baseline.std_error:.4f} {'PASSA' if r.passes else 'non passa'}"
        clv = "  ".join(
            f"CLV {label}: {c.mean:+.2%} ± {c.std_error:.2%} su {c.n}" if c else f"CLV {label}: nessuna giocata"
            for label, c in (("Pinnacle", r.clv_pinnacle), ("bet365", r.clv_bet365))
        )
        print(f"{r.name:<42} n={r.n:<5} log loss {r.log_loss:.4f}{cmp}\n{'':<42} {clv}")
    return 0


def _verdict() -> int:
    if not vault_is_open():
        print("La cassaforte è chiusa: il verdetto si calcola dopo  python -m app.cli open-vault")
        return 1
    with SessionLocal() as db:
        games = load_games(db)
        closing_fair = fair_odds_probabilities(load_odds(db, REFERENCE_BOOKMAKERS, closing=True))
        sharp = sharp_opening(
            fair_odds_probabilities(load_odds(db, ["pinnacle"], closing=False)),
            fair_odds_probabilities(load_odds(db, ["betfair_ex"], closing=False)),
        )
        offered_bet365 = load_odds(db, ["bet365"], closing=False)
    v = compute_verdict(games, sharp, offered_bet365, closing_fair)
    ok = lambda passed: "SUPERATO" if passed else "NON superato"  # noqa: E731
    print(f"Verdetto sulla stagione {', '.join(v.seasons)} (criteri D58, fissati prima di aprire la cassaforte)")
    _print_scores("Modello", v.model)
    print(f"1. Calibrazione ≤ 3%: {v.model.ece:.1%} -> {ok(v.model_calibrated)}")
    if v.model.market_log_loss is not None:
        gap = v.model.model_log_loss_on_market - v.model.market_log_loss
        print(f"2. Distanza dal mercato di chiusura ≤ 0,03: {gap:+.4f} -> {ok(v.model_close_to_market)}")
    if v.radar:
        print(f"3. Radar (bet365, valore ≥ 2%): CLV {v.radar.mean:+.2%} ± {v.radar.std_error:.2%} su {v.radar.n} giocate -> {ok(v.radar_passes)}")
    else:
        print("3. Radar: nessuna giocata misurabile -> NON superato")
    return 0


def _demargin_test(last: str) -> int:
    """Prova del nove dei metodi per togliere il margine (D72): log loss sui risultati veri."""
    from app.forecast.demargin import compare_methods
    from app.ingest.teams import COUNTRY_ORDER

    with SessionLocal() as db:
        games = [g for country in COUNTRY_ORDER for g in load_games(db, country) if g.season <= last and g.tier <= 2]
        books = {closing: load_odds(db, ["pinnacle"], closing=closing) for closing in (False, True)}
    for closing, label in ((False, "apertura"), (True, "chiusura")):
        for market in ("1X2", "OU2.5"):
            rows = []
            for g in games:
                prices = books[closing].get(g.match_id, {}).get(market)
                if not prices:
                    continue
                if market == "1X2":
                    outcome = 0 if g.home_goals > g.away_goals else 1 if g.home_goals == g.away_goals else 2
                    rows.append(((prices["1"], prices["X"], prices["2"]), outcome))
                else:
                    rows.append(((prices["over"], prices["under"]), 0 if g.home_goals + g.away_goals >= 3 else 1))
            if not rows:
                continue
            print()
            print(f"Pinnacle {label}, {market}: {len(rows)} partite (6 campionati, fino al {last})")
            for s in compare_methods(rows):
                verdict = "PASSA" if s.passes else ("peggio" if s.diff_vs_proportional > 2 * s.diff_std_error else "pari")
                print(f"  {s.name:<14} log loss {s.log_loss:.5f}  vs proporzionale {s.diff_vs_proportional:+.5f} ± {s.diff_std_error:.5f} {verdict:<6}"
                      f"  quote > 4: previste {s.longshot_predicted:.2%}, uscite {s.longshot_observed:.2%}")
    return 0


def _venues() -> int:
    """Stadi di casa: città e campo da API-Football (piano gratuito, ~40 richieste), coordinate da Open-Meteo."""
    from app.adapters.cache import FileCache
    from app.adapters.open_meteo import OpenMeteoAdapter
    from app.ingest.venues import sync_venues
    from app.jobs import api_football_adapter

    settings = get_settings()
    with SessionLocal() as db:
        sync_venues(db, api_football_adapter(db, settings), OpenMeteoAdapter(FileCache(settings.data_cache_dir, "open-meteo")))
    return 0


def _weather_test(fetch_only: bool, patient: bool) -> int:
    """Meteo (D76) e shock climatico dell'ospite (D78): scarica il meteo grezzo (riprendibile) e prova i fattori."""
    import time as _time

    from app.adapters.cache import FileCache
    from app.adapters.open_meteo import OpenMeteoAdapter
    from app.forecast import factor_test as ft
    from app.forecast import weather_test as wt
    from app.forecast.binary_model import BinaryRow
    from app.forecast.weather import climate_shock, weather_factors
    from app.ingest.teams import COUNTRY_ORDER

    settings = get_settings()
    store = settings.data_cache_dir / "weather" / "raw.json"
    meteo = OpenMeteoAdapter(FileCache(settings.data_cache_dir, "open-meteo"))
    waits = {"n": 0}

    def wait() -> bool:  # con --patient aspetta la fine del limite orario di Open-Meteo, al massimo 8 volte
        if not patient or waits["n"] >= 8:
            return False
        waits["n"] += 1
        print("Pausa di un'ora per il limite di Open-Meteo...", flush=True)
        _time.sleep(3660)
        return True

    with SessionLocal() as db:
        items = wt.targets(db)
        raw = wt.fetch_features(meteo, items, store, wait=wait)
        normals = wt.fetch_normals(meteo, items)
        if len(raw) < len(items):
            print(f"Mancano ancora {len(items) - len(raw)} partite: rilancia il comando più tardi (limiti di Open-Meteo).")
        if fetch_only:
            return 0
        games = [g for c in COUNTRY_ORDER for g in load_games(db, c) if g.tier <= 2 and wt.FIRST <= g.season <= wt.CONFIRMATION]
        opening = load_odds(db, ["pinnacle"], closing=False)
        opening_fair = fair_odds_probabilities(opening)
        closing_fair = fair_odds_probabilities(load_odds(db, REFERENCE_BOOKMAKERS, closing=True))
        offered_bet365 = load_odds(db, ["bet365"], closing=False)
    season_of = {g.match_id: g.season for g in games}
    target_of = {t.match_id: t for t in items}

    def report(title: str, factors: dict, seasons: list[str], max_season: str) -> None:
        sel = [g for g in games if g.season <= max_season]
        ou = [
            BinaryRow(g.match_id, g.season, int(g.home_goals + g.away_goals >= 3), opening_fair[g.match_id]["OU2.5"]["over"])
            for g in sel if g.match_id in next(iter(factors.values())) and "OU2.5" in opening_fair.get(g.match_id, {})
        ]  # fmt: skip
        print(f"\n{title} — Under/Over 2.5: {len(ou)} partite, valutate {seasons[0]} - {seasons[-1]}")
        for r in wt.run_binary(ou, factors, seasons):
            cmp = "" if r.diff is None else f"  vs ricalibrato {r.diff:+.5f} ± {r.std_error:.5f} {'PASSA' if r.passes else 'non passa'}"
            print(f"  {r.name:<42} n={r.n:<6} log loss {r.log_loss:.5f}{cmp}")
        rows = [r for r in ft.market_rows(sel, opening_fair, closing_fair) if r.match_id in next(iter(factors.values()))]
        print(f"{title} — 1X2: {len(rows)} partite")
        for r in ft.run(rows, factors, seasons, opening, offered_bet365, closing_fair):
            if r.vs_baseline is None:
                continue
            print(f"  {r.name:<42} n={r.n:<6} log loss {r.log_loss:.5f}  vs ricalibrato {r.vs_baseline.mean_diff:+.5f} ± {r.vs_baseline.std_error:.5f} {'PASSA' if r.passes else 'non passa'}")

    tuning = sorted({s for s in season_of.values() if wt.FIRST < s <= wt.LAST})
    # D76: meteo assoluto (solo stagioni di taratura)
    weather = {int(m): list(weather_factors(v)) for m, v in raw.items() if v and season_of.get(int(m), "9") <= wt.LAST}
    std = wt.standardize(weather, season_of, wt.FIRST)
    factors = {"meteo (pioggia + vento + temperatura)": std} | {f"solo {n}": {m: [v[i]] for m, v in std.items()} for i, n in enumerate(wt.FEATURE_NAMES)}
    report("D76 meteo", factors, tuning, wt.LAST)

    # D78 (3): shock climatico dell'ospite, taratura e poi conferma sulla 2025/26
    shock = {}
    for m, v in raw.items():
        t = target_of.get(int(m))
        if not v or t is None or t.away_lat is None:
            continue
        s = climate_shock(v[2], normals.get((round(t.away_lat, 2), round(t.away_lon, 2)), {}), t.kickoff.month)
        if s:
            shock[int(m)] = list(s)
    std_shock = wt.standardize(shock, season_of, wt.FIRST)
    shock_factors = {"shock climatico (con segno + assoluto)": std_shock, "solo con segno": {m: [v[0]] for m, v in std_shock.items()},
                     "solo assoluto": {m: [v[1]] for m, v in std_shock.items()}}  # fmt: skip
    report("D78 shock climatico, taratura", shock_factors, tuning, wt.LAST)
    report("D78 shock climatico, conferma", shock_factors, [wt.CONFIRMATION], wt.CONFIRMATION)
    return 0

def _popularity_test() -> int:
    """Tifo dei bookmaker (D78, ipotesi 6): taratura fino al 2024/25, conferma sul 2025/26."""
    from sqlalchemy import select

    from app.forecast import popularity_test as pt
    from app.forecast.demargin import shin
    from app.models import Competition, Match, MatchStatus

    with SessionLocal() as db:
        matches = db.execute(
            select(Match).join(Competition, Match.competition_id == Competition.id)
            .where(Competition.code.in_(pt.LEAGUES), Match.status == MatchStatus.FINISHED, Match.season >= "2013/14")
        ).scalars().all()  # fmt: skip
        teams = {m.id: (m.season, m.home_team.name, m.away_team.name) for m in matches}
        pinnacle = load_odds(db, ["pinnacle"], closing=False)
        bet365 = load_odds(db, ["bet365"], closing=False)
    rows: dict[str, list] = {"taratura (2013/14 - 2024/25)": [], "conferma (2025/26)": []}
    for match_id, (season, home, away) in teams.items():
        pin, b365 = pinnacle.get(match_id, {}).get("1X2"), bet365.get(match_id, {}).get("1X2")
        if not pin or not b365:
            continue
        fair = shin([pin["1"], pin["X"], pin["2"]])
        key = "conferma (2025/26)" if season >= "2025/26" else "taratura (2013/14 - 2024/25)"
        rows[key] += pt.value_rows(season, home, away, fair, [b365["1"], b365["X"], b365["2"]])
    for label, rs in rows.items():
        if len(rs) < 10:
            print(f"{label}: dati insufficienti ({len(rs)})")
            continue
        r = pt.regress(rs)
        print(f"{label}: {r.n} vittorie quotate")
        print(f"  squadre popolari:     {pt.describe(r.popular)}  (ipotesi: negativo)")
        print(f"  avversarie popolari:  {pt.describe(r.against_popular)}  (ipotesi: positivo)")
        print(f"  {'CONFERMATA' if r.confirmed else 'non confermata'}")
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
    pr = commands.add_parser("predict", help="calcola le previsioni di Archie per le partite in programma")
    pr.add_argument("--force", action="store_true", help="ricalcola anche se non ci sono dati nuovi")
    ft = commands.add_parser("factor-test", help="prova del nove dei fattori contro il mercato (Serie A e B)")
    ft.add_argument("--from", dest="first", default="2013/14")
    ft.add_argument("--to", dest="last", default="2024/25")
    commands.add_parser("verdict", help="verdetto sulla stagione 2025/26 (solo a cassaforte aperta)")
    commands.add_parser("popularity-test", help="tifo dei bookmaker sulle squadre popolari (D78)")
    wt = commands.add_parser("weather-test", help="prova del nove del meteo (D76)")
    wt.add_argument("--fetch-only", action="store_true", help="scarica soltanto il meteo, senza la prova")
    wt.add_argument("--patient", action="store_true", help="se Open-Meteo limita, aspetta un'ora e riprende")
    commands.add_parser("venues", help="stadi di casa delle squadre (città, campo, coordinate)")
    dm = commands.add_parser("demargin-test", help="prova del nove dei metodi per togliere il margine (D72)")
    dm.add_argument("--last", default="2024/25", help="ultima stagione valutata (la 2025/26 non si usa per tarare)")
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
    if args.command == "predict":
        with SessionLocal() as db:
            print(f"Previsioni aggiornate: {refresh_predictions(db, datetime.now(UTC), force=args.force)}")
        return 0
    if args.command == "factor-test":
        return _factor_test(args.first, args.last)
    if args.command == "popularity-test":
        return _popularity_test()
    if args.command == "weather-test":
        return _weather_test(args.fetch_only, args.patient)
    if args.command == "venues":
        return _venues()
    if args.command == "demargin-test":
        return _demargin_test(args.last)
    if args.command == "verdict":
        return _verdict()
    if args.command == "open-vault":
        return _open_vault()
    if args.command == "sync":
        return _sync(args.source, args.first_season)
    return 1


if __name__ == "__main__":
    sys.exit(main())
