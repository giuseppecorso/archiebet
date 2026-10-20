import { hueOf, initials } from './crest';

describe('Distintivo di riserva', () => {
  it('ricava le iniziali dal nome', () => {
    expect(initials('Hellas Verona')).toBe('HV');
    expect(initials('Inter')).toBe('IN');
    expect(initials('1. FC Köln')).toBe('1F');
  });

  it('dà sempre lo stesso colore alla stessa squadra', () => {
    expect(hueOf('Inter')).toBe(hueOf('Inter'));
    expect(hueOf('Inter')).toBeGreaterThanOrEqual(0);
    expect(hueOf('Inter')).toBeLessThan(360);
  });
});
