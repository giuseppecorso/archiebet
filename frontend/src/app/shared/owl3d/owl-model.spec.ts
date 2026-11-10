import { onEllipsoid, seeded } from './owl-model';

describe('gufo 3D: calcoli del modello', () => {
  it('i numeri casuali sono ripetibili e tra 0 e 1', () => {
    const a = seeded(7);
    const b = seeded(7);
    const xs = Array.from({ length: 50 }, () => a());
    expect(Array.from({ length: 50 }, () => b())).toEqual(xs);
    for (const x of xs) {
      expect(x).toBeGreaterThanOrEqual(0);
      expect(x).toBeLessThan(1);
    }
  });

  it('il punto sull ellissoide sta sulla superficie', () => {
    const c: [number, number, number] = [0, -0.05, 0];
    const r: [number, number, number] = [0.8, 0.9, 0.72];
    expect(onEllipsoid(c, r, 0, 0)).toEqual([0, 0.85, 0]); // in cima
    for (const [t, p] of [[0.3, 1.1], [2.5, 0.7], [4, 2]]) {
      const [x, y, z] = onEllipsoid(c, r, t, p);
      expect((x / r[0]) ** 2 + ((y - c[1]) / r[1]) ** 2 + (z / r[2]) ** 2).toBeCloseTo(1, 10);
    }
  });
});
