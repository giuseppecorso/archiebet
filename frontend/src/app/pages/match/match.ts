import { httpResource } from '@angular/common/http';
import { Component, computed, input, signal } from '@angular/core';
import { RouterLink } from '@angular/router';
import { MatchDetail, OddsRow, TeamSummary } from '../../core/football';
import { dayLabel, kickoffTime, longDate, num, odds, pct } from '../../core/format';
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

@Component({
  selector: 'ab-match',
  imports: [RouterLink, FormBadges, ShowMore],
  templateUrl: './match.html',
  styleUrl: './match.scss',
})
export class MatchPage {
  /** Dalla rotta /partite/:id */
  readonly id = input.required<string>();

  protected readonly detail = httpResource<MatchDetail>(() => `/api/matches/${this.id()}`);
  protected readonly scope = signal<'season' | 'venue'>('season');
  protected readonly tableOpen = signal(false);

  protected readonly fmt = { odds, num, pct, dayLabel, kickoffTime, longDate };

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

  protected isPlaying(teamId: number): boolean {
    const m = this.detail.value()?.match;
    return !!m && (m.home.id === teamId || m.away.id === teamId);
  }
}
