import { ago, dayLabel, fairOdds, kickoffTime, num, odds, pct } from './format';

describe('formattazione', () => {
  it('mostra l\'orario in ora italiana', () => {
    expect(kickoffTime('2026-10-10T18:45:00Z')).toBe('20:45'); // ora legale: UTC+2
    expect(kickoffTime('2027-01-10T19:45:00Z')).toBe('20:45'); // ora solare: UTC+1
    expect(kickoffTime('2012-08-25T12:00:00Z', false)).toBe('--:--');
  });

  it('usa il giorno italiano anche vicino alla mezzanotte', () => {
    const now = new Date('2026-10-11T10:00:00Z');
    expect(dayLabel('2026-10-11T18:45:00Z', now)).toBe('OGGI');
    expect(dayLabel('2026-10-11T22:30:00Z', now)).toBe('DOMANI'); // 00:30 del 12 in Italia
    expect(dayLabel('2026-10-10T18:45:00Z', now)).toBe('IERI');
    expect(dayLabel('2026-10-17T13:00:00Z', now)).toBe('SAB 17/10');
    expect(dayLabel('2025-04-26T13:00:00Z', now)).toBe('26/04/25'); // lontana: con l'anno
  });

  it('formatta quote, numeri e percentuali', () => {
    expect(odds(1.9)).toBe('1.90');
    expect(odds(null)).toBe('–');
    expect(num(1.5)).toBe('1,5');
    expect(num(11.667)).toBe('11,67');
    expect(pct(0.375)).toBe('38%');
    expect(pct(null)).toBe('–');
  });

  it('da quanto tempo', () => {
    const now = new Date('2026-10-12T18:00:00Z');
    expect(ago('2026-10-12T17:59:40Z', now)).toBe('adesso');
    expect(ago('2026-10-12T17:55:00Z', now)).toBe('5 min fa');
    expect(ago('2026-10-12T16:30:00Z', now)).toBe("un'ora fa");
    expect(ago('2026-10-12T15:00:00Z', now)).toBe('3 ore fa');
    expect(ago('2026-10-11T12:00:00Z', now)).toBe('ieri');
    expect(ago('2026-09-30T18:00:00Z', now)).toBe('12 giorni fa');
    expect(ago(null, now)).toBe('mai');
  });

  it('quota giusta = 1 / probabilità', () => {
    expect(fairOdds(0.4)).toBe('2.50');
    expect(fairOdds(0.3)).toBe('3.33');
    expect(fairOdds(0)).toBe('–');
    expect(fairOdds(null)).toBe('–');
  });
});
