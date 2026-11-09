import { lineup, rowSizes } from './lineup';

describe('formazione della bacheca', () => {
  it('nessuna giocata, nessun giocatore', () => {
    expect(lineup(0)).toEqual([]);
  });

  it('una giocata sola è il portiere', () => {
    expect(lineup(1)).toEqual([{ x: 50, y: 88 }]);
  });

  it('undici giocate: portiere e linee 4-3-3', () => {
    expect(rowSizes(11)).toEqual([4, 3, 3]);
    expect(lineup(11).length).toBe(11);
  });

  it('linee da 4 al massimo, le più piene dietro', () => {
    for (let n = 1; n <= 30; n++) {
      const sizes = rowSizes(n);
      expect(sizes.reduce((a, b) => a + b, 0)).toBe(n - 1);
      expect(Math.max(0, ...sizes)).toBeLessThanOrEqual(4);
      expect([...sizes].sort((a, b) => b - a)).toEqual(sizes);
    }
  });

  it('tutti dentro il campo e nessuno sovrapposto', () => {
    for (let n = 1; n <= 30; n++) {
      const spots = lineup(n);
      expect(spots.length).toBe(n);
      expect(new Set(spots.map((s) => `${s.x.toFixed(2)}|${s.y.toFixed(2)}`)).size).toBe(n);
      for (const s of spots) {
        expect(s.x).toBeGreaterThan(5);
        expect(s.x).toBeLessThan(95);
        expect(s.y).toBeGreaterThan(5);
        expect(s.y).toBeLessThan(95);
      }
    }
  });

  it('la difesa sta dietro, l’attacco davanti', () => {
    const spots = lineup(11);
    expect(spots[1].y).toBe(68);
    expect(spots[10].y).toBe(14);
  });
});
