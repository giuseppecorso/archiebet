import { httpResource } from '@angular/common/http';
import { Component, computed, effect, input, signal } from '@angular/core';
import { RouterLink } from '@angular/router';
import { FanFact, MatchFan, SOURCE_LABELS, factTone } from '../../core/fan';
import { MatchDetail, OddsRow, TeamSummary } from '../../core/football';
import { dayLabel, fairOdds, kickoffTime, longDate, num, odds, pct } from '../../core/format';
import { LIVE_REFRESH_MS, liveLabel } from '../../core/live';
import { Crest, LeagueLogo } from '../../shared/crest';
import { FormBadges } from '../../shared/form-badges';
import { ShowMore } from '../../shared/show-more';

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
  imports: [RouterLink, FormBadges, ShowMore, Crest, LeagueLogo],
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
