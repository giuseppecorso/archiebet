"""Comandi da terminale. Uso: python -m app.cli create-user <nome> | set-password <nome> | sync | predict | backtest | open-vault"""

import argparse
import getpass
import sys
from collections.abc import Sequence
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
from app.ingest.football_data import sync_football_data
from app.ingest.teams import tidy_teams
from app.jobs import api_football_adapter, sync_api_football_all
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


def _demo_setup(first_season: int) -> int:
    """Avvio dimostrativo (Docker): utente demo, storico gratuito di football-data e previsioni. Ripetibile senza danni."""
    import os

    from sqlalchemy import func, select

    from app.models import Match, User

    username = os.environ.get("DEMO_USER", "demo")
    password = os.environ.get("DEMO_PASSWORD", "archiebet-demo")
    with SessionLocal() as db:
        if db.scalar(select(User).where(User.username == username)) is None:
            create_user(db, username, password)
            print(f"Utente dimostrativo '{username}' creato.")
        has_matches = (db.scalar(select(func.count()).select_from(Match)) or 0) > 0
    if not has_matches:
        _sync("football-data", first_season)
    with SessionLocal() as db:
        print(f"Previsioni aggiornate: {refresh_predictions(db, datetime.now(UTC), force=True)}")
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
                report = sync_api_football_all(db, settings, log=print)
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


def _timing_test() -> int:
    """Prova D119: quando conviene giocare da Sisal ed Eurobet."""
    from app.forecast import timing as tm

    from app.forecast.learning_service import load_timing_books

    books = load_timing_books()
    print(f"Partite nell'archivio: {len(books)}")

    def reference(b):
        return "consensus" if b.group == "Serie C" else "pinnacle"

    obs = tm.observations(books, reference)
    for group in ("Serie A e B", "Serie C", "estero", "serie minori"):
        sel = [o for o in obs if o.group == group]
        if not sel:
            print(f"\n{group}: nessun dato")
            continue
        advice = tm.advise(sel)
        print(f"\n{group}: {len({o.fixture_id for o in sel})} partite, {len(sel)} esiti (Sisal ed Eurobet, 1X2 e U/O 2.5)"
              f" -> {advice.verdict}{' (' + advice.best + ')' if advice.best else ''}")
        for r in advice.results:
            print(f"  {r.label:<17} CLV {r.clv.mean * 100:+.2f}% ± {r.clv.std_error * 100:.2f}   rispetto a 30 minuti {r.vs_last.mean * 100:+.2f} ± {r.vs_last.std_error * 100:.2f}"
                  f"  ({r.clv.n} esiti)")
        if group != "Serie C":
            for h in tm.OCCASION_HORIZONS:
                t = tm.occasion_timing(sel, h)
                if t is None:
                    print(f"  occasioni viste {h}: nessuna")
                    continue
                print(f"  occasioni viste {h}: {t.n}, CLV giocando subito {t.now.mean * 100:+.2f}% ± {t.now.std_error * 100:.2f},"
                      f" guadagno contro 30 minuti {t.gain.mean * 100:+.2f} ± {t.gain.std_error * 100:.2f}, ancora con valore a 30 minuti {t.still_value:.0%}"
                      f" -> {'giocala subito' if t.play_now else 'nessun consiglio'}")
    return 0


def _strategy_search(first: str, split: str, last: str) -> int:
    """Archie cerca da solo le strategie (D118): taratura fino a split escluso, conferma da split a last."""
    from app.forecast import strategy_search as ss

    from app.forecast.learning_service import HISTORY_LEAGUES, sim_matches

    by_book, fixtures = sim_matches(first, last)
    moments = ss.season_moments(fixtures)
    items = ss.bets(by_book["bet365"], moments)
    tuning = [b for b in items if b.season < split]
    confirm = [b for b in items if b.season >= split]
    strategies = ss.all_strategies(HISTORY_LEAGUES)
    print(f"Giocate possibili: taratura {len(tuning)} ({first} - prima del {split}), conferma {len(confirm)} ({split} - {last});"
          f" strategie provate: {len(strategies)}")
    results = ss.search(strategies, tuning, confirm)

    def show(r):
        def part(n, clv, roi):
            if not n:
                return "nessuna giocata"
            return f"{n:5d} giocate  CLV {clv.mean * 100:+.2f}% ± {clv.std_error * 100:.2f} (t {clv.t:4.1f})  rendimento {roi.mean * 100:+.1f}%"
        return f"  {r.strategy.name}\n     taratura: {part(r.tuning_n, r.tuning_clv, r.tuning_roi)}\n     conferma: {part(r.confirm_n, r.confirm_clv, r.confirm_roi)}"

    candidates = [r for r in results if r.candidate]
    print(f"\nCandidate in taratura (almeno {ss.MIN_PLAYS} giocate, CLV >= {ss.MIN_CLV:.0%}, t >= {ss.T_SCREEN}): {len(candidates)}")
    for r in sorted(candidates, key=lambda r: -r.tuning_clv.t):
        print(show(r) + ("   <-- PASSA" if r.passed else ""))
    passed = [r for r in candidates if r.passed]
    print(f"\nStrategie che passano la conferma: {len(passed)}")
    valid = [r for r in results if r.tuning_n >= ss.MIN_PLAYS and r.tuning_clv]
    print(f"\nPer confronto, le 10 migliori in taratura per t (anche sotto soglia), su {len(valid)} con almeno {ss.MIN_PLAYS} giocate:")
    for r in sorted(valid, key=lambda r: -r.tuning_clv.t)[:10]:
        print(show(r))
    return 0


def _history_sim(first: str, last: str) -> int:
    """Simulazione storica di Pronostici, Occasioni e Multipla del giorno (D86)."""
    from app.forecast import history_sim as hs
    from app.forecast.multiple import PROFILES

    from app.forecast.learning_service import sim_matches

    by_book, _ = sim_matches(first, last, ("bet365", "market_max"))
    sims = by_book["bet365"]
    tuning = [m for m in sims if m.season < last]
    confirm = [m for m in sims if m.season == last]
    print(f"Partite con Pinnacle (apertura e chiusura) e bet365: {len(sims)} ({first} - {last}); taratura {len(tuning)}, conferma {len(confirm)}")

    def pct(x):
        return f"{x * 100:+.2f}%"

    print("\n(1) Calibrazione dei Pronostici (Pinnacle d'apertura senza margine), tutte le stagioni")
    for market in ("1X2", "OU2.5"):
        print(f"  {market}")
        for b in hs.calibration(sims, market):
            flag = "" if abs(b.off_by) <= 2 * b.std_error else "  <-- fuori da 2 errori standard"
            print(f"    {b.low:.0%}-{b.high:.0%}: {b.n:6d} esiti  previsto {b.predicted:.1%}  uscito {b.observed:.1%}  (± {b.std_error:.1%}){flag}")
        fav = hs.favorite_hits(sims, market)
        print(f"    pronostico secco: {fav.n} partite, giusti {fav.observed} contro {fav.expected:.0f} attesi (± {fav.std_error:.0f}), rapporto {fav.ratio:.3f}")

    print("\n(2) Occasioni alla quota bet365 d'apertura")
    best_t, results = None, {}
    for rule in hs.RULES:
        t_sum, c_sum = hs.summarize_plays(hs.occasions(tuning, rule)), hs.summarize_plays(hs.occasions(confirm, rule))
        results[rule.name] = (t_sum, c_sum)
        for label, sm in (("taratura", t_sum), ("conferma", c_sum)):
            if sm is None:
                print(f"  {rule.name:<30} {label}: nessuna giocata")
                continue
            print(f"  {rule.name:<30} {label}: {sm.clv.n:5d} giocate in {sm.clv.clusters:5d} partite  CLV {pct(sm.clv.mean)} ± {sm.clv.std_error * 100:.2f}"
                  f"  (t {sm.clv.t:5.1f}){' PASSA' if sm.clv.significant else ''}   rendimento {pct(sm.roi.mean)} ± {sm.roi.std_error * 100:.1f}")
    current = results[hs.RULES[0].name]
    for rule in hs.RULES[1:]:
        t_sum, c_sum = results[rule.name]
        better = (t_sum and current[0] and t_sum.clv.t > current[0].clv.t and c_sum and current[1] and c_sum.clv.mean > current[1].clv.mean
                  and c_sum.clv.significant)
        print(f"  {rule.name}: {'migliore di D72 in taratura e in conferma' if better else 'non sostituisce D72'}")

    d72 = hs.RULES[0]
    plays = hs.occasions(sims, d72)
    print("\n  D72 per stagione / campionato / fascia di quota / mercato (tutte le stagioni)")
    for title, key in (("stagione", lambda p: p.season), ("campionato", lambda p: p.league),
                       ("quota", lambda p: hs.price_band(p.price)), ("mercato", lambda p: f"{p.market} {p.selection}")):
        print(f"   per {title}:")
        for k, ps in sorted(hs.group_plays(plays, key).items()):
            sm = hs.summarize_plays(ps)
            print(f"     {k:<12} {sm.clv.n:5d}  CLV {pct(sm.clv.mean)} ± {sm.clv.std_error * 100:.2f}   rendimento {pct(sm.roi.mean)} ± {sm.roi.std_error * 100:.1f}")

    best_sims = by_book["market_max"]
    sm = hs.summarize_plays(hs.occasions(best_sims, d72))
    if sm:
        print(f"\n  D72 alla quota migliore del mercato (non giocabile dall'utente, solo confronto): {sm.clv.n} giocate, CLV {pct(sm.clv.mean)} ± {sm.clv.std_error * 100:.2f}, rendimento {pct(sm.roi.mean)}")

    print("\n(3) Multipla del giorno (gambe 1X2 e Under/Over 2.5 a quota bet365), tutte le stagioni")
    for name, n in (("tranquilla", 3), ("equilibrata", 4), ("coraggiosa", 4)):
        ms = hs.daily_multiples(sims, PROFILES[name], n)
        su = hs.summarize_multiples(ms)
        if su is None:
            print(f"  {name}: nessuna multipla")
            continue
        value_share = sum(m.with_value for m in ms) / len(ms)
        print(f"  {name} ({n} partite): {su.n} giorni, vinte {su.wins} contro {su.expected_wins:.1f} attese (± {su.std_error:.1f})"
              f"{' OK' if su.within_two_se else ' <-- fuori da 2 errori standard'}, quota media {sum(m.price for m in ms) / len(ms):.2f},"
              f" con valore {value_share:.0%} dei giorni, rendimento {pct(su.roi)}")
    return 0


def _d89_test() -> int:
    """Prova del nove dei fattori D89: base mercato (A, B, top 5, seconde) e base modello (Serie C)."""
    from collections import defaultdict
    from datetime import timedelta

    from sqlalchemy import select

    from app.adapters.api_football import ApiFootballAdapter
    from app.forecast import factor_test as ft
    from app.forecast import factors_d89 as fd
    from app.forecast import weather_test as wt
    from app.forecast.binary_model import BinaryRow
    from app.forecast.demargin import shin
    from app.forecast.market_model import MarketRow
    from app.ingest.af_history import CUP_LEAGUES, SERIE_C_LEAGUES
    from app.ingest.teams import COUNTRY_ORDER
    from app.models import MatchSource, Team, TeamAlias

    forever = timedelta(days=36500)
    settings = get_settings()
    af = ApiFootballAdapter(FileCache(settings.data_cache_dir, "api-football"), settings.api_football_key)
    tuning, confirm = ["2022/23", "2023/24", "2024/25"], ["2025/26"]

    with SessionLocal() as db:
        af_team = {int(a.alias): a.team_id for a in db.scalars(select(TeamAlias).where(TeamAlias.source == "api-football")) if a.alias.isdigit()}
        af_match = {int(m.external_id): m.match_id for m in db.scalars(select(MatchSource).where(MatchSource.source == "api-football"))}
        teams = list(db.scalars(select(Team)))
        comps = {c.id: c for c in db.scalars(select(Competition))}
        games = sorted((g for c in COUNTRY_ORDER for g in load_games(db, c)), key=lambda g: g.kickoff_at)
        opening = load_odds(db, ["pinnacle"], closing=False)
    surface = {t.id: t.surface for t in teams}
    coords = {t.id: (t.latitude, t.longitude) for t in teams if t.latitude is not None and t.longitude is not None}

    # Calendario completo di ogni squadra: campionati (database) + coppe (API-Football)
    all_dates: dict[int, list] = defaultdict(list)
    european: dict[int, list] = defaultdict(list)
    for g in games:
        all_dates[g.home_id].append(g.kickoff_at)
        all_dates[g.away_id].append(g.kickoff_at)
    for league in CUP_LEAGUES:
        for season in range(2021, 2026):
            try:
                cup = af.fixtures(league, season, forever)
            except Exception:  # noqa: BLE001 - coppa non in cache: si salta
                continue
            for fx in cup:
                if fx.status == "cancelled":
                    continue
                for t in (fx.home.id, fx.away.id):
                    if t in af_team:
                        all_dates[af_team[t]].append(fx.kickoff_at)
                        if league in (2, 3, 848):
                            european[af_team[t]].append(fx.kickoff_at)
    fixtures = [fd.Fixture(g.match_id, g.kickoff_at, g.home_id, g.away_id) for g in games]
    f1 = fd.congestion_features(fixtures, all_dates, european)

    spells: dict[int, list] = {}
    for af_id, team_id in af_team.items():
        try:
            found = af.coaches(af_id, forever)
        except Exception:  # noqa: BLE001 - non in cache
            continue
        spells[team_id] = [fd.CoachSpell(c.start, c.end) for c in found if c.start]
    f2 = fd.coach_features(fixtures, spells)

    def report(title, rows, ou_rows, factors, seasons):
        print(f"\n{title} — 1X2: {len(rows)} partite, valutate {seasons[0]} - {seasons[-1]}")
        for r in ft.run(rows, factors, seasons, {}, {}, {}):
            cmp = "" if r.vs_baseline is None else f"  vs ricalibrato {r.vs_baseline.mean_diff:+.5f} ± {r.vs_baseline.std_error:.5f} {'PASSA' if r.passes else 'non passa'}"
            print(f"  {r.name:<44} n={r.n:<6} log loss {r.log_loss:.5f}{cmp}")
        print(f"{title} — Under/Over 2.5: {len(ou_rows)} partite")
        for r in wt.run_binary(ou_rows, factors, seasons):
            cmp = "" if r.diff is None else f"  vs ricalibrato {r.diff:+.5f} ± {r.std_error:.5f} {'PASSA' if r.passes else 'non passa'}"
            print(f"  {r.name:<44} n={r.n:<6} log loss {r.log_loss:.5f}{cmp}")

    # --- Base mercato: Pinnacle d'apertura (Shin), 10 campionati ---
    rows, ou_rows = [], []
    for g in games:
        if g.tier > 2 or not ("2021/22" <= g.season <= "2025/26"):
            continue
        o = opening.get(g.match_id, {})
        if "1X2" in o:
            p = shin([o["1X2"]["1"], o["1X2"]["X"], o["1X2"]["2"]])
            outcome = 0 if g.home_goals > g.away_goals else 1 if g.home_goals == g.away_goals else 2
            rows.append(MarketRow(g.match_id, g.season, outcome, tuple(p)))
        if "OU2.5" in o:
            p_over = shin([o["OU2.5"]["over"], o["OU2.5"]["under"]])[0]
            ou_rows.append(BinaryRow(g.match_id, g.season, int(g.home_goals + g.away_goals >= 3), p_over))
    market_factors = {"F1 partite ravvicinate (riposo + coppe europee)": f1, "F2 nuovo allenatore": f2}
    print(f"Base mercato: {len(rows)} partite con Pinnacle d'apertura; nuovi allenatori trovati in {sum(1 for v in f2.values() if v[0])} partite")
    for label, seasons in (("Taratura", tuning), ("Conferma", confirm)):
        report(f"{label} (base mercato)", [r for r in rows if r.season <= seasons[-1]], [r for r in ou_rows if r.season <= seasons[-1]], market_factors, seasons)

    # --- Base modello: Serie C, previsioni walk-forward di Archie ---
    lineups: dict[tuple[int, int], tuple] = {}
    coach_of: dict[tuple[int, int], int] = {}
    for league in SERIE_C_LEAGUES:
        for season in range(2022, 2026):
            for fx in af.fixtures(league, season, forever):
                mid = af_match.get(fx.id)
                if mid is None or fx.status != "finished":
                    continue
                try:
                    found = af.lineups(fx.id, forever)
                except Exception:  # noqa: BLE001 - non in cache
                    continue
                for lu in found:
                    team = af_team.get(lu.team_id)
                    if team is None:
                        continue
                    if lu.starters:
                        lineups[(mid, team)] = lu.starters
                    if lu.coach_id:
                        coach_of[(mid, team)] = lu.coach_id
    italian = [g for g in games if comps[g.competition_id].country == "Italia"]
    c_seasons = ["2023/24", "2024/25", "2025/26"]
    print(f"\nSerie C: formazioni per {len({m for m, _ in lineups})} partite; modello di Archie in walk-forward {c_seasons[0]} - {c_seasons[-1]} (qualche minuto)")
    res = walk_forward(italian, c_seasons, ModelConfig())
    preds = [pr for pr in res.predictions if comps[pr.competition_id].tier == 3]
    c_fixtures = [f for f in fixtures if f.match_id in {pr.match_id for pr in preds}]
    c_rows = [MarketRow(pr.match_id, pr.season, pr.outcome, pr.p_1x2) for pr in preds]
    c_ou = [BinaryRow(pr.match_id, pr.season, int(pr.total_goals >= 3), pr.p_over25) for pr in preds]
    model_factors = {
        "F1 partite ravvicinate (riposo + coppe)": f1,
        "F2 nuovo allenatore (formazioni)": fd.coach_features_from_lineups(c_fixtures, coach_of),
        "F4 campo sintetico": fd.turf_features(c_fixtures, surface),
        "F5 distanza della trasferta": fd.distance_features(c_fixtures, coords),
        "F1b titolari abituali assenti": fd.absence_features(c_fixtures, lineups),
    }
    for name, feats in model_factors.items():
        print(f"  {name}: valori per {sum(1 for f in c_fixtures if f.match_id in feats)} partite di Serie C")
    report("Taratura (base modello, Serie C)", [r for r in c_rows if r.season <= "2024/25"], [r for r in c_ou if r.season <= "2024/25"], model_factors, ["2024/25"])
    report("Conferma (base modello, Serie C)", c_rows, c_ou, model_factors, confirm)
    return 0


def _secondary_test() -> int:
    """Prova D82 su angoli e cartellini con l'archivio dello storico quote (da lanciare su una copia del database)."""
    import json
    from datetime import timedelta

    from sqlalchemy import select

    from app.adapters.oddspapi import BOOKMAKERS, TOURNAMENTS, OddsPapiAdapter, OPFixture
    from app.forecast import secondary_test as st
    from app.ingest.oddspapi import OddsPapiReport, link_fixtures
    from app.models import Match

    settings = get_settings()
    adapter = OddsPapiAdapter(FileCache(settings.data_cache_dir, "oddspapi"), settings.oddspapi_key)
    lines = {str(m["marketId"]): line for m in adapter.markets() if (line := st.line_of(m))}
    outcome_names = {str(o["outcomeId"]): o["outcomeName"].lower() for m in adapter.markets() if str(m["marketId"]) in lines for o in m["outcomes"]}
    records = []
    for path in (settings.data_cache_dir / "odds-archive").glob("*.json"):
        data = json.loads(path.read_text(encoding="utf-8"))["data"]
        if data["bookmakers"] and TOURNAMENTS.get(data["fixture"]["tournamentId"], "").startswith(("ITA-A", "ITA-B", "ENG", "ESP", "GER", "FRA")):
            records.append(data)
    print(f"Archivio: {len(records)} partite con storico (campionati con i risultati di angoli e cartellini)")

    fixtures = [OPFixture(r["fixture"]["fixtureId"], r["fixture"]["tournamentId"], datetime.fromisoformat(r["fixture"]["startTime"].replace("Z", "+00:00")),
                          r["fixture"]["participant1Id"], r["fixture"]["participant2Id"], 2) for r in records]  # fmt: skip
    names = {str(r["fixture"][f"participant{k}Id"]): r["fixture"][f"participant{k}Name"] for r in records for k in (1, 2)}
    with SessionLocal() as db:
        report = OddsPapiReport()
        links = link_fixtures(db, fixtures, adapter.participants() | names, report, datetime.now(UTC))
        db.commit()
        results = {}
        for fid, m in links.items():
            if m.home_corners is not None and m.home_yellow is not None:
                results[fid] = st.Result(m.home_corners, m.away_corners, m.home_yellow, m.away_yellow, m.home_red or 0, m.away_red or 0)
    print(f"Agganciate: {len(links)} partite, con risultati di angoli e cartellini: {len(results)}; squadre non riconosciute: {len(set(report.unknown_teams))}")

    def series(points):
        out = []
        for p in points:
            ts = datetime.fromisoformat(p["createdAt"].replace("Z", "+00:00"))
            out.append((ts, float(p["price"]) if p.get("active", True) and p.get("price") else None))
        return sorted(out, key=lambda x: x[0])

    histories = []
    for r, fx in zip(records, fixtures):
        if fx.id not in links:
            continue
        by_market: dict[str, dict] = {}
        for slug, book in r["bookmakers"].items():
            bm = BOOKMAKERS.get(slug, slug)
            for mid, market in (book.get("markets") or {}).items():
                if mid not in lines:
                    continue
                for oid, outcome in (market.get("outcomes") or {}).items():
                    name = outcome_names.get(oid)
                    if name in ("over", "under"):
                        by_market.setdefault(mid, {}).setdefault(bm, {})[name] = series((outcome.get("players") or {}).get("0") or [])
        for mid, prices in by_market.items():
            histories.append(st.MarketHistory(fx.id, fx.start_time, lines[mid], prices))
    print(f"Linee Over/Under: {len(histories)}")

    print("\n(a)+(b) Precisione delle quote di chiusura (log loss dell'Over, più basso = meglio), Pinnacle contro ogni italiano sulle stesse linee")
    best_rule: dict[str, tuple[str, float]] = {}
    for family in ("angoli", "cartellini"):
        for rule in (st.RULES if family == "cartellini" else ("cartellini",)):
            label = family if family == "angoli" else f"{family}, regola '{rule}'"
            for italian in ("sisal", "eurobet"):
                acc = {a.bookmaker: a for a in st.closing_log_loss(histories, results, ("pinnacle", italian), family, rule)}
                if len(acc) < 2:
                    print(f"  {label}, {italian}: nessuna linea in comune")
                    continue
                pin, it = acc["pinnacle"], acc[italian]
                print(f"  {label}: pinnacle {pin.log_loss:.4f} contro {italian} {it.log_loss:.4f} (n {it.n})"
                      f"  {'Pinnacle almeno pari' if pin.log_loss <= it.log_loss else italian + ' più preciso'}")
                if family == "cartellini":
                    for a in acc.values():
                        if a.bookmaker not in best_rule or a.log_loss < best_rule[a.bookmaker][1]:
                            best_rule[a.bookmaker] = (rule, a.log_loss)
    if best_rule:
        print("  regola dei cartellini che spiega meglio ogni bookmaker: " + ", ".join(f"{bm} '{r}'" for bm, (r, _) in sorted(best_rule.items())))

    print("\n(c) Occasioni con la regola D72 su Sisal ed Eurobet (CLV contro la chiusura di Pinnacle, errore standard per partita)")
    rule_of = lambda bm: best_rule.get(bm, ("cartellini", 0))[0]  # noqa: E731
    for family in ("angoli", "cartellini"):
        for side in ("totale", "squadra"):
            hs = [h for h in histories if h.line.family == family and (h.line.side == "totale") == (side == "totale")]
            plays = st.occasions(hs, results, ("sisal", "eurobet"), rule_of)
            est = st.clv_estimate(plays)
            if est is None:
                print(f"  {family} {side}: nessuna occasione")
                continue
            won = [p for p in plays if p.match_id in results]
            roi = sum((p.price - 1) if p.won else -1 for p in won) / len(won) if won else float("nan")
            print(f"  {family} {side}: {est.n} occasioni in {est.clusters} partite, CLV {est.mean * 100:+.2f}% ± {est.std_error * 100:.2f}"
                  f" (t {est.t:.1f}){' PASSA' if est.significant else ''}; rendimento {roi * 100:+.1f}% su {len(won)}")
    return 0


def _live_check() -> int:
    """Verifica del termometro (D92) e dell'effetto del punteggio (D93) sul risultato all'intervallo."""
    import math

    import numpy as np
    from sqlalchemy import select

    from app.forecast import live as lv
    from app.forecast.demargin import shin
    from app.forecast.history_sim import CalibrationBin
    from app.models import Match, MatchStatus

    leagues = ("ITA-A", "ITA-B", "ENG-1", "ENG-2", "ESP-1", "ESP-2", "GER-1", "GER-2", "FRA-1", "FRA-2")
    with SessionLocal() as db:
        matches = db.execute(
            select(Match).join(Competition, Match.competition_id == Competition.id)
            .where(Competition.code.in_(leagues), Match.status == MatchStatus.FINISHED, Match.season >= "2021/22",
                   Match.ht_home_goals.is_not(None))
        ).scalars().all()  # fmt: skip
        rows = [(m.id, m.season, m.home_goals, m.away_goals, m.ht_home_goals, m.ht_away_goals) for m in matches]
        closing = load_odds(db, ["pinnacle"], closing=True)

    fits = {}  # partita -> (p1, px, p2, gol attesi casa, gol attesi ospite)
    for mid, *_ in rows:
        o = closing.get(mid, {})
        if "1X2" in o:
            p1, px, p2 = shin([o["1X2"]["1"], o["1X2"]["X"], o["1X2"]["2"]])
            p_over = shin([o["OU2.5"]["over"], o["OU2.5"]["under"]])[0] if "OU2.5" in o else None
            fits[mid] = (p1, px, p2, *lv.fit_rates(p1, p2, p_over))
    rows = [r for r in rows if r[0] in fits]
    tuning, confirm = [r for r in rows if r[1] <= "2024/25"], [r for r in rows if r[1] == "2025/26"]
    first_half = sum(r[4] + r[5] for r in tuning) / sum(r[2] + r[3] for r in tuning)
    share = 1 - first_half
    print(f"Quota dei gol nel primo tempo (taratura, {len(tuning)} partite): {first_half:.3f}  (nel modello: {lv.FIRST_HALF_SHARE})")

    # D93: gol del secondo tempo osservati / attesi per chi è avanti, indietro, in parità all'intervallo
    obs = {"leader": 0.0, "trailer": 0.0, "level": 0.0}
    exp = {"leader": 0.0, "trailer": 0.0, "level": 0.0}
    for mid, season, hg, ag, hth, hta in tuning:
        lh, la = fits[mid][3] * share, fits[mid][4] * share
        sides = ("leader", "trailer") if hth > hta else ("trailer", "leader") if hth < hta else ("level", "level")
        for side, o_goals, e_goals in zip(sides, (hg - hth, ag - hta), (lh, la)):
            obs[side] += o_goals
            exp[side] += e_goals
    effect = {k: obs[k] / exp[k] for k in obs}
    print("Effetto del punteggio (gol del secondo tempo osservati / attesi): " + ", ".join(f"{k} {v:.3f}" for k, v in effect.items()))

    def evaluate(sample, eff):
        out, preds, best = [], [], []
        for mid, season, hg, ag, hth, hta in sample:
            p1, px, p2, lh, la = fits[mid]
            rh, ra = lv.remaining_rates((lh, la), share, hth, hta, eff)
            probs = lv.outcome_probabilities(rh, ra, hth, hta)
            result = "1" if hg > ag else "X" if hg == ag else "2"
            out.append(-math.log(max(probs[result], 1e-9)))
            preds += [(probs[sel], sel == result) for sel in ("1", "X", "2")]
            top = max(("1", "X", "2"), key=lambda sel: probs[sel])
            best.append((probs[top], top == result))
        return np.array(out), preds, best

    def calibration_table(preds):
        edges = (0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.8, 1.0001)
        outside = 0
        for low, high in zip(edges, edges[1:]):
            inside = [(p, w) for p, w in preds if low <= p < high]
            if not inside:
                continue
            k = len(inside)
            b = CalibrationBin(low, min(high, 1.0), k, sum(p for p, _ in inside) / k, sum(w for _, w in inside) / k,
                               math.sqrt(sum(p * (1 - p) for p, _ in inside)) / k)
            off = abs(b.off_by) > 2 * b.std_error
            outside += off
            print(f"    {b.low:.0%}-{b.high:.0%}: {b.n:6d} esiti  previsto {b.predicted:.1%}  uscito {b.observed:.1%}  (± {b.std_error:.1%}){'  <-- fuori' if off else ''}")
        return outside

    results = {}
    for label, sample in (("Taratura 2021/22 - 2024/25", tuning), ("Conferma 2025/26", confirm)):
        print(f"\n{label}: {len(sample)} partite")
        for name, eff in (("senza effetto del punteggio (D92)", lv.NO_SCORE_EFFECT), ("con effetto del punteggio (D93)", effect)):
            ll, preds, best = evaluate(sample, eff)
            print(f"  {name}: log loss all'intervallo {ll.mean():.4f}")
            outside = calibration_table(preds)
            hits, expected = sum(w for _, w in best), sum(p for p, _ in best)
            se = math.sqrt(sum(p * (1 - p) for p, _ in best))
            print(f"    esito più probabile: uscito {hits} contro {expected:.0f} attese (± {se:.0f}); fasce fuori: {outside}")
            results[(label, name)] = (ll, outside, abs(hits - expected) <= 2 * se)

    base = results[("Conferma 2025/26", "senza effetto del punteggio (D92)")]
    new = results[("Conferma 2025/26", "con effetto del punteggio (D93)")]
    diff = new[0] - base[0]
    se = diff.std(ddof=1) / math.sqrt(len(diff))
    adopt = diff.mean() < -2 * se and new[1] <= base[1]
    print(f"\nD92 termometro: {'AFFIDABILE' if base[1] <= 1 and base[2] else 'non affidabile'} (fasce fuori {base[1]})")
    print(f"D93 effetto del punteggio, conferma: log loss {diff.mean():+.5f} ± {se:.5f}, fasce fuori {new[1]} contro {base[1]} -> {'SI ADOTTA' if adopt else 'non si adotta'}")
    return 0


def _seriec_test() -> int:
    """Prova D95: modello di Archie contro il consenso di Sisal, Eurobet e Snai in Serie C (usare una copia del database)."""
    import json
    import math

    import numpy as np

    from app.adapters.oddspapi import BOOKMAKERS, MARKETS, TOURNAMENTS, OddsPapiAdapter, OPFixture
    from app.forecast.demargin import proportional
    from app.forecast.secondary_test import closing
    from app.ingest.oddspapi import OddsPapiReport, link_fixtures

    settings = get_settings()
    adapter = OddsPapiAdapter(FileCache(settings.data_cache_dir, "oddspapi"), settings.oddspapi_key)
    records = []
    for path in (settings.data_cache_dir / "odds-archive").glob("*.json"):
        data = json.loads(path.read_text(encoding="utf-8"))["data"]
        if data["bookmakers"] and TOURNAMENTS.get(data["fixture"]["tournamentId"], "").startswith("ITA-C"):
            records.append(data)
    fixtures = [OPFixture(r["fixture"]["fixtureId"], r["fixture"]["tournamentId"], datetime.fromisoformat(r["fixture"]["startTime"].replace("Z", "+00:00")),
                          r["fixture"]["participant1Id"], r["fixture"]["participant2Id"], 2) for r in records]  # fmt: skip
    names = {str(r["fixture"][f"participant{k}Id"]): r["fixture"][f"participant{k}Name"] for r in records for k in (1, 2)}
    with SessionLocal() as db:
        report = OddsPapiReport()
        links = link_fixtures(db, fixtures, adapter.participants() | names, report, datetime.now(UTC))
        db.commit()
        linked = {fid: (m.id, m.season, m.home_goals, m.away_goals, m.status) for fid, m in links.items()}
        games = load_games(db)
    print(f"Serie C nell'archivio: {len(records)} partite, agganciate {len(linked)}; squadre non riconosciute: {sorted(set(report.unknown_teams))[:10]}")

    # Consenso dei bookmaker italiani in chiusura (ultima quota attiva prima del calcio d'inizio)
    name_1x2, outcomes_1x2 = MARKETS["101"]
    consensus = {}
    for r, fx in zip(records, fixtures):
        if fx.id not in linked:
            continue
        probs = []
        for slug, book in r["bookmakers"].items():
            market = (book.get("markets") or {}).get("101")
            if not market:
                continue
            prices = {}
            for oid, outcome in (market.get("outcomes") or {}).items():
                points = [(datetime.fromisoformat(p["createdAt"].replace("Z", "+00:00")), float(p["price"]) if p.get("active", True) and p.get("price") else None)
                          for p in (outcome.get("players") or {}).get("0") or []]  # fmt: skip
                price = closing(sorted(points, key=lambda x: x[0]), fx.start_time)
                if price and oid in outcomes_1x2:
                    prices[outcomes_1x2[oid]] = price
            if set(prices) == {"1", "X", "2"}:
                probs.append(dict(zip(("1", "X", "2"), proportional([prices["1"], prices["X"], prices["2"]]))))
        if probs:
            mid = linked[fx.id][0]
            consensus[mid] = {k: sum(p[k] for p in probs) / len(probs) for k in ("1", "X", "2")}

    seasons = sorted({linked[f][1] for f in linked})
    print(f"Consenso dei bookmaker per {len(consensus)} partite; modello di Archie in walk-forward {seasons} (qualche minuto)")
    res = walk_forward(games, seasons, ModelConfig())
    model = {p.match_id: p for p in res.predictions}
    diffs, ll_model, ll_books = [], [], []
    for mid, cons in consensus.items():
        p = model.get(mid)
        if p is None:
            continue
        result = ("1", "X", "2")[p.outcome]
        a, b = -math.log(max(p.p_1x2[p.outcome], 1e-9)), -math.log(max(cons[result], 1e-9))
        ll_model.append(a)
        ll_books.append(b)
        diffs.append(a - b)
    d = np.array(diffs)
    se = d.std(ddof=1) / math.sqrt(len(d))
    print(f"\nPartite confrontate: {len(d)}")
    print(f"  log loss 1X2: Archie {np.mean(ll_model):.4f}, consenso Sisal/Eurobet/Snai {np.mean(ll_books):.4f}")
    print(f"  Archie meno consenso: {d.mean():+.5f} ± {se:.5f}  (negativo = Archie più preciso)")
    verdict = "Archie MIGLIORE: 'sopra Archie' diventa 'valore'" if d.mean() < -2 * se else (
        "Archie PEGGIORE: in Serie C la stima migliore diventa il consenso dei bookmaker" if d.mean() > 2 * se else "nessuna differenza dimostrata: resta tutto com'è")
    print(f"Verdetto D95: {verdict}")
    return 0


def _seriec_edge() -> int:
    """Prova D98: battere il consenso dei bookmaker italiani in Serie C (usare una copia del database)."""
    import json
    from collections import defaultdict
    from datetime import timedelta

    from sqlalchemy import select

    from app.adapters.api_football import ApiFootballAdapter
    from app.adapters.oddspapi import MARKETS, TOURNAMENTS, OddsPapiAdapter, OPFixture
    from app.forecast import seriec_edge as se
    from app.forecast.factors_d89 import Fixture, absence_features
    from app.ingest.af_history import SERIE_C_LEAGUES
    from app.ingest.oddspapi import OddsPapiReport, link_fixtures
    from app.models import MatchSource, TeamAlias

    settings = get_settings()
    adapter = OddsPapiAdapter(FileCache(settings.data_cache_dir, "oddspapi"), settings.oddspapi_key)
    af = ApiFootballAdapter(FileCache(settings.data_cache_dir, "api-football"), settings.api_football_key)
    records = []
    for path in (settings.data_cache_dir / "odds-archive").glob("*.json"):
        data = json.loads(path.read_text(encoding="utf-8"))["data"]
        if data["bookmakers"] and TOURNAMENTS.get(data["fixture"]["tournamentId"], "").startswith("ITA-C"):
            records.append(data)
    fixtures = [OPFixture(r["fixture"]["fixtureId"], r["fixture"]["tournamentId"], datetime.fromisoformat(r["fixture"]["startTime"].replace("Z", "+00:00")),
                          r["fixture"]["participant1Id"], r["fixture"]["participant2Id"], 2) for r in records]  # fmt: skip
    names = {str(r["fixture"][f"participant{k}Id"]): r["fixture"][f"participant{k}Name"] for r in records for k in (1, 2)}
    with SessionLocal() as db:
        links = link_fixtures(db, fixtures, adapter.participants() | names, OddsPapiReport(), datetime.now(UTC))
        db.commit()
        linked = {fid: (m.id, m.home_goals, m.away_goals) for fid, m in links.items() if m.home_goals is not None and m.away_goals is not None}
        af_team = {int(a.alias): a.team_id for a in db.scalars(select(TeamAlias).where(TeamAlias.source == "api-football")) if a.alias.isdigit()}
        af_match = {int(m.external_id): m.match_id for m in db.scalars(select(MatchSource).where(MatchSource.source == "api-football"))}
        games = load_games(db)

    # Storia delle quote per partita (bookmaker → mercato → esito → serie)
    def ts(text: str) -> datetime:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))

    books = []
    for r, fx in zip(records, fixtures):
        if fx.id not in linked:
            continue
        prices: dict = {}
        for slug, book in r["bookmakers"].items():
            for market_id, market in (book.get("markets") or {}).items():
                if market_id not in MARKETS or MARKETS[market_id][0] not in se.SELECTIONS:
                    continue
                name, outcomes = MARKETS[market_id]
                for oid, outcome in (market.get("outcomes") or {}).items():
                    if oid in outcomes:
                        series = sorted((ts(p["createdAt"]), float(p["price"]) if p.get("active", True) and p.get("price") else None)
                                        for p in (outcome.get("players") or {}).get("0") or [])  # fmt: skip
                        prices.setdefault(slug.split(".")[0], {}).setdefault(name, {})[outcomes[oid]] = series
        mid, hg, ag = linked[fx.id]
        books.append(se.MatchBook(mid, fx.start_time, hg, ag, prices))
    tuning = [m for m in books if m.kickoff < se.SPLIT]
    confirm = [m for m in books if m.kickoff >= se.SPLIT]
    print(f"Serie C nell'archivio: {len(records)} partite, con risultato e quote {len(books)} (taratura {len(tuning)}, conferma {len(confirm)})")

    # (T0) il consenso in chiusura è un riferimento migliore dell'apertura?
    diffs, ids = [], []
    for m in books:
        close, open_ = se.consensus(m.snapshot("1X2"), "1X2"), se.opening_consensus(m)
        if close and open_:
            w = m.winner("1X2")
            diffs.append(se.log_loss(close[w]) - se.log_loss(open_[w]))
            ids.append(m.match_id)
    t0 = se.paired(diffs, ids)
    t0_ok = t0.mean <= 0
    print(f"\n(T0) chiusura meno apertura, log loss 1X2: {t0.mean:+.5f} ± {t0.std_error:.5f} su {t0.n} partite -> {'passa' if t0_ok else 'NON passa'}")

    # Righe per T1-T3: consenso in chiusura e informazioni in più
    base = {}
    for m in books:
        c = se.consensus(m.snapshot("1X2"), "1X2")
        if c:
            base[m.match_id] = (m.kickoff, "1X2".index(m.winner("1X2")), (c["1"], c["X"], c["2"]))

    # T1: formazioni ufficiali (titolari abituali dalle 5 partite precedenti della stessa stagione)
    starters: dict[tuple[int, int], tuple] = {}
    for league in SERIE_C_LEAGUES:
        for season in (2025, 2026):
            age = timedelta(days=36500) if season == 2025 else timedelta(hours=12)
            for fx in af.fixtures(league, season, age):
                mid = af_match.get(fx.id)
                if mid is None or fx.status != "finished":
                    continue
                for lu in af.lineups(fx.id, timedelta(days=36500)):
                    team = af_team.get(lu.team_id)
                    if team is not None and lu.starters:
                        starters[(mid, team)] = lu.starters
    absence: dict[int, list[float]] = {}
    serie_c = [g for g in games if g.tier == 3 and g.season in ("2025/26", "2026/27")]
    for season in ("2025/26", "2026/27"):
        absence |= absence_features([Fixture(g.match_id, g.kickoff_at, g.home_id, g.away_id) for g in serie_c if g.season == season], starters)
    print(f"Formazioni: {len({m for m, _ in starters})} partite di Serie C; con assenze calcolabili tra quelle in prova: {sum(1 for m in base if m in absence)}")

    # T2: modello di Archie in walk-forward
    res = walk_forward(games, ["2025/26", "2026/27"], ModelConfig())
    archie = {p.match_id: tuple(p.p_1x2) for p in res.predictions}

    extras = {
        "T1 formazioni": {m: tuple(a) for m, a in absence.items()},
        "T2 combinazione con Archie": archie,
        "T3 calibrazione (pareggi, sfavoriti)": defaultdict(tuple),
    }
    results = {}
    for label, spec in se.SPECS.items():
        rows = [se.Row(mid, k, o, c, extras[label][mid]) for mid, (k, o, c) in sorted(base.items(), key=lambda x: x[1][0])
                if label.startswith("T3") or mid in extras[label]]  # fmt: skip
        tune = [r for r in rows if r.kickoff < se.SPLIT]
        conf = [r for r in rows if r.kickoff >= se.SPLIT]
        cv = se.improvement(tune, se.cross_validated(tune, spec))
        params = se.fit(tune, spec)
        out = se.improvement(conf, [spec.correction(r, params) for r in conf])
        ok = se.passes(cv) and se.passes(out)
        results[label] = ok
        print(f"\n({label}) partite: taratura {len(tune)}, conferma {len(conf)}; parametri stimati sulla taratura {tuple(round(p, 3) for p in params)}")
        print(f"   taratura (validazione incrociata): {cv.mean:+.5f} ± {cv.std_error:.5f}   conferma: {out.mean:+.5f} ± {out.std_error:.5f}"
              f"   -> {'PASSA' if ok else 'non passa'}  (negativo = meglio del consenso)")  # fmt: skip

    # (T4) Occasioni contro il consenso degli altri due bookmaker
    plays = se.kaunitz_occasions(books)
    print(f"\n(T4) Occasioni contro il consenso degli altri bookmaker: {len(plays)} giocate")
    t4 = {}
    for label, part in (("taratura", [p for p in plays if p.kickoff < se.SPLIT]), ("conferma", [p for p in plays if p.kickoff >= se.SPLIT])):
        est = se.clv_of(part)
        if est is None:
            print(f"   {label}: nessuna giocata")
            t4[label] = False
            continue
        t4[label] = est.mean > 2 * est.std_error
        profit = sum(p.price - 1 if p.won else -1 for p in part) / len(part)
        hits, expected = sum(p.won for p in part), sum(p.p_close for p in part)
        print(f"   {label}: {est.n} giocate in {est.clusters} partite, CLV {est.mean:+.2%} ± {est.std_error:.2%} (t {est.t:.1f});"
              f" controllo: rendimento {profit:+.1%}, vinte {hits} contro {expected:.1f} attese")  # fmt: skip
        by_market = defaultdict(list)
        for p in part:
            by_market[(p.market, p.selection)].append(p)
        for key, ps in sorted(by_market.items()):
            e = se.clv_of(ps)
            print(f"      {key[0]} {key[1]}: {len(ps)} giocate, CLV {e.mean:+.2%}")
    t4_ok = t0_ok and all(t4.values())
    print(f"   -> {'PASSA' if t4_ok else 'non passa'}" + ("" if t0_ok else " (T0 non superato: non si giudica)"))
    passed = [k for k, v in results.items() if v] + (["T4 occasioni contro il consenso"] if t4_ok else [])
    print(f"\nVerdetto D98: {', '.join(passed) if passed else 'nessuna prova superata'}")
    # --- D99: Archie contro le quote d'apertura ---
    print("\n=== D99: Archie contro le quote d'apertura ===")
    spec = se.SPECS["T2 combinazione con Archie"]
    rows = []
    for m in sorted(books, key=lambda x: x.kickoff):
        o = se.opening_consensus(m)
        if o and m.match_id in archie:
            rows.append(se.Row(m.match_id, m.kickoff, "1X2".index(m.winner("1X2")), (o["1"], o["X"], o["2"]), archie[m.match_id]))
    tune = [r for r in rows if r.kickoff < se.SPLIT]
    conf = [r for r in rows if r.kickoff >= se.SPLIT]
    cv = se.improvement(tune, se.cross_validated(tune, spec))
    params = se.fit(tune, spec)
    out = se.improvement(conf, [spec.correction(r, params) for r in conf])
    a_ok = se.passes(cv) and se.passes(out)
    print(f"(a) combinazione in apertura: taratura {len(tune)}, conferma {len(conf)}; peso di Archie {params[0]:.3f}")
    print(f"   taratura (validazione incrociata): {cv.mean:+.5f} ± {cv.std_error:.5f}   conferma: {out.mean:+.5f} ± {out.std_error:.5f}"
          f"   -> {'PASSA' if a_ok else 'non passa'}")  # fmt: skip
    model = {}
    for pr in res.predictions:
        model[(pr.match_id, "1X2")] = dict(zip(("1", "X", "2"), pr.p_1x2))
        model[(pr.match_id, "OU2.5")] = {"over": pr.p_over25, "under": 1 - pr.p_over25}
    plays = se.model_occasions(books, model)
    b = {}
    print(f"(b) occasioni 'sopra Archie' (Sisal, Eurobet): {len(plays)} giocate")
    for label, part in (("taratura", [p for p in plays if p.kickoff < se.SPLIT]), ("conferma", [p for p in plays if p.kickoff >= se.SPLIT])):
        est = se.clv_of(part)
        if est is None:
            print(f"   {label}: nessuna giocata")
            b[label] = False
            continue
        b[label] = est.mean > 2 * est.std_error
        profit = sum(p.price - 1 if p.won else -1 for p in part) / len(part)
        hits, expected = sum(p.won for p in part), sum(p.p_close for p in part)
        print(f"   {label}: {est.n} giocate in {est.clusters} partite, CLV {est.mean:+.2%} ± {est.std_error:.2%} (t {est.t:.1f});"
              f" controllo: rendimento {profit:+.1%}, vinte {hits} contro {expected:.1f} attese")  # fmt: skip
    b_ok = all(b.values())
    print(f"   -> {'PASSA' if b_ok else 'non passa'}")
    print(f"Verdetto D99: (a) {'passa' if a_ok else 'non passa'}, (b) {'passa' if b_ok else 'non passa'}")
    return 0

def _odds_archive(since: str, minor: bool = False, east: bool = False) -> int:
    """Salva lo storico quote di OddsPapi (gratuito, ma solo ~6 mesi) per le prove sui mercati (D82)."""
    from app.adapters.cache import FileCache
    from app.adapters.oddspapi import OddsPapiAdapter
    from app.ingest.odds_archive import archive_history

    settings = get_settings()
    adapter = OddsPapiAdapter(FileCache(settings.data_cache_dir, "oddspapi"), settings.oddspapi_key,
                              monthly_reserve=settings.oddspapi_monthly_reserve)
    start = datetime.fromisoformat(since).replace(tzinfo=UTC)
    tournaments = None
    if minor:
        from app.ingest.odds_archive import MINOR_TOURNAMENTS

        tournaments = MINOR_TOURNAMENTS
    if east:
        from app.ingest.odds_archive import EAST_NORTH_TOURNAMENTS

        tournaments = EAST_NORTH_TOURNAMENTS
    report = archive_history(adapter, FileCache(settings.data_cache_dir, "odds-archive"), start, tournaments=tournaments)
    print(f"Archivio: {report.saved} salvate, {report.missing} senza storico, {report.already} già presenti, {report.failed} da riprovare")
    return 0


def _style_test() -> int:
    """Prova D108: gli stili di gioco che si incastrano aggiungono qualcosa al modello "fatti × subiti"?"""
    import numpy as np
    from sqlalchemy import select

    from app.forecast import counts as ct
    from app.models import Match

    leagues = ("ITA-A", "ITA-B", "ENG-1", "ENG-2", "ESP-1", "ESP-2", "GER-1", "GER-2", "FRA-1", "FRA-2")
    with SessionLocal() as db:
        rows = db.execute(
            select(Match, Competition.code).join(Competition, Competition.id == Match.competition_id)
            .where(Competition.code.in_(leagues), Match.status == "finished", Match.season >= "2009/10")
        ).all()  # fmt: skip
    games = []
    for m, code in rows:
        vals = (m.home_shots, m.away_shots, m.home_corners, m.away_corners, m.home_fouls, m.away_fouls, m.home_yellow, m.away_yellow, m.home_red, m.away_red)
        if any(v is None for v in vals):
            continue
        games.append(ct.CountGame(m.id, code, m.season, m.kickoff_at, m.home_team_id, m.away_team_id, {
            "shots": (m.home_shots, m.away_shots), "corners": (m.home_corners, m.away_corners), "fouls": (m.home_fouls, m.away_fouls),
            "cards": (m.home_yellow + m.home_red, m.away_yellow + m.away_red)}))  # fmt: skip
    print(f"Partite con tutti i numeri: {len(games)}")
    last_tuning = "2021/22"
    for label, target, driver in (("S1 angoli ← tiri", "corners", "shots"), ("S2 cartellini ← falli", "cards", "fouls"), ("S3 tiri ← tiri", "shots", "shots")):
        best = None
        for k in (2, 4, 8, 16):
            rs = [r for r in ct.build_rows(games, target, driver, k) if r.season >= "2010/11"]
            tune = [r for r in rs if r.season <= last_tuning]
            size = ct.fit_size(tune)
            y, b, s = ct.arrays(tune)
            ll = ct.log_lik_vec(y, b, s, size).sum()
            if best is None or ll > best[0]:
                best = (ll, k, rs, size)
        _, k, rs, size = best
        tune = [r for r in rs if r.season <= last_tuning]
        conf = [r for r in rs if r.season > last_tuning]
        # Controllo: il modello base batte la sola media del campionato (forze tutte a 1)?
        flat = {r.match_id: r for r in ct.build_rows(games, target, driver, 1e9)}
        flat_conf = [flat[r.match_id] for r in conf]
        flat_size = ct.fit_size([flat[r.match_id] for r in tune])
        yc, bc, sc = ct.arrays(conf)
        yf, bf, sf = ct.arrays(flat_conf)
        base_vs_flat = ct.paired(ct.log_lik_vec(yc, bc, sc, size) - ct.log_lik_vec(yf, bf, sf, flat_size))
        # Validazione incrociata in taratura (una stagione fuori alla volta) e conferma
        cv = []
        for season in sorted({r.season for r in tune}):
            beta = ct.fit_beta([r for r in tune if r.season != season], size)
            cv.append(ct.gain([r for r in tune if r.season == season], size, beta))
        cv_est = ct.paired(np.concatenate(cv))
        beta = ct.fit_beta(tune, size)
        conf_est = ct.paired(ct.gain(conf, size, beta))
        ok = cv_est[0] > 2 * cv_est[1] and conf_est[0] > 2 * conf_est[1]
        print(f"\n({label}) k={k}, dispersione {size:.1f}; partite: taratura {len(tune)}, conferma {len(conf)}")
        print(f"   controllo, modello base meno sola media (conferma): {base_vs_flat[0]:+.4f} ± {base_vs_flat[1]:.4f} per partita")
        print(f"   coefficiente di stile {beta:+.3f}; guadagno taratura {cv_est[0]:+.5f} ± {cv_est[1]:.5f}, conferma {conf_est[0]:+.5f} ± {conf_est[1]:.5f}"
              f" -> {'PASSA' if ok else 'non passa'}")  # fmt: skip
    return 0


def _minor_test(group: str = "serie minori") -> int:
    """Prove D106 / D128 (b): Occasioni D72 su Sisal ed Eurobet contro Pinnacle, CLV contro la chiusura Pinnacle.

    La prova passa solo se passano (a) e (b): si comincia da (b), che non ha bisogno dei risultati."""
    from collections import defaultdict

    from app.forecast import seriec_edge as se
    from app.forecast.learning_service import load_timing_books

    minor = [b for b in load_timing_books() if b.group == group]
    books = [se.MatchBook(i, b.kickoff, 0, 0, b.prices) for i, b in enumerate(minor)]
    with_pin = [m for m in books if "pinnacle" in m.prices]
    times = sorted(m.kickoff for m in with_pin)
    split = times[len(times) // 2]
    print(f"{group.capitalize()} nell'archivio: {len(books)} partite, con Pinnacle {len(with_pin)}; divisione al {split:%d/%m/%Y}")
    plays = se.pinnacle_occasions(with_pin)
    ok = True
    for label, part in (("taratura", [p for p in plays if p.kickoff < split]), ("conferma", [p for p in plays if p.kickoff >= split])):
        e = se.clv_of(part)
        if e is None:
            print(f"  {label}: nessuna occasione")
            ok = False
            continue
        good = e.mean > 2 * e.std_error
        ok = ok and good
        print(f"  {label}: {e.n} occasioni in {e.clusters} partite, CLV {e.mean * 100:+.2f}% ± {e.std_error * 100:.2f} -> {'positivo' if good else 'non positivo'}")
    by_market = defaultdict(list)
    for p in plays:
        by_market[p.market].append(p)
    for market, ps in sorted(by_market.items()):
        e = se.clv_of(ps)
        print(f"  (controllo) {market}: {e.n} occasioni, CLV {e.mean * 100:+.2f}% ± {e.std_error * 100:.2f}")
    print(f"(b) {'PASSA' if ok else 'NON passa'}" + ("" if ok else ": la prova D106 non passa, (a) non serve"))
    return 0


def _lineup_test() -> int:
    """Prova D123: formazioni previste (metodo pesato) contro "stessi titolari dell'ultima partita"."""
    from app.forecast.lineups import backtest
    from app.ingest.af_stats import STATS_LEAGUES, load_player_games

    cache = FileCache(get_settings().data_cache_dir, "api-football")
    for league, name in STATS_LEAGUES.items():
        for season in (2024, 2025, 2026):
            t = backtest(load_player_games(cache, league, season))
            if t is None:
                print(f"{name} {season}: nessun dato")
                continue
            print(f"{name} {season}: {t.n} formazioni, indovinati su 11: Archie {t.archie:.2f}, ultima formazione {t.last:.2f},"
                  f" differenza {t.gain.mean:+.3f} ± {t.gain.std_error:.3f} -> {'PASSA' if t.passes else 'non passa'}")
    return 0


def _player_test() -> int:
    """Prova D110: tiri dei giocatori, modello contro la media a presenza (solo dati già in cache)."""
    import math
    from datetime import timedelta

    import numpy as np
    from scipy.optimize import minimize_scalar
    from scipy.special import gammaln

    from app.adapters.api_football import ApiFootballAdapter
    from app.adapters.cache import MISSING
    from app.forecast import player_props as pp
    from app.forecast.history_sim import clustered_mean
    from app.ingest.af_stats import STATS_LEAGUES

    settings = get_settings()
    af = ApiFootballAdapter(FileCache(settings.data_cache_dir, "api-football"), settings.api_football_key)
    forever = timedelta(days=36500)
    games = []
    for league in STATS_LEAGUES:
        for season in (2024, 2025, 2026):
            body = af.cache.get(f"fixtures?league={league}&season={season}", forever)
            if body is MISSING:
                continue
            from app.adapters.api_football import parse_fixtures

            for fx in parse_fixtures(body):
                if fx.status != "finished":
                    continue
                players = af.cache.get(f"fixtures/players?fixture={fx.id}", forever)
                if players is not MISSING:
                    games += pp.parse_players(players, fx.id, league, season, fx.kickoff_at, fx.home.id)
    print(f"Righe giocatore-partita: {len(games)} in {len({g.fixture_id for g in games})} partite")

    def fit_size(y, mean):
        res = minimize_scalar(lambda ls: -(gammaln(y + math.exp(ls)) - gammaln(math.exp(ls)) - gammaln(y + 1)
                                           + math.exp(ls) * np.log(math.exp(ls) / (math.exp(ls) + mean)) + y * np.log(mean / (math.exp(ls) + mean))).sum(),
                              bounds=(math.log(0.3), math.log(1000)), method="bounded")  # fmt: skip
        return float(math.exp(res.x))

    best = None
    for m in (180, 360, 720, 1440):
        rows = pp.build_player_rows(games, m)
        tune = [r for r in rows if r.season == 2024]
        ys, ms = np.array([r.shots for r in tune], float), np.maximum(np.array([r.mean_shots for r in tune]), 1e-6)
        yo, mo = np.array([r.on_target for r in tune], float), np.maximum(np.array([r.mean_on for r in tune]), 1e-6)
        size_s, size_o = fit_size(ys, ms), fit_size(yo, mo)
        loss = sum(pp.row_log_loss(r, size_s, size_o) for r in tune)
        print(f"   m={m}: log loss taratura {loss / max(len(tune), 1):.4f} per riga (dispersione tiri {size_s:.1f}, in porta {size_o:.1f})")
        if best is None or loss < best[0]:
            best = (loss, m, rows, size_s, size_o)
    _, m, rows, size_s, size_o = best
    tune = [r for r in rows if r.season == 2024]
    conf = [r for r in rows if r.season >= 2025]
    diffs = [pp.row_log_loss(r, size_s, size_o) - pp.row_log_loss(r, None, None, naive=True) for r in conf]
    est = clustered_mean(diffs, [r.fixture_id for r in conf])
    ok = est.mean < -2 * est.std_error
    print(f"\nScelto m={m}. Righe: taratura {len(tune)}, conferma {len(conf)}")
    print(f"Conferma, log loss modello meno confronto: {est.mean:+.4f} ± {est.std_error:.4f} per riga -> {'PASSA' if ok else 'non passa'}")
    print("Calibrazione in conferma, 'almeno 1 tiro' (prevista → vera):")
    bins = [(0, 0.2), (0.2, 0.4), (0.4, 0.6), (0.6, 0.8), (0.8, 1.01)]
    for low, high in bins:
        sel = [(pp.prob_at_least(1, r.mean_shots, size_s), r.shots >= 1) for r in conf]
        sel = [(p, y) for p, y in sel if low <= p < high]
        if sel:
            print(f"   {low:.0%}-{min(high, 1):.0%}: {len(sel)} righe, prevista {sum(p for p, _ in sel) / len(sel):.1%}, vera {sum(y for _, y in sel) / len(sel):.1%}")
    return 0


def _af_stats(seasons: str) -> int:
    """Scarica tiri, angoli, falli e cartellini di squadre e giocatori (Serie A e B) per i modelli dei mercati secondari."""
    from app.adapters.api_football import ApiFootballAdapter
    from app.ingest.af_stats import STATS_LEAGUES, download_match_stats

    settings = get_settings()
    with SessionLocal() as db:
        adapter = ApiFootballAdapter(FileCache(settings.data_cache_dir, "api-football"), settings.api_football_key,
                                     on_call=lambda source: record_usage(db, source), daily_reserve=500)
        report = download_match_stats(adapter, STATS_LEAGUES, [int(x) for x in seasons.split(",")])
    print(f"Partite: {report.fixtures}, scaricate {report.done}, non riuscite {report.failed}" + (f"; fermato: {report.stopped}" if report.stopped else ""))
    return 0


def _af_history() -> int:
    """Storico API-Football per le prove D89 (coppe, allenatori, formazioni di Serie C), poi gli stadi."""
    from app.adapters.api_football import ApiFootballAdapter
    from app.ingest.af_history import download_history

    settings = get_settings()
    with SessionLocal() as db:
        adapter = ApiFootballAdapter(FileCache(settings.data_cache_dir, "api-football"), settings.api_football_key,
                                     on_call=lambda source: record_usage(db, source), daily_reserve=300)
        report = download_history(adapter, seasons=range(2021, 2026), lineup_seasons=range(2022, 2026))
        print(f"Fatto: {report.teams} squadre-stagione, {report.cup_fixtures} partite di coppa, {report.coaches} periodi di allenatori,"
              f" {report.lineups} formazioni. Richieste rimaste oggi: {adapter.remaining_today}")
    if report.stopped is None:
        return _venues()
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
    demo = commands.add_parser("demo-setup", help="avvio dimostrativo: utente demo, storico gratuito e previsioni (Docker)")
    demo.add_argument("--from", dest="first_season", type=int, default=2023, help="prima stagione da scaricare")
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
    commands.add_parser("east-test", help="prova D128 (b): Occasioni nell'Est e nel Nord Europa contro Pinnacle")
    commands.add_parser("minor-test", help="prova D106 (b): Occasioni nelle serie minori contro Pinnacle")
    commands.add_parser("lineup-test", help="prova D123: formazioni previste contro l'ultima formazione")
    commands.add_parser("learning-refresh", help="Archie rifà le prove della Fase 7 e salva i risultati (come il lavoro settimanale)")
    commands.add_parser("review-refresh", help="pagella settimanale di Archie e correzioni automatiche (D132)")
    commands.add_parser("study-refresh", help="Archie studia le partite dei prossimi giorni (D137)")
    det = commands.add_parser("af-details", help="scheda completa delle partite finite da API-Football: xG, giocatori, eventi (D140)")
    det.add_argument("--seasons", default="2022,2023,2024,2025,2026")
    det.add_argument("--leagues", default="", help="id API-Football separati da virgola (vuoto = campionati principali e Serie C)")
    commands.add_parser("timing-test", help="prova D119: quando giocare da Sisal ed Eurobet (archivio OddsPapi)")
    stg = commands.add_parser("strategy-search", help="prova D118: Archie cerca da solo le strategie")
    stg.add_argument("--first", default="2012/13")
    stg.add_argument("--split", default="2020/21", help="prima stagione di conferma")
    stg.add_argument("--last", default="2025/26")
    hsim = commands.add_parser("history-sim", help="simulazione storica di Pronostici, Occasioni e Multipla (D86)")
    hsim.add_argument("--first", default="2021/22")
    hsim.add_argument("--last", default="2025/26", help="stagione di conferma (le precedenti sono la taratura)")
    oa = commands.add_parser("odds-archive", help="salva lo storico quote OddsPapi (angoli, cartellini, principali)")
    oa.add_argument("--since", default="2026-04-01", help="data di inizio, AAAA-MM-GG")
    oa.add_argument("--minor", action="store_true", help="serie minori di tutto il mondo (prova D106)")
    oa.add_argument("--east", action="store_true", help="massime serie dell'Est e del Nord Europa (prova D128)")
    commands.add_parser("seriec-test", help="prova D95: modello di Archie contro i bookmaker italiani in Serie C (copia del DB)")
    commands.add_parser("seriec-edge", help="prova D98: battere il consenso dei bookmaker italiani in Serie C (copia del DB)")
    commands.add_parser("live-check", help="verifica del termometro della speranza sul punteggio all'intervallo (D92)")
    commands.add_parser("secondary-test", help="prova D82 su angoli e cartellini (usare una copia del database)")
    commands.add_parser("d89-test", help="prova del nove dei fattori D89 (riposo, allenatore, sintetico, distanza, assenze)")
    commands.add_parser("style-test", help="prova D108: stili di gioco che si incastrano (angoli, cartellini, tiri)")
    commands.add_parser("player-test", help="prova D110: tiri dei giocatori (dati di API-Football in cache)")
    afs = commands.add_parser("af-stats", help="statistiche di squadre e giocatori da API-Football (Serie A e B)")
    afs.add_argument("--seasons", default="2026,2025,2024")
    commands.add_parser("af-history", help="storico API-Football per le prove dei fattori D89 (coppe, allenatori, formazioni)")
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
    if args.command == "demo-setup":
        return _demo_setup(args.first_season)
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
    if args.command == "east-test":
        return _minor_test("est e nord")
    if args.command == "minor-test":
        return _minor_test()
    if args.command == "lineup-test":
        return _lineup_test()
    if args.command == "learning-refresh":
        from app.forecast.learning_service import refresh_learning

        print(refresh_learning())
        return 0
    if args.command == "af-details":
        from app.ingest.af_detail import download_details
        from app.ingest.venues import LEAGUES as MAIN_LEAGUES

        leagues = [int(x) for x in args.leagues.split(",") if x] or list(MAIN_LEAGUES)
        with SessionLocal() as db:
            report = download_details(api_football_adapter(db, get_settings()), leagues, [int(x) for x in args.seasons.split(",")])
        print(f"partite finite {report.fixtures}, scaricate {report.downloaded} con {report.requests} richieste; stop: {report.stopped}")
        return 0
    if args.command == "study-refresh":
        from datetime import UTC, datetime as dt

        from app.forecast.study_service import refresh_studies

        with SessionLocal() as db:
            print(f"partite studiate: {refresh_studies(db, dt.now(UTC))}")
        return 0
    if args.command == "review-refresh":
        from app.forecast.review_service import refresh_review

        print(refresh_review())
        return 0
    if args.command == "timing-test":
        return _timing_test()
    if args.command == "strategy-search":
        return _strategy_search(args.first, args.split, args.last)
    if args.command == "history-sim":
        return _history_sim(args.first, args.last)
    if args.command == "odds-archive":
        return _odds_archive(args.since, args.minor, args.east)
    if args.command == "seriec-test":
        return _seriec_test()
    if args.command == "seriec-edge":
        return _seriec_edge()
    if args.command == "live-check":
        return _live_check()
    if args.command == "secondary-test":
        return _secondary_test()
    if args.command == "d89-test":
        return _d89_test()
    if args.command == "style-test":
        return _style_test()
    if args.command == "player-test":
        return _player_test()
    if args.command == "af-stats":
        return _af_stats(args.seasons)
    if args.command == "af-history":
        return _af_history()
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
