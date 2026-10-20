import { liveLabel, liveShort } from './live';

describe('Etichetta del minuto live', () => {
  it('mostra minuto, intervallo e supplementari', () => {
    expect(liveLabel({ status: '2H', minute: 67, home_goals: 1, away_goals: 0 })).toBe("67'");
    expect(liveLabel({ status: 'HT', minute: 45, home_goals: 0, away_goals: 0 })).toBe('Intervallo');
    expect(liveLabel({ status: 'ET', minute: 105, home_goals: 1, away_goals: 1 })).toBe('Supplementari');
    expect(liveShort({ status: 'HT', minute: 45, home_goals: 0, away_goals: 0 })).toBe('INT');
    expect(liveShort({ status: '1H', minute: 12, home_goals: 0, away_goals: 0 })).toBe("12'");
  });
});
