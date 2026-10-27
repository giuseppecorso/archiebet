"""Lo studio di una partita (D137): probabilità di Archie dai numeri di campo, non dalle quote. Funzioni pure.

1. Modello dei gol: Dixon-Coles con pesi nel tempo (gol attesi di casa e ospite, correzione dei risultati bassi).
2. Primo tempo: per ogni squadra la parte dei suoi gol fatti e subiti nel primo tempo, avvicinata alla media del
   campionato quando le partite sono poche.
3. Probabilità di Archie = probabilità del modello aggiornata con quello che è successo davvero nelle ultime partite in
   casa della squadra di casa e in trasferta dell'ospite (media bayesiana: il modello vale come 192 partite, D141).
   Un pronostico entra solo se modello e campo sono d'accordo.
4. Pronostici per livello (cauto, equilibrato, rischioso), scartando quelli che il campo smentisce, con la spiegazione
   scritta dai numeri.
"""

import math
import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field

from app.forecast.dixon_coles import score_matrix

PRIOR_GAMES = 192  # il modello pesa come 192 partite (prove D140-D141): le ultime 10+10 partite servono a spiegare e a filtrare, quasi non spostano la probabilità
MODEL_TOLERANCE = 0.08  # anche il modello da solo deve stare (quasi) dentro il livello: modello e campo d'accordo
SHARE_PRIOR_GOALS = 20  # quota del primo tempo: la media del campionato pesa come 20 gol
MIN_SAMPLE = 4  # partite minime in casa (o in trasferta) per giudicare
MAX_GOALS = 10

LEVELS = {  # probabilità di Archie per livello
    "cauto": (0.72, 0.93),
    "equilibrato": (0.55, 0.72),
    "rischioso": (0.35, 0.55),
}
CONTRADICTED = 0.15  # il campo smentisce se la frequenza osservata sta sotto la soglia del livello di oltre 15 punti


# --- Mercati studiati: esito come funzione del risultato (finale e del primo tempo) ---

Outcome = Callable[[int, int, int, int], bool]  # gol casa, gol ospite, gol casa 1° tempo, gol ospite 1° tempo


@dataclass(frozen=True)
class MarketDef:
    selections: dict[str, Outcome]
    first_half: bool = False
    second_half: bool = False  # i gol del secondo tempo sono quelli finali meno quelli del primo (D143)


def _over(line: float, get: Callable[[int, int, int, int], int]) -> dict[str, Outcome]:
    return {"over": lambda h, a, x, y: get(h, a, x, y) > line, "under": lambda h, a, x, y: get(h, a, x, y) < line}


MARKETS: dict[str, MarketDef] = {
    "1X2": MarketDef({"1": lambda h, a, x, y: h > a, "X": lambda h, a, x, y: h == a, "2": lambda h, a, x, y: h < a}),
    "DC": MarketDef({"1X": lambda h, a, x, y: h >= a, "X2": lambda h, a, x, y: h <= a, "12": lambda h, a, x, y: h != a}),
    **{f"OU{n}.5": MarketDef(_over(n + 0.5, lambda h, a, x, y: h + a)) for n in (1, 2, 3)},
    "GG": MarketDef({"yes": lambda h, a, x, y: h > 0 and a > 0, "no": lambda h, a, x, y: h == 0 or a == 0}),
    **{f"TGH{n}.5": MarketDef(_over(n + 0.5, lambda h, a, x, y: h)) for n in (0, 1)},
    **{f"TGA{n}.5": MarketDef(_over(n + 0.5, lambda h, a, x, y: a)) for n in (0, 1)},
    **{f"MG{lo}-{hi}": MarketDef({"yes": lambda h, a, x, y, lo=lo, hi=hi: lo <= h + a <= hi}) for lo, hi in ((1, 3), (2, 4), (2, 5))},
    "CB_1X_O1.5": MarketDef({"yes": lambda h, a, x, y: h >= a and h + a > 1.5}),
    "CB_X2_O1.5": MarketDef({"yes": lambda h, a, x, y: h <= a and h + a > 1.5}),
    "CB_1_O1.5": MarketDef({"yes": lambda h, a, x, y: h > a and h + a > 1.5}),
    "CB_2_O1.5": MarketDef({"yes": lambda h, a, x, y: h < a and h + a > 1.5}),
    "CB_1X_U3.5": MarketDef({"yes": lambda h, a, x, y: h >= a and h + a < 3.5}),
    "CB_X2_U3.5": MarketDef({"yes": lambda h, a, x, y: h <= a and h + a < 3.5}),
    "CB_GG_O2.5": MarketDef({"yes": lambda h, a, x, y: h > 0 and a > 0 and h + a > 2.5}),
    **{f"1T_OU{n}.5": MarketDef(_over(n + 0.5, lambda h, a, x, y: x + y), first_half=True) for n in (0, 1)},
    "1T_TGH0.5": MarketDef(_over(0.5, lambda h, a, x, y: x), first_half=True),
    "1T_TGA0.5": MarketDef(_over(0.5, lambda h, a, x, y: y), first_half=True),
    **{f"2T_OU{n}.5": MarketDef(_over(n + 0.5, lambda h, a, x, y: (h - x) + (a - y)), second_half=True) for n in (0, 1)},
    "2T_TGH0.5": MarketDef(_over(0.5, lambda h, a, x, y: h - x), second_half=True),
    "2T_TGA0.5": MarketDef(_over(0.5, lambda h, a, x, y: a - y), second_half=True),
}


def event_text(market: str, selection: str, home: str, away: str) -> str:
    """Il pronostico detto a parole: "il Brescia segna nel primo tempo", "almeno 3 gol", ..."""
    team = home if "TGH" in market else away
    first = " nel primo tempo" if market.startswith("1T_") else " nel secondo tempo" if market.startswith("2T_") else ""
    if market == "1X2":
        return {"1": f"vince {home}", "X": "pareggio", "2": f"vince {away}"}[selection]
    if market == "DC":
        return {"1X": f"{home} non perde", "X2": f"{away} non perde", "12": "non finisce in pareggio"}[selection]
    if market == "GG":
        return "segnano entrambe" if selection == "yes" else "almeno una delle due non segna"
    if market.startswith("MG"):
        lo, hi = market[2:].split("-")
        return f"tra {lo} e {hi} gol in partita"
    if market.startswith("CB_"):
        _, res, goals = market.split("_")
        res_text = {"1X": f"{home} non perde", "X2": f"{away} non perde", "1": f"vince {home}", "2": f"vince {away}", "GG": "segnano entrambe"}[res]
        n = float(goals[1:])
        goal_text = f"almeno {math.ceil(n)} gol" if goals[0] == "O" else f"al massimo {math.floor(n)} gol"
        return f"{res_text} e {goal_text}"
    line = float(re.search(r"(\d+\.5)$", market).group(1))
    if "TG" in market:
        if selection == "over":
            return f"{team} segna{first}" if line == 0.5 else f"{team} segna almeno {math.ceil(line)} gol{first}"
        return f"{team} non segna{first}" if line == 0.5 else f"{team} segna al massimo {math.floor(line)} gol{first}"
    if selection == "over":
        return f"almeno un gol{first}" if line == 0.5 else f"almeno {math.ceil(line)} gol{first}"
    return f"nessun gol{first}" if line == 0.5 else f"al massimo {math.floor(line)} gol{first}"


# --- Probabilità del modello ---

def first_half_share(goals_1h: int, goals: int, league_share: float) -> float:
    """Parte dei gol nel primo tempo, avvicinata alla media del campionato quando i gol sono pochi."""
    return (goals_1h + SHARE_PRIOR_GOALS * league_share) / (goals + SHARE_PRIOR_GOALS)


def model_probabilities(lam: float, mu: float, rho: float, share_home: float, share_away: float) -> dict[str, dict[str, float]]:
    """Probabilità di ogni mercato: partita intera con Dixon-Coles, primo tempo con Poisson sui gol del primo tempo."""
    full = score_matrix(lam, mu, rho, MAX_GOALS)
    full = full / full.sum()
    lam1, mu1 = lam * share_home, mu * share_away
    ph = [math.exp(-lam1) * lam1**i / math.factorial(i) for i in range(MAX_GOALS + 1)]
    pa = [math.exp(-mu1) * mu1**j / math.factorial(j) for j in range(MAX_GOALS + 1)]
    lam2, mu2 = lam - lam1, mu - mu1  # gol attesi nel secondo tempo
    qh = [math.exp(-lam2) * lam2**i / math.factorial(i) for i in range(MAX_GOALS + 1)]
    qa = [math.exp(-mu2) * mu2**j / math.factorial(j) for j in range(MAX_GOALS + 1)]
    out: dict[str, dict[str, float]] = {}
    for name, m in MARKETS.items():
        probs = {}
        for sel, wins in m.selections.items():
            if m.first_half:
                probs[sel] = sum(ph[i] * pa[j] for i in range(MAX_GOALS + 1) for j in range(MAX_GOALS + 1) if wins(0, 0, i, j))
            elif m.second_half:  # gol del secondo tempo come "finale" con primo tempo a zero
                probs[sel] = sum(qh[i] * qa[j] for i in range(MAX_GOALS + 1) for j in range(MAX_GOALS + 1) if wins(i, j, 0, 0))
            else:
                probs[sel] = float(sum(full[i, j] for i in range(MAX_GOALS + 1) for j in range(MAX_GOALS + 1) if wins(i, j, 0, 0)))
        out[name] = probs
    return out


# --- I fatti del campo ---

@dataclass(frozen=True)
class Played:
    """Una partita giocata vista dalla parte della squadra: gol fatti, subiti, fatti e subiti nel primo tempo."""

    scored: int
    conceded: int
    scored_1h: int
    conceded_1h: int


def hits(market: str, selection: str, games: Sequence[Played], as_home: bool) -> int:
    """Quante volte l'esito è uscito: per la squadra di casa le sue partite in casa, per l'ospite quelle in trasferta."""
    wins = MARKETS[market].selections[selection]
    if as_home:
        return sum(wins(g.scored, g.conceded, g.scored_1h, g.conceded_1h) for g in games)
    return sum(wins(g.conceded, g.scored, g.conceded_1h, g.scored_1h) for g in games)


@dataclass(frozen=True)
class Evidence:
    home_hits: int
    home_n: int
    away_hits: int
    away_n: int

    @property
    def n(self) -> int:
        return self.home_n + self.away_n

    @property
    def frequency(self) -> float:
        return (self.home_hits + self.away_hits) / self.n if self.n else 0.0


def archie_probability(p_model: float, ev: Evidence) -> float:
    """Il modello vale come PRIOR_GAMES partite; poi contano i fatti."""
    return (p_model * PRIOR_GAMES + ev.home_hits + ev.away_hits) / (PRIOR_GAMES + ev.n)


# --- Pronostici ---

@dataclass(frozen=True)
class StudyPick:
    market: str
    selection: str
    level: str
    p_model: float
    p_archie: float
    evidence: Evidence
    event: str
    reasons: tuple[str, ...] = field(default=())


def level_of(p: float) -> str | None:
    for name, (lo, hi) in LEVELS.items():
        if lo <= p < hi:
            return name
    return None


def _count(k: int, n: int) -> str:
    return f"{k} su {n}"


def explain(event: str, ev: Evidence, home: str, away: str, p_model: float, p_archie: float) -> tuple[str, ...]:
    return (
        f"«{event[0].upper() + event[1:]}»: è successo in {_count(ev.home_hits, ev.home_n)} partite in casa del {home} "
        f"e in {_count(ev.away_hits, ev.away_n)} in trasferta del {away}.",
        f"Il modello dei gol dà il {p_model:.0%}; con i fatti del campo Archie arriva al {p_archie:.0%}.",
    )


def study_picks(
    probs: dict[str, dict[str, float]], home_games: Sequence[Played], away_games: Sequence[Played], home: str, away: str
) -> list[StudyPick]:
    """Tutti i pronostici sensati della partita, con livello e spiegazione; mai quelli smentiti dal campo."""
    if len(home_games) < MIN_SAMPLE or len(away_games) < MIN_SAMPLE:
        return []
    out = []
    for market, sels in probs.items():
        for sel, p_model in sels.items():
            ev = Evidence(hits(market, sel, home_games, True), len(home_games), hits(market, sel, away_games, False), len(away_games))
            p = archie_probability(p_model, ev)
            level = level_of(p)
            if level is None:
                continue
            floor = LEVELS[level][0]
            if p_model < floor - MODEL_TOLERANCE:
                continue  # solo il campo recente lo sostiene: troppo poco
            # Il campo deve essere d'accordo da tutte e due le parti
            if min(ev.home_hits / ev.home_n, ev.away_hits / ev.away_n) < floor - CONTRADICTED * 2 or ev.frequency < floor - CONTRADICTED:
                continue
            event = event_text(market, sel, home, away)
            out.append(StudyPick(market, sel, level, p_model, p, ev, event, explain(event, ev, home, away, p_model, p)))
    return out


def strength(pick: StudyPick, price: float | None = None) -> float:
    """Ordine dei pronostici di un livello: prima dove lo studio vede più della quota, poi i più solidi."""
    edge = max(0.0, pick.p_archie * price - 1) if price else 0.0
    agreement = 1 - abs(pick.evidence.frequency - pick.p_model)  # modello e campo d'accordo
    return pick.p_archie + 0.5 * edge + 0.1 * agreement + 0.002 * pick.evidence.n


def pick_strength(pick: dict) -> float:
    """Ordine dei pronostici salvati: probabilità di Archie e accordo modello-campo; un poco più su con un tratto per tempo
    coerente, un poco più giù con i segnali di prudenza (D143), compreso il disaccordo con il bookmaker (D145: quando lo
    studio crede più della quota, di solito ha ragione la quota)."""
    hh, hn, ah, an = pick["evidence"]
    frequency = (hh + ah) / (hn + an) if hn + an else 0.0
    return (pick["p_archie"] + 0.1 * (1 - abs(frequency - pick["p_model"])) + 0.002 * (hn + an)
            + TRAIT_BONUS * len(pick.get("traits", [])) - CAUTION_PENALTY * len(pick.get("caution", [])))


def choose_multiple(studies: Sequence[tuple[int, list[dict]]], level: str, n: int, exclude: set[int] = frozenset()) -> list[tuple[int, dict]]:
    """Il pronostico più solido del livello per ogni partita, poi le n partite migliori (una gamba per partita).
    `exclude`: partite già proposte ("genera un'altra multipla")."""
    best = []
    for match_id, picks in studies:
        if match_id in exclude:
            continue
        mine = [p for p in picks if p["level"] == level]
        if mine:
            top = max(mine, key=pick_strength)
            best.append((pick_strength(top), match_id, top))
    best.sort(key=lambda x: x[0], reverse=True)
    return [(match_id, pick) for _, match_id, pick in best[:n]]


# --- Correzioni prudenti dello studio: notizie, motivazione, meteo (D138, non provate sul passato) ---

NEWS_EFFECT = {"netta": 0.06, "lieve": 0.03}  # gol attesi: +x a chi le notizie favoriscono, −x all'altra
MOTIVATION_EFFECT = 0.03  # chi lotta per qualcosa contro chi non ha più obiettivi
MOTIVATION_MIN_PLAYED = 8  # a inizio stagione la classifica non dice ancora niente
BAD_WEATHER = (4.0, 35.0)  # pioggia in mm nelle due ore di gioco, vento medio in km/h
WEATHER_EFFECT = 0.04  # meno gol attesi con pioggia o vento forti


@dataclass(frozen=True)
class Adjustment:
    home: float = 1.0  # moltiplica i gol attesi della squadra di casa
    away: float = 1.0
    reasons: tuple[str, ...] = ()

    def then(self, other: "Adjustment") -> "Adjustment":
        return Adjustment(self.home * other.home, self.away * other.away, self.reasons + other.reasons)


def news_adjustment(side: str, strength: str, reason: str, home: str, away: str) -> Adjustment:
    effect = NEWS_EFFECT.get(strength, 0.0)
    if side not in ("home", "away") or not effect:
        return Adjustment()
    team = home if side == "home" else away
    text = f"Notizie: favoriscono {team} ({strength}). {reason}".strip()
    return Adjustment(1 + effect, 1 - effect, (text,)) if side == "home" else Adjustment(1 - effect, 1 + effect, (text,))


@dataclass(frozen=True)
class TableSpot:
    position: int
    teams: int
    points: int
    played: int
    points_top: int  # punti della seconda in classifica (zona promozione/titolo)
    points_safe: int  # punti della prima squadra fuori dalla zona retrocessione


def goal_of(spot: TableSpot) -> str | None:
    """"vertice", "salvezza", "nessun obiettivo" oppure None (in corsa per qualcosa a metà classifica)."""
    if spot.played < MOTIVATION_MIN_PLAYED:
        return None
    if spot.position <= 2 or spot.points >= spot.points_top - 3:
        return "vertice"
    if spot.points <= spot.points_safe + 3 and spot.position > spot.teams // 2:
        return "salvezza"
    games_left = 2 * (spot.teams - 1) - spot.played
    if spot.points_top - spot.points > 3 * games_left // 2 and spot.points - spot.points_safe > 6:
        return "nessun obiettivo"
    return None


def motivation_adjustment(home_spot: TableSpot | None, away_spot: TableSpot | None, home: str, away: str) -> Adjustment:
    if home_spot is None or away_spot is None:
        return Adjustment()
    gh, ga = goal_of(home_spot), goal_of(away_spot)
    words = {"vertice": "lotta per il vertice", "salvezza": "lotta per la salvezza", "nessun obiettivo": "non ha più obiettivi"}
    parts = [f"{t} {s.position}° con {s.points} punti{' (' + words[g] + ')' if g else ''}" for t, s, g in ((home, home_spot, gh), (away, away_spot, ga))]
    text = "Classifica: " + "; ".join(parts) + "."
    motivated = ("vertice", "salvezza")
    if gh in motivated and ga == "nessun obiettivo":
        return Adjustment(1 + MOTIVATION_EFFECT, 1.0, (text,))
    if ga in motivated and gh == "nessun obiettivo":
        return Adjustment(1.0, 1 + MOTIVATION_EFFECT, (text,))
    return Adjustment(reasons=(text,))


def weather_adjustment(rain_mm: float | None, wind_kmh: float | None) -> Adjustment:
    if rain_mm is None or wind_kmh is None:
        return Adjustment()
    if rain_mm >= BAD_WEATHER[0] or wind_kmh >= BAD_WEATHER[1]:
        what = f"pioggia forte ({rain_mm:.0f} mm)" if rain_mm >= BAD_WEATHER[0] else f"vento forte ({wind_kmh:.0f} km/h)"
        return Adjustment(1 - WEATHER_EFFECT, 1 - WEATHER_EFFECT, (f"Meteo previsto: {what}, di solito si segna un po' meno.",))
    return Adjustment()


# --- Pagella dello studio (D139): i pronostici escono quanto Archie dice? ---


def scorecard(rows: Sequence[tuple[str, str, float, bool]]) -> dict:
    """rows: (settimana, livello, probabilità di Archie, uscito). Per livello e per settimana: proposti, usciti, attesi."""
    def tally(items):
        n = len(items)
        won = sum(1 for *_, hit in items if hit)
        expected = sum(p for _, _, p, _ in items)
        return {"picks": n, "won": won, "expected": round(expected, 2), "hit_rate": round(won / n, 4) if n else None,
                "promised": round(expected / n, 4) if n else None}  # fmt: skip

    levels = {level: tally([r for r in rows if r[1] == level]) for level in LEVELS}
    weeks = sorted({r[0] for r in rows})
    by_week = [{"week": w, **{level: tally([r for r in rows if r[0] == w and r[1] == level]) for level in LEVELS}} for w in weeks]
    return {"levels": levels, "weeks": by_week}


# --- Tratti per tempo e segnali di prudenza (D143) ---

TRAIT_MIN_GOALS = 15  # gol minimi per giudicare un tratto
TRAIT_Z = 2.0  # oltre 2 deviazioni standard dalla media del campionato: difficile che sia il caso
TRAIT_BONUS = 0.02  # nell'ordine: un pronostico sui tempi coerente con un tratto vero sale un poco
CAUTION_PENALTY = 0.03  # nell'ordine: ogni segnale di prudenza sulla squadra favorita fa scendere un poco
BOOK_GAP = 0.05  # lo studio crede almeno 5 punti più della quota: prova D144, di solito ha ragione la quota (D145)


def book_probability(book: dict, market: str, selection: str, bookmakers: Sequence[str]) -> float | None:
    """Probabilità della quota senza margine (proporzionale), media tra i bookmaker che quotano tutto il mercato."""
    sels = MARKETS[market].selections if market in MARKETS else {}
    found = []
    for bm in bookmakers:
        prices = book.get(bm, {}).get(market, {})
        if sels and set(prices) >= set(sels) and all(prices[s] > 1 for s in sels):
            implied = {s: 1 / prices[s] for s in sels}
            total = sum(implied.values())
            found.append(implied[selection] / total)
    return sum(found) / len(found) if found else None


def half_trait(goals_1h: int, goals: int, league_share: float) -> tuple[str, float] | None:
    """("primo" o "secondo", quota del primo tempo) se la squadra si stacca dalla media oltre il caso (test binomiale)."""
    if goals < TRAIT_MIN_GOALS or not 0 < league_share < 1:
        return None
    z = (goals_1h - goals * league_share) / math.sqrt(goals * league_share * (1 - league_share))
    if abs(z) < TRAIT_Z:
        return None
    return ("primo" if z > 0 else "secondo"), goals_1h / goals


def trait_text(team: str, scored: bool, half: str, share: float, league_share: float) -> str:
    verb = "segna" if scored else "subisce"
    mine = share if half == "primo" else 1 - share
    league = league_share if half == "primo" else 1 - league_share
    return f"{team} {verb} soprattutto nel {half} tempo: {mine:.0%} dei gol contro il {league:.0%} del campionato (non è un caso: test statistico)."


def favored_side(market: str, selection: str) -> str | None:
    """Quale squadra deve "fare bene" perché il pronostico esca: "home", "away" o nessuna."""
    home = {("1X2", "1"), ("DC", "1X"), ("CB_1X_O1.5", "yes"), ("CB_1_O1.5", "yes"), ("CB_1X_U3.5", "yes")}
    away = {("1X2", "2"), ("DC", "X2"), ("CB_X2_O1.5", "yes"), ("CB_2_O1.5", "yes"), ("CB_X2_U3.5", "yes")}
    if (market, selection) in home or (market.endswith(("TGH0.5", "TGH1.5")) and selection == "over"):
        return "home"
    if (market, selection) in away or (market.endswith(("TGA0.5", "TGA1.5")) and selection == "over"):
        return "away"
    return None


def half_of(market: str) -> str | None:
    return "primo" if market.startswith("1T_") else "secondo" if market.startswith("2T_") else None


# --- Multiple a tema ---

THEMES = {
    "tutte": "Tutte",
    "primo_tempo": "Solo primo tempo",
    "gol": "Solo gol",
    "maggiori": "Campionati maggiori",
    "minori": "Serie minori",
    "coppe": "Competizioni internazionali",
    "notizie": "Partite con più notizie",
}
GOAL_MARKETS = ("OU", "GG", "TG", "MG")  # Under/Over, Goal/No goal, gol di una squadra, multigol
NEWS_MIN = 3  # "più notizie": almeno 3 notizie sulle due squadre


def theme_market(theme: str, market: str) -> bool:
    """Il mercato rientra nel tema?"""
    if theme == "primo_tempo":
        return market.startswith("1T_")
    if theme == "gol":
        return market.split("_", 1)[-1].startswith(GOAL_MARKETS) if market[:3] in ("1T_", "2T_") else market.startswith(GOAL_MARKETS)
    return True


def theme_match(theme: str, tier: int, cup: bool, news: int) -> bool:
    """La partita rientra nel tema? `tier`: categoria del campionato (1 = massima serie), `news`: notizie raccolte."""
    if theme == "maggiori":
        return tier == 1 and not cup
    if theme == "minori":
        return tier >= 2 and not cup
    if theme == "coppe":
        return cup
    if theme == "notizie":
        return news >= NEWS_MIN
    return True


# --- Quota obiettivo: "voglio una multipla a quota 50" ---


def leg_price(pick: dict) -> float:
    """Quota della gamba: la migliore tra i bookmaker dell'utente, altrimenti la quota giusta dello studio."""
    return max(pick["prices"].values(), default=0.0) or 1 / pick["p_archie"]


def up_to_target(ranked: Sequence[tuple[int, dict]], target: float) -> list[tuple[int, dict]]:
    """Dai pronostici più solidi in giù finché la quota totale arriva all'obiettivo (tutti, se non ci arriva)."""
    out, total = [], 1.0
    for match_id, pick in ranked:
        if total >= target:
            break
        out.append((match_id, pick))
        total *= leg_price(pick)
    return out
