import { PERIOD_MS, TRAIL_MS, TrailPoint, orbitAt, prune, trailSegments } from './flight';

describe('volo di Archie', () => {
  it('fa un giro intero e torna al punto di partenza', () => {
    const a = orbitAt(1234);
    const b = orbitAt(1234 + PERIOD_MS);
    expect(b.x).toBeCloseTo(a.x, 10);
    expect(b.y).toBeCloseTo(a.y, 10);
  });

  it('davanti nella metà bassa, più grande; dietro nella metà alta, più piccolo', () => {
    const low = orbitAt(PERIOD_MS / 4); // seno = 1
    const high = orbitAt((3 * PERIOD_MS) / 4); // seno = −1
    expect(low.front).toBe(true);
    expect(high.front).toBe(false);
    expect(low.y).toBeGreaterThan(high.y);
    expect(low.scale).toBeCloseTo(1.05, 10);
    expect(high.scale).toBeCloseTo(0.55, 10);
  });

  it('resta dentro la scena', () => {
    for (let t = 0; t < PERIOD_MS; t += 250) {
      const o = orbitAt(t);
      expect(Math.abs(o.x)).toBeLessThanOrEqual(0.41 + 1e-9);
      expect(Math.abs(o.y)).toBeLessThan(0.25);
      expect(Math.abs(o.tilt)).toBeLessThanOrEqual(10 + 1e-9);
    }
  });

  it('si inclina nel verso in cui vola', () => {
    // a un quarto di giro va verso sinistra (x scende): inclinazione negativa
    const before = orbitAt(PERIOD_MS / 4 - 10);
    const after = orbitAt(PERIOD_MS / 4 + 10);
    expect(after.x).toBeLessThan(before.x);
    expect(orbitAt(PERIOD_MS / 4).tilt).toBeLessThan(0);
  });
});

describe('scia d’aria', () => {
  const pt = (t: number, front = true): TrailPoint => ({ x: t, y: 0, t, scale: 1, front });

  it('i tratti più vecchi sono più trasparenti e sottili', () => {
    const segs = trailSegments([pt(0), pt(100), pt(500), pt(900)], 1000);
    expect(segs.length).toBe(3);
    expect(segs[0].opacity).toBeLessThan(segs[2].opacity);
    expect(segs[0].width).toBeLessThan(segs[2].width);
    expect(segs[2].opacity).toBeLessThanOrEqual(0.32);
  });

  it('i tratti scaduti spariscono', () => {
    expect(trailSegments([pt(0), pt(10)], TRAIL_MS + 1)).toEqual([]);
    expect(prune([pt(0), pt(500)], TRAIL_MS + 100).map((p) => p.t)).toEqual([500]);
  });

  it('un tratto è davanti al pallone solo se lo sono entrambi gli estremi', () => {
    const segs = trailSegments([pt(900, true), pt(950, false), pt(990, false)], 1000);
    expect(segs.map((s) => s.front)).toEqual([false, false]);
    expect(trailSegments([pt(900), pt(950)], 1000)[0].front).toBe(true);
  });
});
