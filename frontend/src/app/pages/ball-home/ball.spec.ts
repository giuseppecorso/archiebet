import { DailyLeg, DailySlip } from '../../core/daily';
import { BALL_MENU, FACES, HEXAGONS, PENTAGONS, Vec3, dot, faceAt, freshWins, legKey, patchAt, pentagonCorners, uniqueLegs } from './ball';

const leg = (match_id: number, status: DailyLeg['status'], selection = 'over'): DailyLeg => ({
  match_id, kickoff_at: '2026-11-09T20:45:00Z', competition: 'Serie A', home: 'Como', away: 'Cagliari',
  market: 'OU2.5', selection, event: 'Più di 2,5 gol', p: 0.55, price: 1.8, status,
}); // prettier-ignore

const slip = (legs: DailyLeg[]): DailySlip =>
  ({ id: 1, kind: 'giorno', title: 'Del giorno', period: '2026-11-09', published_at: '', singles: false, legs, total_odds: 1, win_probability: 0.5, status: 'open' });

/** Punto sulla linea fra due centri: t = 0 è il primo, t = 1 il secondo. */
const between = (a: Vec3, b: Vec3, t: number): Vec3 => [a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t, a[2] + (b[2] - a[2]) * t];

describe('pallone classico', () => {
  it('ha 12 toppe nere e 20 bianche, tutte sulla sfera', () => {
    expect(PENTAGONS.length).toBe(12);
    expect(HEXAGONS.length).toBe(20);
    for (const f of FACES) expect(Math.hypot(...f)).toBeCloseTo(1, 9);
  });

  it('ogni voce del menù ha la sua toppa nera', () => {
    expect(BALL_MENU.length).toBe(PENTAGONS.length);
    expect(new Set(BALL_MENU.map((e) => e.label)).size).toBe(12);
  });

  it('il centro di una toppa cade su quella toppa', () => {
    PENTAGONS.forEach((c, i) => expect(patchAt(c)).toBe(i));
    HEXAGONS.forEach((c, i) => expect(faceAt(c)).toBe(12 + i));
    HEXAGONS.forEach((c) => expect(patchAt(c)).toBe(-1));
  });

  it('la toppa nera finisce a un terzo della strada verso la nera vicina', () => {
    const a = PENTAGONS[0];
    const b = PENTAGONS.find((p) => p !== a && dot(a, p) > 0.4)!; // una delle cinque vicine
    expect(patchAt(between(a, b, 0.3))).toBe(0);
    expect(patchAt(between(a, b, 0.37))).toBe(-1);
    expect(patchAt(between(a, b, 0.5))).toBe(-1); // a metà strada c'è la cucitura fra due bianche
  });

  it('ogni toppa nera ha cinque angoli uguali, in fila a 72 gradi', () => {
    for (let i = 0; i < 12; i++) {
      const corners = pentagonCorners(i);
      expect(corners.length).toBe(5);
      corners.forEach((c, k) => {
        expect(dot(c, PENTAGONS[i])).toBeCloseTo(dot(corners[0], PENTAGONS[i]), 9);
        expect(dot(c, corners[(k + 1) % 5])).toBeCloseTo(dot(corners[0], corners[1]), 9); // lati tutti uguali
      });
      // appena dentro l'angolo è ancora la toppa nera, appena fuori no
      expect(patchAt(between(PENTAGONS[i], corners[0], 0.97))).toBe(i);
      expect(patchAt(between(PENTAGONS[i], corners[0], 1.06))).toBe(-1);
    }
  });

  it('le toppe nere coprono poco più di un quarto del pallone', () => {
    let black = 0;
    const n = 20000;
    for (let i = 0; i < n; i++) {
      // punti sparsi in modo regolare sulla sfera (spirale di Fibonacci)
      const y = 1 - (2 * (i + 0.5)) / n;
      const r = Math.sqrt(1 - y * y);
      const a = i * Math.PI * (3 - Math.sqrt(5));
      if (patchAt([r * Math.cos(a), y, r * Math.sin(a)]) >= 0) black++;
    }
    expect(black / n).toBeGreaterThan(0.26);
    expect(black / n).toBeLessThan(0.3);
  });
});

describe('festa dei pronostici presi', () => {
  it('lo stesso pronostico in due schedine conta una volta', () => {
    expect(uniqueLegs([slip([leg(1, 'won'), leg(2, 'open')]), slip([leg(1, 'won')])]).length).toBe(2);
  });

  it('si festeggia solo un pronostico preso e non ancora festeggiato', () => {
    const legs = [leg(1, 'won'), leg(2, 'open'), leg(3, 'lost'), leg(4, 'won')];
    expect(freshWins(new Set([legKey(legs[0])]), legs).map((l) => l.match_id)).toEqual([4]);
  });

  it('due pronostici diversi sulla stessa partita sono due feste', () => {
    expect(freshWins(new Set(), [leg(1, 'won', 'over'), leg(1, 'won', 'gg')]).length).toBe(2);
  });
});
