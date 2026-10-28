import { CountLine, PlayerShots, countTip, playerTips } from './picks';

const line = (l: number, p: number, side: CountLine['side'] = 'totale'): CountLine => ({ side, line: l, p_over: p, fair_over: 1 / p, fair_under: 1 / (1 - p), offers: {} });

describe('countTip', () => {
  it('sceglie l\'esito più vicino al 70% tra 60% e 85%', () => {
    const tip = countTip([line(8.5, 0.82), line(9.5, 0.66), line(10.5, 0.48), line(11.5, 0.31)]);
    expect(tip).toEqual({ pick: 'Under', line: 11.5, p: 0.69, fair: 1 / 0.69 });
  });
  it('ignora le linee di una sola squadra e restituisce null fuori fascia', () => {
    expect(countTip([line(4.5, 0.7, 'casa'), line(20.5, 0.5)])).toBeNull();
  });
});

describe('playerTips', () => {
  it('i due più probabili a tirare in porta, senza gli assenti', () => {
    const p = (name: string, p_on: number, absent: string | null = null) => ({ name, p_on, absent }) as PlayerShots;
    expect(playerTips([p('A', 0.4), p('B', 0.7, 'infortunato'), p('C', 0.6), p('D', 0.5)]).map((x) => x.name)).toEqual(['C', 'D']);
  });
});
