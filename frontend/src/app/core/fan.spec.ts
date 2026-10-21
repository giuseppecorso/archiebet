import { factTone } from './fan';

describe('factTone', () => {
  it('colora i fatti contro la squadra, a favore e neutri', () => {
    expect(factTone('squalifica')).toBe('bad');
    expect(factTone('rientro')).toBe('good');
    expect(factTone('allenatore_nuovo')).toBe('neutral');
  });
});
