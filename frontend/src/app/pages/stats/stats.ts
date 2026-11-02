import { Subnav } from '../../shared/subnav';
import { MIO_ARCHIE_TABS } from '../../core/sections';
import { RulesPanel } from '../../shared/rules-panel';
import { httpResource } from '@angular/common/http';
import { Component, computed, signal } from '@angular/core';
import { RouterLink } from '@angular/router';
import { BetGroup, BetSummary, Breakdown, SelectionGroup, SummaryOut, Versus, VersusGroup, euro } from '../../core/bets';
import { num, pct } from '../../core/format';
import { ShowMore } from '../../shared/show-more';
import { Chart } from '../../shared/chart';
import { GroupBar, Trends, balanceOption, clvOption, groupsOption, monthsOption, oddsOption } from '../../core/charts';

type Period = SummaryOut['period'];
type Dim = 'by_size' | 'by_market' | 'by_competition' | 'by_bookmaker';

/** Le mie statistiche: riepilogo, grafici dell'andamento (D170), dove vinci e dove perdi, tu contro Archie, abitudini. */
@Component({
  selector: 'ab-stats',
  imports: [RouterLink, ShowMore, RulesPanel, Subnav, Chart],
  templateUrl: './stats.html',
  styleUrl: './stats.scss',
})
export class Stats {
  protected readonly tabs = MIO_ARCHIE_TABS;
  protected readonly periods: [Period, string][] = [
    ['week', 'Settimana'],
    ['30d', 'Ultimi 30 giorni'],
    ['season', 'Stagione'],
    ['all', 'Sempre'],
  ];
  protected readonly period = signal<Period>('all');
  protected readonly summary = httpResource<SummaryOut>(() => `/api/bets/summary?period=${this.period()}`);

  /** Dove vinci e dove perdi */
  protected readonly dims: [Dim, string][] = [
    ['by_size', 'Numero di partite'],
    ['by_market', 'Mercato'],
    ['by_competition', 'Campionato'],
    ['by_bookmaker', 'Bookmaker'],
  ];
  protected readonly dim = signal<Dim>('by_size');
  protected readonly groupsOpen = signal(false);
  protected readonly breakdown = httpResource<Breakdown>(() => `/api/bets/breakdown?period=${this.period()}`);
  protected readonly versus = httpResource<Versus>(() => `/api/bets/versus?period=${this.period()}`);

  /** Numero di partite e bookmaker guardano la schedina intera; mercato e campionato le singole selezioni */
  protected readonly betRows = computed<BetGroup[] | null>(() => {
    const bd = this.breakdown.value();
    const d = this.dim();
    return bd && (d === 'by_size' || d === 'by_bookmaker') ? bd[d] : null;
  });
  protected readonly selectionRows = computed<SelectionGroup[] | null>(() => {
    const bd = this.breakdown.value();
    const d = this.dim();
    return bd && (d === 'by_market' || d === 'by_competition') ? bd[d] : null;
  });

  /** Grafici (D170): le opzioni si ricalcolano quando cambiano periodo o raggruppamento */
  protected readonly trends = httpResource<Trends>(() => `/api/bets/trends?period=${this.period()}`);
  protected readonly balanceChart = computed(() => balanceOption(this.trends.value()?.days ?? []));
  protected readonly monthsChart = computed(() => monthsOption(this.trends.value()?.months ?? []));
  protected readonly clvChart = computed(() => clvOption(this.trends.value()?.clv_weeks ?? []));
  protected readonly oddsChart = computed(() => oddsOption(this.trends.value()?.odds_bands ?? []));
  protected readonly hasOddsBands = computed(() => (this.trends.value()?.odds_bands ?? []).some((b) => b.selections > 0));
  /** I primi 8 gruppi (i più giocati) per rendimento: schedine intere o selezioni come singole */
  protected readonly groupBars = computed<GroupBar[]>(() => {
    const bets = this.betRows()?.map((g) => ({ label: g.label, value: g.roi ?? 0, n: g.bets }));
    const sels = this.selectionRows()?.map((g) => ({ label: g.label, value: g.flat_roi ?? 0, n: g.selections }));
    return (bets ?? sels ?? []).slice(0, 8).sort((a, b) => b.value - a.value);
  });
  protected readonly groupsChart = computed(() => groupsOption(this.groupBars()));
  protected readonly filtered = computed(() => this.period() !== 'all' || this.dim() !== 'by_size');

  protected readonly fmt = { euro, pct, num };

  protected resetFilters(): void {
    this.period.set('all');
    this.setDim('by_size');
  }

  protected setDim(d: Dim): void {
    this.dim.set(d);
    this.groupsOpen.set(false);
  }

  protected sign(value: string | number | null): 'pos' | 'neg' | '' {
    const n = Number(value ?? 0);
    return n > 0 ? 'pos' : n < 0 ? 'neg' : '';
  }

  /** Rendimento e CLV come percentuali con segno: 0.1 → "+10,0%" */
  protected signedPct(value: number | null): string {
    if (value == null) return '–';
    const p = value * 100;
    return `${p > 0 ? '+' : p < 0 ? '−' : ''}${Math.abs(p).toLocaleString('it-IT', { minimumFractionDigits: 1, maximumFractionDigits: 1 })}%`;
  }

  /** Verdetto sul fiuto: conta solo se la differenza supera due errori standard (come per il radar) */
  protected skillVerdict(v: Versus): string {
    if (v.skill == null || v.skill_std_error == null) return '';
    if (v.judged < 30) return 'Servono almeno 30 selezioni chiuse per dire qualcosa.';
    if (v.skill > 2 * v.skill_std_error) return 'Vinci più spesso di quanto Archie si aspettava: il tuo fiuto aggiunge qualcosa.';
    if (v.skill < -2 * v.skill_std_error) return 'Vinci meno spesso di quanto Archie si aspettava: fidati di più delle probabilità.';
    return 'In linea con Archie: la differenza è dentro il caso.';
  }

  protected versusRows(v: Versus): [string, string, VersusGroup | null][] {
    return [
      ["Archie d'accordo", 'aveva valore alla tua quota', v.agreed],
      ['Archie contrario', "non l'avrebbe giocata", v.disagreed],
    ];
  }

  protected cards(s: SummaryOut): [string, string, BetSummary][] {
    return [['Le tue giocate', 'tutte quelle registrate', s.total]];
  }
}
