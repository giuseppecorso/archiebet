import { liveScore } from './play';

describe('liveScore', () => {
  it('conta i gol simulati fino al minuto, partendo dal punteggio di partenza', () => {
    const sim = { score: [1, 0] as [number, number], sample: [{ minute: 35, side: 'away' as const }, { minute: 80, side: 'home' as const }] };
    expect(liveScore(sim, 30)).toEqual([1, 0]);
    expect(liveScore(sim, 60)).toEqual([1, 1]);
    expect(liveScore(sim, 90)).toEqual([2, 1]);
  });
});
