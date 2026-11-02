import { CHART, clvOption, groupsOption, monthLabel, oddsOption, shortDay } from './charts';

type Series = { data: ({ value: number; itemStyle: { color: string } } | number | null)[] }[];

describe('grafici delle statistiche (D170)', () => {
  it('date brevi in italiano', () => {
    expect(shortDay('2026-11-02')).toBe('2 nov');
    expect(monthLabel('2026-10')).toBe('ott 26');
  });

  it('CLV: blu sopra lo zero, rosso sotto', () => {
    const option = clvOption([
      { week: '2026-10-26', avg_clv: 0.03, count: 4 },
      { week: '2026-11-02', avg_clv: -0.02, count: 2 },
    ]);
    const data = (option['series'] as Series)[0].data as { itemStyle: { color: string } }[];
    expect(data.map((d) => d.itemStyle.color)).toEqual([CHART.good, CHART.bad]);
  });

  it('classifica dei gruppi: il primo in cima (ECharts disegna dal basso)', () => {
    const option = groupsOption([
      { label: 'Singole', value: 0.2, n: 10 },
      { label: 'Doppie', value: -0.1, n: 5 },
    ]);
    expect((option['yAxis'] as { data: string[] }).data).toEqual(['Doppie', 'Singole']);
  });

  it('fasce di quota senza selezioni restano fuori', () => {
    const option = oddsOption([
      { label: 'fino a 1,50', selections: 3, won: 2, hit_rate: 0.6667, expected_rate: 0.7 },
      { label: 'oltre 5,00', selections: 0, won: 0, hit_rate: null, expected_rate: null },
    ]);
    expect((option['xAxis'] as { data: string[] }).data).toEqual(['fino a 1,50']);
    expect((option['series'] as Series)[1].data).toEqual([0.7]);
  });
});
