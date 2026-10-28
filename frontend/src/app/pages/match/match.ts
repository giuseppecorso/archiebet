import { AskArchie } from '../../shared/ask-archie';
import { WhyPopup } from '../../shared/why-popup';
import { AuthService } from '../../core/auth.service';
import { StudyLeg } from '../../core/study';
import { OfferButton } from '../../shared/offer-button';
import { HttpClient, HttpErrorResponse, httpResource } from '@angular/common/http';
import { Component, computed, effect, inject, input, signal } from '@angular/core';
import { KeyValuePipe } from '@angular/common';
import { firstValueFrom } from 'rxjs';
import { Market, marketLabel, marketSelections, parseSecondary, parseTeamGoals, pickLabel } from '../../core/bets';
import { MatchAnalysis, MatchNumbers, MatchPicks, PlayerShots, TeamLineup, verdictClass } from '../../core/picks';
import { RouterLink } from '@angular/router';
import { FanFact, MatchFan, SOURCE_LABELS, factTone } from '../../core/fan';
import { MatchDetail, MatchEvent, OddsRow, TeamSummary, scorerList } from '../../core/football';
import { Twins } from '../../core/lab';
import { dayLabel, fairOdds, kickoffTime, longDate, num, odds, pct } from '../../core/format';
import { LIVE_REFRESH_MS, liveLabel } from '../../core/live';
import { Crest, LeagueLogo } from '../../shared/crest';
import { FormBadges } from '../../shared/form-badges';
import { ShowMore } from '../../shared/show-more';
import { MatchEvents } from '../../shared/match-events';

interface StatLine {
  label: string;
  home: string;
  away: string;
  homeWidth: number;
  awayWidth: number;
}

/** Statistiche a confronto: [etichetta, campo, formato] */
const STATS: [string, keyof TeamSummary, 'num' | 'pct'][] = [
  ['Punti a partita', 'points_per_game', 'num'],
  ['Gol fatti (media)', 'goals_for', 'num'],
  ['Gol subiti (media)', 'goals_against', 'num'],
  ['xG creati (media)', 'xg_for', 'num'],
  ['xG concessi (media)', 'xg_against', 'num'],
  ['Tiri a partita', 'shots_for', 'num'],
  ['Tiri in porta', 'shots_on_target_for', 'num'],
  ['Calci d\'angolo', 'corners_for', 'num'],
  ['Porta inviolata', 'clean_sheets', 'pct'],
  ['Over 2.5', 'over_2_5', 'pct'],
  ['Goal (segnano entrambe)', 'both_scored', 'pct'],
];

const MATCH_STATS: [string, string][] = [
  ['Gol', 'goals'],
  ['xG', 'xg'],
  ['Tiri', 'shots'],
  ['Tiri in porta', 'shots_on_target'],
  ['Calci d\'angolo', 'corners'],
  ['Falli', 'fouls'],
  ['Ammonizioni', 'yellow'],
  ['Espulsioni', 'red'],
];

/** Colonne della tabella quote: [mercato, esito] */
const ODDS_COLUMNS: [string, string][] = [
  ['1X2', '1'],
  ['1X2', 'X'],
  ['1X2', '2'],
  ['OU2.5', 'over'],
  ['OU2.5', 'under'],
];

/** Righe della tabella "Tutti i mercati": [nome, mercato, esito] */
const ARCHIE_MARKETS: [string, string, string][] = [
  ['1X (doppia chance)', 'DC', '1X'],
  ['X2 (doppia chance)', 'DC', 'X2'],
  ['12 (doppia chance)', 'DC', '12'],
  ...[0.5, 1.5, 2.5, 3.5, 4.5].flatMap((line): [string, string, string][] => [
    [`Over ${line}`, `OU${line}`, 'over'],
    [`Under ${line}`, `OU${line}`, 'under'],
  ]),
  ['Goal (segnano entrambe)', 'GG', 'yes'],
  ['NoGoal', 'GG', 'no'],
];

@Component({
  selector: 'ab-match',
  imports: [RouterLink, FormBadges, ShowMore, Crest, LeagueLogo, KeyValuePipe, AskArchie, OfferButton, MatchEvents, WhyPopup],
  templateUrl: './match.html',
  styleUrl: './match.scss',
})
export class MatchPage {
  /** Dalla rotta /partite/:id */
  readonly id = input.required<string>();

  protected readonly detail = httpResource<MatchDetail>(() => `/api/matches/${this.id()}`);
  /** Archie tifoso (D102): fatti delle due squadre dalle notizie e giudizio di Archie */
  protected readonly fan = httpResource<MatchFan>(() => `/api/fan/match/${this.id()}`);
  protected readonly factTone = factTone;
  /** I due pronostici (D107) e l'analisi scritta da Archie */
  protected readonly matchPicks = httpResource<MatchPicks>(() => `/api/picks/match/${this.id()}`);
  /** Lo studio della partita (D137): i pronostici migliori per livello, ognuno con il suo perché */
  protected readonly study = httpResource<Record<string, StudyLeg[]>>(() => `/api/study/match/${this.id()}`);
  protected readonly studyLegs = computed(() =>
    (['cauto', 'equilibrato', 'rischioso'] as const).flatMap((level) => {
      const leg = this.study.value()?.[level]?.[0];
      return leg ? [{ level, leg }] : [];
    }),
  );
  /** Angoli e cartellini: lo studio non li calcola, restano le probabilità dalle quote (D131) */
  protected readonly statsSuggestions = computed(() => (this.matchPicks.value()?.suggestions ?? []).filter((s) => /^(COR|CRD)/.test(s.market)));
  /** Marcatori nel tabellone in alto (partita in corso o finita) */
  protected scorers(side: 'home' | 'away'): string {
    return scorerList(this.events.value() ?? undefined, side);
  }
  protected priceList(leg: StudyLeg): [string, number][] {
    return Object.entries(leg.prices);
  }
  protected capital(text: string): string {
    return text.charAt(0).toUpperCase() + text.slice(1);
  }
  protected readonly analysis = httpResource<MatchAnalysis | null>(() => `/api/fan/match/${this.id()}/analysis`);
  /** Multigol e combo: quote giuste ricavate dal mercato (D136, stima) */
  protected readonly derived = httpResource<{ group: string; label: string; probability: number; fair_odds: number }[]>(() => `/api/picks/match/${this.id()}/derived`);

  protected derivedOf(group: string) {
    return (this.derived.value() ?? []).filter((d) => d.group === group).sort((a, b) => b.probability - a.probability);
  }
  /** Tiri, angoli e cartellini attesi (D109) */
  protected readonly numbers = httpResource<MatchNumbers[]>(() => `/api/picks/match/${this.id()}/numbers`);
  protected readonly numbersSide = signal<'totale' | 'casa' | 'ospite'>('totale');
  /** Tiri dei giocatori (D111): i primi 6 per squadra, gli assenti secondo le notizie in fondo */
  protected readonly players = httpResource<PlayerShots[]>(() => `/api/picks/match/${this.id()}/players`);
  protected readonly marketSelections = marketSelections;
  /** Formazioni previste o ufficiali (D123) */
  protected readonly lineups = httpResource<TeamLineup[]>(() => `/api/picks/match/${this.id()}/lineups`);
  protected readonly roleLabels: Record<string, string> = { G: 'Portiere', D: 'Difesa', M: 'Centrocampo', F: 'Attacco' };
  /** Cronaca (D133): gol, cartellini, cambi; si ricarica con la partita mentre è in corso */
  protected readonly events = httpResource<MatchEvent[]>(() => {
    const m = this.detail.value()?.match;
    return m && (m.status === 'finished' || m.live) ? `/api/matches/${this.id()}/events?t=${m.live ? `${m.live.minute}-${m.live.home_goals}-${m.live.away_goals}` : 'fine'}` : undefined;
  });
  /** Partite gemelle (D121): le 100 partite passate più simili e come sono finite */
  protected readonly twins = httpResource<Twins>(() => `/api/lab/twins/${this.id()}`);
  protected readonly playersBySide = computed(() => {
    const all = this.players.value() ?? [];
    const pick = (side: 'casa' | 'ospite') => {
      const list = all.filter((p) => p.side === side);
      return [...list.filter((p) => !p.absent).slice(0, 6), ...list.filter((p) => p.absent)];
    };
    return [pick('casa'), pick('ospite')];
  });
  protected readonly writing = signal(false);
  protected readonly analysisError = signal<string | null>(null);
  protected readonly verdictClass = verdictClass;
  private readonly http = inject(HttpClient);
  /** Scrivere l'analisi usa l'AI: solo l'amministratore (gli amici leggono quelle già scritte) */
  private readonly auth = inject(AuthService);
  protected readonly admin = computed(() => !!this.auth.user()?.is_admin);

  /** La pagina è divisa in tre schede: si vede una sola parte alla volta */
  protected readonly tabs = [
    { key: 'pronostici', label: 'Pronostici' },
    { key: 'numeri', label: 'Numeri' },
    { key: 'squadre', label: 'Squadre' },
  ] as const;
  protected readonly tab = signal<'pronostici' | 'numeri' | 'squadre'>('pronostici');

  /** Giocate raggruppate per tipo, una tendina sceglie quale gruppo vedere */
  protected readonly playGroups = computed(() => [...new Set((this.matchPicks.value()?.markets ?? []).map((mk) => playGroupOf(mk.market)))]);
  private readonly chosenGroup = signal<string | null>(null);
  protected readonly playGroup = computed(() => {
    const groups = this.playGroups();
    const g = this.chosenGroup();
    return g && groups.includes(g) ? g : (groups[0] ?? '');
  });
  protected readonly shownMarkets = computed(() => {
    const shown = (this.matchPicks.value()?.markets ?? []).filter((mk) => playGroupOf(mk.market) === this.playGroup());
    if (!['Multigol', 'Combo'].includes(this.playGroup())) return shown;
    return [...shown].sort((a, b) => (b.probabilities['yes'] ?? 0) - (a.probabilities['yes'] ?? 0)).slice(0, 3); // solo le 3 più probabili
  });

  protected pickGroup(g: string): void {
    this.chosenGroup.set(g);
  }

  protected marketName(market: string): string {
    return marketLabel(market, this.detail.value()?.match);
  }

  protected pickName(market: string, selection: string): string {
    return pickLabel(market as Market, selection, this.detail.value()?.match);
  }

  /** Chiede ad Archie di scrivere (o aggiornare) l'analisi: ~0,03 €, al massimo una ogni 3 ore per partita */
  protected async writeAnalysis(): Promise<void> {
    this.writing.set(true);
    this.analysisError.set(null);
    try {
      const out = await firstValueFrom(this.http.post<MatchAnalysis>(`/api/fan/match/${this.id()}/analysis`, {}));
      this.analysis.set(out);
    } catch (e) {
      const detail = e instanceof HttpErrorResponse ? e.error?.detail : null;
      this.analysisError.set(typeof detail === 'string' ? detail : 'Analisi non riuscita: riprova tra poco.');
    } finally {
      this.writing.set(false);
    }
  }
  protected readonly sourceLabels = SOURCE_LABELS;

  /** I fatti divisi per squadra: [casa, ospite] */
  protected readonly fanFacts = computed<[FanFact[], FanFact[]]>(() => {
    const d = this.detail.value();
    const facts = this.fan.value()?.facts ?? [];
    if (!d) return [[], []];
    return [facts.filter((f) => f.team_id === d.match.home.id), facts.filter((f) => f.team_id === d.match.away.id)];
  });

  constructor() {
    // A partita in corso minuto, punteggio e probabilità si aggiornano da soli ogni 30 secondi
    effect((onCleanup) => {
      if (!this.detail.value()?.match.live) return;
      const timer = setInterval(() => this.detail.reload(), LIVE_REFRESH_MS);
      onCleanup(() => clearInterval(timer));
    });
  }
  protected readonly scope = signal<'season' | 'venue'>('season');
  protected readonly tableOpen = signal(false);

  protected readonly fmt = { odds, num, pct, fairOdds, dayLabel, kickoffTime, longDate, liveLabel };

  /** Le tre schede 1 / X / 2 di Archie, con la probabilità del mercato accanto */
  protected readonly archieCards = computed(() => {
    const d = this.detail.value();
    const p = d?.prediction;
    if (!d || !p) return [];
    const market = p.market['1X2']?.probabilities;
    const names: [string, string][] = [['1', d.match.home.name], ['X', 'Pareggio'], ['2', d.match.away.name]];
    return names.map(([sel, name]) => ({
      sel,
      name,
      pct: pct(p.markets['1X2'][sel]),
      fair: fairOdds(p.markets['1X2'][sel]),
      market: market ? pct(market[sel]) : null,
    }));
  });

  /** Tutti gli altri mercati: probabilità e quota giusta di Archie, mercato dove c'è */
  protected readonly archieMarkets = computed(() => {
    const p = this.detail.value()?.prediction;
    if (!p) return [];
    return ARCHIE_MARKETS.filter(([, market, sel]) => p.markets[market]?.[sel] != null).map(([label, market, sel]) => ({
      label,
      pct: pct(p.markets[market][sel]),
      fair: fairOdds(p.markets[market][sel]),
      market: p.market[market] ? pct(p.market[market].probabilities[sel]) : null,
    }));
  });

  protected readonly stats = computed<StatLine[]>(() => {
    const d = this.detail.value();
    if (!d) return [];
    const home = d.home[this.scope()];
    const away = d.away[this.scope()];
    return STATS.map(([label, key, kind]) => {
      const h = home[key] ?? null;
      const a = away[key] ?? null;
      const max = Math.max(h ?? 0, a ?? 0) || 1;
      const show = (v: number | null) => (kind === 'pct' ? pct(v) : num(v));
      return { label, home: show(h), away: show(a), homeWidth: ((h ?? 0) / max) * 100, awayWidth: ((a ?? 0) / max) * 100 };
    });
  });

  protected readonly matchStats = computed(() => {
    const s = this.detail.value()?.match_stats;
    if (!s) return [];
    return MATCH_STATS.filter(([, key]) => s[key]?.some((v) => v != null)).map(([label, key]) => ({
      label,
      home: num(s[key][0]),
      away: num(s[key][1]),
    }));
  });

  /** Una riga per bookmaker: 1, X, 2, Over 2.5, Under 2.5, ognuna con apertura e chiusura */
  protected readonly oddsRows = computed(() => {
    const byBook = new Map<string, { label: string; markets: Record<string, OddsRow> }>();
    for (const o of this.detail.value()?.odds ?? []) {
      const row = byBook.get(o.bookmaker) ?? { label: o.label, markets: {} };
      row.markets[o.market] = o;
      byBook.set(o.bookmaker, row);
    }
    return [...byBook.values()].map(({ label, markets }) => ({
      label,
      cells: ODDS_COLUMNS.map(([market, sel]) => ({
        open: markets[market]?.opening[sel] ?? null,
        close: markets[market]?.closing[sel] ?? null,
      })),
    }));
  });

  protected outcomes(side: 'home' | 'away') {
    return this.detail.value()?.[side].form.map((f) => f.outcome) ?? [];
  }

  /** Classifica ridotta: prime 10 righe più le due squadre in campo, ovunque siano */
  protected readonly standingsRows = computed(() => {
    const rows = this.detail.value()?.standings ?? [];
    return this.tableOpen() ? rows : rows.filter((row) => row.rank <= 10 || this.isPlaying(row.team.id));
  });

  /** Si può ancora giocare: in programma e non iniziata */
  protected isUpcoming(): boolean {
    const m = this.detail.value()?.match;
    return !!m && m.status === 'scheduled' && new Date(m.kickoff_at).getTime() > Date.now();
  }

  protected isPlaying(teamId: number): boolean {
    const m = this.detail.value()?.match;
    return !!m && (m.home.id === teamId || m.away.id === teamId);
  }
}

/** Tipo di giocata per la tendina di «Gioca questa partita» */
export function playGroupOf(market: string): string {
  if (market.startsWith('1T_') || market.startsWith('2T_')) return 'Primo e secondo tempo';
  if (market.startsWith('OU')) return 'Under / Over';
  if (market === 'GG') return 'Goal / No goal';
  if (market.startsWith('MG')) return 'Multigol';
  if (market.startsWith('CB_')) return 'Combo';
  if (parseTeamGoals(market)) return 'Gol delle squadre';
  if (parseSecondary(market)) return 'Angoli e cartellini';
  return 'Esito finale';
}
