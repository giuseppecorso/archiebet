import { atLeast, systemRows } from './strategies';

describe('strategie: sistemi', () => {
  it('almeno k giuste: casi semplici', () => {
    expect(atLeast([0.5, 0.5], 0)).toBeCloseTo(1, 12);
    expect(atLeast([0.5, 0.5], 1)).toBeCloseTo(0.75, 12);
    expect(atLeast([0.5, 0.5], 2)).toBeCloseTo(0.25, 12);
    expect(atLeast([0.6, 0.7, 0.8], 3)).toBeCloseTo(0.6 * 0.7 * 0.8, 12);
    // 2 su 3: tutte e tre + esattamente due
    const two = 0.6 * 0.7 * 0.2 + 0.6 * 0.3 * 0.8 + 0.4 * 0.7 * 0.8 + 0.6 * 0.7 * 0.8;
    expect(atLeast([0.6, 0.7, 0.8], 2)).toBeCloseTo(two, 12);
  });

  it('i sistemi vanno da 2 su n alla multipla secca', () => {
    const legs = [
      { p: 0.6, odds: 1.6 },
      { p: 0.7, odds: 1.4 },
      { p: 0.5, odds: 2.0 },
    ];
    const rows = systemRows(legs, 10);
    expect(rows.map((r) => r.k)).toEqual([2, 3]);
    const [two, three] = rows;
    expect(two.combos).toBe(3);
    expect(two.perBet).toBeCloseTo(3.33, 2);
    // con 2 giuste vince almeno la coppia con le quote più basse: 10/3 × 1,4 × 1,6
    expect(two.min).toBeCloseTo((10 / 3) * 1.4 * 1.6, 2);
    expect(three.combos).toBe(1);
    expect(three.max).toBeCloseTo(10 * 1.6 * 1.4 * 2.0, 2);
    expect(three.pWin).toBeCloseTo(0.6 * 0.7 * 0.5, 12);
    expect(two.pWin).toBeGreaterThan(three.pWin); // il sistema vince più spesso, ma meno
  });
});
