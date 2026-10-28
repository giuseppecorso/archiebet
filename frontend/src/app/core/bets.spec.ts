import { euro, marketFamily, marketLabel, marketSelections, pickLabel, preview, systemPreview } from './bets';

describe('giocate: etichette e anteprima', () => {
  it('etichetta gli esiti in italiano', () => {
    const match = { home: { id: 1, name: 'Inter' }, away: { id: 2, name: 'Roma' } };
    expect(pickLabel('1X2', '1', match)).toBe('1 · Inter');
    expect(pickLabel('1X2', '2', match)).toBe('2 · Roma');
    expect(pickLabel('GG', 'no')).toBe('NoGoal');
    expect(pickLabel('OU2.5', 'over')).toBe('Over 2.5');
  });

  it('gestisce le linee dei gol, gli angoli e i cartellini (D131)', () => {
    const match = { home: { id: 1, name: 'Inter' }, away: { id: 2, name: 'Roma' } };
    expect(pickLabel('OU4.5', 'under')).toBe('Under 4.5');
    expect(pickLabel('COR9.5', 'over')).toBe('Over 9.5 angoli');
    expect(pickLabel('CRDA1.5', 'over', match)).toBe('Over 1.5 cartellini · Roma');
    expect(marketLabel('CORH4.5', match)).toBe('Angoli Inter U/O 4.5');
    expect(marketLabel('OU0.5')).toBe('Under / Over 0.5');
    expect(marketSelections('DC')).toEqual(['1X', 'X2', '12']);
    expect(['1X2', 'OU2.5', 'CORH4.5', 'CRD3.5'].map(marketFamily)).toEqual(['esito', 'gol', 'angoli', 'cartellini']);
  });

  it('gestisce gol di una squadra e Draw No Bet (D135)', () => {
    const match = { home: { id: 1, name: 'Inter' }, away: { id: 2, name: 'Roma' } };
    expect(pickLabel('TGH1.5', 'over', match)).toBe('Over 1.5 gol · Inter');
    expect(marketLabel('TGA0.5', match)).toBe('Gol Roma U/O 0.5');
    expect(pickLabel('DNB', '2', match)).toBe('2 DNB · Roma');
    expect(marketSelections('DNB')).toEqual(['1', '2']);
    expect(['TGH1.5', 'DNB'].map(marketFamily)).toEqual(['gol squadra', 'esito']);
  });

  it('calcola quota totale e vincita come il backend', () => {
    // 1,85 × 2,10 × 1,50 = 5,8275; × 10 € = 58,28 € (stesso test del backend)
    expect(preview([1.85, 2.1, 1.5], 10)).toEqual({ total: 5.8275, payout: 58.28 });
    // Caso trovato a mano: 1,55 × 3,19 = 4,9445 → × 10 = 49,445 → 49,45 (non 49,44 per colpa della virgola mobile)
    expect(preview([1.55, 3.19], 10)).toEqual({ total: 4.9445, payout: 49.45 });
  });

  it('formatta gli euro con il segno', () => {
    expect(euro('12.5', true)).toBe('+12,50 €');
    expect(euro(-3, true)).toBe('−3,00 €');
    expect(euro('0', true)).toBe('0,00 €');
    expect(euro(null)).toBe('–');
  });
});

describe('systemPreview', () => {
  it('sistema 2 su 3 con 9 €: 3 doppie, minimo 18, massimo 78', () => {
    expect(systemPreview([2, 3, 4], 2, 9)).toEqual({ combos: 3, min: 18, max: 78 });
    expect(systemPreview([2, 2, 2, 2, 2, 2], 4, 15).combos).toBe(15);
  });
});
