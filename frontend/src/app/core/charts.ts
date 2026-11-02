/**
 * Le impostazioni dei grafici delle statistiche (D170): colori, testi, griglia, tooltip e un costruttore per grafico.
 * Funzioni pure: ricevono i dati del server e restituiscono le opzioni di ECharts.
 *
 * Colori validati per il fondo scuro dei pannelli (#0d1e15): blu e rosso restano distinguibili anche per chi non vede
 * bene rosso e verde (per questo "vinte" è blu e non verde come nel resto dell'app); l'ambra è "quello che dice la quota".
 * Il colore non è mai l'unico segnale: legenda, etichette e tooltip dicono sempre cosa si guarda.
 */
import type { EChartsCoreOption } from 'echarts/core';
import { euro } from './bets';
import { pct, signedPct } from './format';

export const CHART = {
  good: '#2f9fd9',
  bad: '#e5534b',
  quote: '#bf8800',
  surface: '#0d1e15',
  text: '#f2f5f1',
  muted: '#93a99a',
  grid: '#19301f',
  axis: '#2b5039',
  font: "'Barlow', system-ui, sans-serif",
};

export interface DayPoint {
  day: string;
  bets: number;
  won: number;
  profit: string;
  cum_profit: string;
}
export interface MonthPoint {
  month: string;
  won: number;
  lost: number;
}
export interface WeekClv {
  week: string;
  avg_clv: number;
  count: number;
}
export interface OddsBand {
  label: string;
  selections: number;
  won: number;
  hit_rate: number | null;
  expected_rate: number | null;
}
export interface Trends {
  days: DayPoint[];
  months: MonthPoint[];
  clv_weeks: WeekClv[];
  odds_bands: OddsBand[];
}

/** Una barra di "dove vinci e dove perdi": gruppo, rendimento e quante giocate ci sono dietro */
export interface GroupBar {
  label: string;
  value: number;
  n: number;
}

const MONTHS = ['gen', 'feb', 'mar', 'apr', 'mag', 'giu', 'lug', 'ago', 'set', 'ott', 'nov', 'dic'];

export function shortDay(iso: string): string {
  const [, m, d] = iso.split('-');
  return `${+d} ${MONTHS[+m - 1]}`;
}

export function monthLabel(month: string): string {
  const [y, m] = month.split('-');
  return `${MONTHS[+m - 1]} ${y.slice(2)}`;
}

const axisLabel = { color: CHART.muted, fontFamily: CHART.font, fontSize: 11 };
const splitLine = { lineStyle: { color: CHART.grid, width: 1 } };
const axisLine = { lineStyle: { color: CHART.axis } };

function base(): EChartsCoreOption {
  return {
    backgroundColor: 'transparent',
    animationDuration: 400,
    textStyle: { fontFamily: CHART.font, color: CHART.text },
    grid: { left: 8, right: 12, top: 28, bottom: 8, containLabel: true },
    tooltip: {
      backgroundColor: '#0b1a12',
      borderColor: CHART.axis,
      textStyle: { color: CHART.text, fontFamily: CHART.font, fontSize: 13 },
      confine: true,
    },
  };
}

function legend(names: string[]): EChartsCoreOption['legend'] {
  return { data: names, top: 0, left: 0, icon: 'roundRect', itemWidth: 12, itemHeight: 8, textStyle: { color: CHART.text, fontSize: 12 } };
}

function percentAxis(): object {
  return { type: 'value', axisLabel: { ...axisLabel, formatter: (v: number) => `${Math.round(v * 100)}%` }, splitLine };
}

/** Il saldo dall'inizio del periodo, giorno per giorno (una sola linea: niente legenda, il titolo dice cos'è) */
export function balanceOption(days: DayPoint[]): EChartsCoreOption {
  return {
    ...base(),
    grid: { left: 8, right: 12, top: 12, bottom: 8, containLabel: true },
    tooltip: {
      ...(base()['tooltip'] as object),
      trigger: 'axis',
      axisPointer: { type: 'line', lineStyle: { color: CHART.muted } },
      formatter: (items: { dataIndex: number }[]) => {
        const d = days[items[0].dataIndex];
        return `<b>${shortDay(d.day)}</b><br>Saldo: <b>${euro(d.cum_profit, true)}</b><br>Quel giorno: ${euro(d.profit, true)} · ${d.won} vinte su ${d.bets}`;
      },
    },
    xAxis: { type: 'category', data: days.map((d) => shortDay(d.day)), boundaryGap: false, axisLabel, axisLine, axisTick: { show: false } },
    yAxis: { type: 'value', axisLabel: { ...axisLabel, formatter: (v: number) => `${v} €` }, splitLine },
    series: [
      {
        type: 'line',
        name: 'Saldo',
        data: days.map((d) => +d.cum_profit),
        lineStyle: { width: 2, color: CHART.good },
        itemStyle: { color: CHART.good, borderColor: CHART.surface, borderWidth: 2 },
        symbolSize: days.length > 40 ? 0 : 8,
        areaStyle: { color: CHART.good, opacity: 0.12 },
        markLine: { silent: true, symbol: 'none', label: { show: false }, lineStyle: { color: CHART.muted, type: 'solid', width: 1 }, data: [{ yAxis: 0 }] },
      },
    ],
  };
}

/** Schedine vinte e perse per mese, impilate */
export function monthsOption(months: MonthPoint[]): EChartsCoreOption {
  const bar = (name: string, color: string, data: number[], top: boolean) => ({
    type: 'bar',
    name,
    stack: 'esito',
    data,
    barMaxWidth: 28,
    itemStyle: { color, borderColor: CHART.surface, borderWidth: 1, borderRadius: top ? [4, 4, 0, 0] : 0 },
  });
  return {
    ...base(),
    legend: legend(['Vinte', 'Perse']),
    tooltip: { ...(base()['tooltip'] as object), trigger: 'axis', axisPointer: { type: 'shadow', shadowStyle: { color: 'rgba(255,255,255,0.04)' } } },
    xAxis: { type: 'category', data: months.map((m) => monthLabel(m.month)), axisLabel, axisLine, axisTick: { show: false } },
    yAxis: { type: 'value', minInterval: 1, axisLabel, splitLine },
    series: [bar('Vinte', CHART.good, months.map((m) => m.won), false), bar('Perse', CHART.bad, months.map((m) => m.lost), true)],
  };
}

/** Barre che partono da zero: blu sopra (bene), rosso sotto (male) */
function signedBars(values: number[]): object[] {
  return values.map((v) => ({
    value: v,
    itemStyle: { color: v >= 0 ? CHART.good : CHART.bad, borderRadius: v >= 0 ? [4, 4, 0, 0] : [0, 0, 4, 4] },
  }));
}

/** CLV medio di ogni settimana */
export function clvOption(weeks: WeekClv[]): EChartsCoreOption {
  return {
    ...base(),
    grid: { left: 8, right: 12, top: 12, bottom: 8, containLabel: true },
    tooltip: {
      ...(base()['tooltip'] as object),
      trigger: 'axis',
      axisPointer: { type: 'shadow', shadowStyle: { color: 'rgba(255,255,255,0.04)' } },
      formatter: (items: { dataIndex: number }[]) => {
        const w = weeks[items[0].dataIndex];
        return `<b>Settimana del ${shortDay(w.week)}</b><br>CLV medio: <b>${signedPct(w.avg_clv)}</b><br>su ${w.count} selezioni`;
      },
    },
    xAxis: { type: 'category', data: weeks.map((w) => shortDay(w.week)), axisLabel, axisLine, axisTick: { show: false } },
    yAxis: percentAxis(),
    series: [{ type: 'bar', name: 'CLV medio', data: signedBars(weeks.map((w) => w.avg_clv)), barMaxWidth: 28 }],
  };
}

/** Per fascia di quota: quanto azzecchi (barre) contro quanto promette la quota (trattino ambra) */
export function oddsOption(bands: OddsBand[]): EChartsCoreOption {
  const shown = bands.filter((b) => b.selections > 0);
  return {
    ...base(),
    legend: legend(['Azzeccate', 'Promesse dalla quota']),
    tooltip: {
      ...(base()['tooltip'] as object),
      trigger: 'axis',
      axisPointer: { type: 'shadow', shadowStyle: { color: 'rgba(255,255,255,0.04)' } },
      formatter: (items: { dataIndex: number }[]) => {
        const b = shown[items[0].dataIndex];
        return `<b>Quote ${b.label}</b><br>Azzeccate: <b>${pct(b.hit_rate)}</b> (${b.won} su ${b.selections})<br>Promesse dalla quota: ${pct(b.expected_rate)}`;
      },
    },
    xAxis: { type: 'category', data: shown.map((b) => b.label), axisLabel: { ...axisLabel, interval: 0, hideOverlap: true }, axisLine, axisTick: { show: false } },
    yAxis: { ...percentAxis(), max: 1 },
    series: [
      { type: 'bar', name: 'Azzeccate', data: shown.map((b) => b.hit_rate), barMaxWidth: 36, itemStyle: { color: CHART.good, borderRadius: [4, 4, 0, 0] } },
      {
        type: 'scatter',
        name: 'Promesse dalla quota',
        data: shown.map((b) => b.expected_rate),
        symbol: 'rect',
        symbolSize: [46, 3],
        itemStyle: { color: CHART.quote },
        z: 3,
      },
    ],
  };
}

/** Classifica orizzontale dei gruppi per rendimento, con la percentuale in fondo alla barra */
export function groupsOption(groups: GroupBar[]): EChartsCoreOption {
  const rows = [...groups].reverse(); // ECharts disegna dal basso: il primo gruppo va in cima
  return {
    ...base(),
    grid: { left: 8, right: 56, top: 4, bottom: 4, containLabel: true },
    tooltip: {
      ...(base()['tooltip'] as object),
      trigger: 'item',
      formatter: (item: { dataIndex: number }) => {
        const g = rows[item.dataIndex];
        return `<b>${g.label}</b><br>Rendimento: <b>${signedPct(g.value)}</b><br>su ${g.n} giocate chiuse`;
      },
    },
    xAxis: { type: 'value', axisLabel: { ...axisLabel, formatter: (v: number) => `${Math.round(v * 100)}%` }, splitLine },
    yAxis: { type: 'category', data: rows.map((g) => g.label), axisLabel: { ...axisLabel, color: CHART.text, width: 110, overflow: 'truncate' }, axisLine, axisTick: { show: false } },
    series: [
      {
        type: 'bar',
        data: rows.map((g) => ({
          value: g.value,
          itemStyle: { color: g.value >= 0 ? CHART.good : CHART.bad, borderRadius: g.value >= 0 ? [0, 4, 4, 0] : [4, 0, 0, 4] },
        })),
        barMaxWidth: 18,
        label: { show: true, position: 'right', color: CHART.text, fontSize: 11, formatter: (p: { value: number }) => signedPct(p.value) },
      },
    ],
  };
}
