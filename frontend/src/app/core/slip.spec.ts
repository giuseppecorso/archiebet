import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { SlipLeg, SlipService } from './slip';

const future = new Date(Date.now() + 86_400_000).toISOString();
const competition = { code: 'ITA-A', name: 'Serie A', country: 'Italia', tier: 1 };

function leg(id: number, pick = '1', odds = 2, bookmaker: string | null = 'Sisal'): SlipLeg {
  return { match: { id, home: { id: 1, name: 'Inter' }, away: { id: 2, name: 'Roma' }, kickoff_at: future, competition }, market: '1X2', pick, odds, bookmaker };
}

describe('schedina in costruzione', () => {
  let slip: SlipService;

  beforeEach(() => {
    localStorage.clear();
    TestBed.configureTestingModule({ providers: [provideHttpClient(), provideHttpClientTesting()] });
    slip = TestBed.inject(SlipService);
  });

  it('aggiunge, sostituisce sulla stessa partita e toglie con un secondo clic', () => {
    slip.toggle(leg(1, '1', 2));
    slip.toggle(leg(2, 'X', 3.2));
    expect(slip.legs().length).toBe(2);
    expect(slip.totalOdds()).toBeCloseTo(6.4);
    slip.toggle(leg(1, '2', 4)); // stessa partita: un solo esito
    expect(slip.legs().map((l) => l.pick)).toEqual(['X', '2']);
    slip.toggle(leg(1, '2', 4)); // secondo clic: tolto
    expect(slip.legs().map((l) => l.match.id)).toEqual([2]);
  });

  it('resta salvata nel browser e calcola la vincita', () => {
    slip.toggle(leg(1, '1', 1.85));
    slip.toggle(leg(2, '1', 2.1));
    slip.stake.set('10');
    expect(slip.summary()).toEqual({ valid: true, total: 3.885, payout: 38.85 });
    expect(JSON.parse(localStorage.getItem('archiebet.slip')!).length).toBe(2);
    expect(slip.bookmaker()).toBe('Sisal');
    slip.toggle(leg(3, '1', 1.5, 'Eurobet'));
    expect(slip.bookmaker()).toBeNull(); // bookmaker diversi
  });

  it('registra la schedina e la svuota', async () => {
    const http = TestBed.inject(HttpTestingController);
    slip.toggle(leg(1, 'X', 3.25));
    const done = slip.register();
    const req = http.expectOne('/api/bets');
    expect(req.request.body.selections).toEqual([{ match_id: 1, market: '1X2', pick: 'X', odds: '3.250' }]);
    expect(req.request.body.kind).toBe('simulated');
    req.flush({ bet: { id: 9 } });
    await done;
    expect(slip.legs()).toEqual([]);
  });
});
