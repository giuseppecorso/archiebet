import { secondaryLabel } from './radar';

describe('Etichette di angoli e cartellini', () => {
  it('rende leggibili i nomi dei mercati secondari', () => {
    expect(secondaryLabel('COR9.5', 'over', 'Torino', 'Monza')).toBe('Angoli Over 9.5');
    expect(secondaryLabel('CRDH1.5', 'under', 'Torino', 'Monza')).toBe('Cartellini Torino Under 1.5');
    expect(secondaryLabel('CORA4.5', 'over', 'Torino', 'Monza')).toBe('Angoli Monza Over 4.5');
    expect(secondaryLabel('1X2', '1', 'Torino', 'Monza')).toBeNull();
  });
});
