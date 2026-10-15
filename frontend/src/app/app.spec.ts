import { HttpRequest, provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { provideRouter, Router, withComponentInputBinding } from '@angular/router';
import { RouterTestingHarness } from '@angular/router/testing';
import { routes } from './app.routes';

describe('ArchieBet: navigazione', () => {
  let http: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [
        provideRouter(routes, withComponentInputBinding()),
        provideHttpClient(),
        provideHttpClientTesting(),
      ],
    });
    http = TestBed.inject(HttpTestingController);
  });

  afterEach(() => http.verify());

  /** La navigazione è asincrona: aspetta che il guard faccia partire la richiesta. */
  async function nextRequest(url: string | ((req: HttpRequest<unknown>) => boolean)) {
    for (let attempt = 0; attempt < 50; attempt++) {
      const [request] = http.match(url);
      if (request) return request;
      await new Promise((resolve) => setTimeout(resolve));
    }
    throw new Error(`Nessuna richiesta a ${String(url)}`);
  }

  async function navigateAs(url: string, loggedIn: boolean): Promise<RouterTestingHarness> {
    const harness = await RouterTestingHarness.create();
    const navigation = harness.navigateByUrl(url);
    const me = await nextRequest('/api/auth/me');
    if (loggedIn) {
      me.flush({ id: 1, username: 'giuse', is_admin: true });
    } else {
      me.flush({ detail: 'Accesso richiesto' }, { status: 401, statusText: 'Unauthorized' });
    }
    await navigation;
    return harness;
  }

  it('chi non ha fatto login finisce sulla pagina di accesso', async () => {
    await navigateAs('/partite', false);
    expect(TestBed.inject(Router).url).toBe('/login');
  });

  it('dopo il login mostra il menu e le partite della dashboard', async () => {
    const harness = await navigateAs('/', true);
    expect(TestBed.inject(Router).url).toBe('/partite');

    const links = [...harness.routeNativeElement!.querySelectorAll('nav a')].map((a) => a.textContent?.trim());
    expect(links).toEqual(['Partite', 'Pronostici', 'Le mie schedine', 'Le mie statistiche', 'Laboratorio', 'Gioca']);

    const serieA = { code: 'ITA-A', name: 'Serie A', country: 'Italia', tier: 1 };
    const premier = { code: 'ENG-1', name: 'Premier League', country: 'Inghilterra', tier: 1 };
    (await nextRequest('/api/competitions')).flush([serieA, premier]);
    const upcoming = await nextRequest((r) => r.url.startsWith('/api/matches?view=upcoming'));
    expect(upcoming.request.url).toContain('competitions=ITA-A'); // tendina sull'Italia: niente Premier
    expect(upcoming.request.url).not.toContain('ENG-1');
    upcoming.flush([
      {
        competition: serieA,
        matches: [
          {
            id: 7, competition: serieA, season: '2026/27', kickoff_at: '2026-10-10T18:45:00Z', kickoff_has_time: true,
            status: 'scheduled', home: { id: 1, name: 'Napoli' }, away: { id: 2, name: 'Frosinone' },
            home_goals: null, away_goals: null, odds_1x2: { '1': 1.44, X: 4.75, '2': 7 },
          },
        ],
      },
    ]);
    (await nextRequest((r) => r.url.startsWith('/api/matches?view=results'))).flush([]);
    (await nextRequest('/api/status')).flush({
      now: '2026-10-10T12:00:00Z', syncing: false, upcoming: 5, upcoming_with_prediction: 3,
      sources: [{ source: 'football-data', label: 'Serie A e B', configured: true, last_ok_at: '2026-10-10T11:00:00Z', last_run_at: '2026-10-10T11:00:00Z', last_run_ok: true, message: 'ok' }],
      competitions: [{ competition: serieA, last_result_at: '2026-09-20T18:45:00Z', awaiting_results: 8, next_match_at: '2026-10-10T18:45:00Z' }],
    });
    const legMatch = (id: number, home: string, away: string) => ({
      id, competition: serieA, season: '2026/27', kickoff_at: '2026-10-10T18:45:00Z', kickoff_has_time: true,
      status: 'scheduled', home: { id, name: home }, away: { id: id + 100, name: away }, home_goals: null, away_goals: null, odds_1x2: null,
    });
    (await nextRequest('/api/picks/multiple?horizon=today')).flush({
      horizon: 'today', missing: ['Eurobet'],
      multiples: [{
        bookmaker: 'Sisal', with_value: false, price: 3.4, win_probability: 0.28, one_in: 3.57, alive_before_last: 0.4, expected_value: -0.048,
        legs: [
          { match: legMatch(7, 'Napoli', 'Frosinone'), market: '1X2', selection: '1', probability: 0.7, price: 1.38, value: -0.034 },
          { match: legMatch(8, 'Roma', 'Lecce'), market: 'DC', selection: '1X', probability: 0.8, price: 1.2, value: -0.04 },
        ],
      }],
    });
    await harness.fixture.whenStable();
    const card = harness.routeNativeElement!.querySelector('ab-multiple-card')!.textContent!;
    expect(card).toContain('1 · Napoli');
    expect(card).toContain('3.40'); // quota totale
    expect(card).toContain('34,00 €'); // vincita con 10 €
    expect(card).toContain('1 volta su 3,6');
    expect(card).toContain('Nessuna multipla con valore'); // onestà: senza valore lo dice
    expect(card).toContain('Su Eurobet non c');

    const bar = harness.routeNativeElement!.querySelector('ab-data-status')!.textContent!;
    expect(bar).toContain('previsioni 3/5');
    expect(bar).toContain('(8 in arrivo)');

    const row = harness.routeNativeElement!.querySelector('ab-match-row a') as HTMLAnchorElement;
    expect(row.textContent).toContain('Napoli');
    expect(row.textContent).toContain('20:45'); // 18:45 UTC in ora italiana
    expect(row.textContent).toContain('1.44');
    expect(row.getAttribute('href')).toBe('/partite/7');

    // Tendina dei paesi: Inghilterra → solo la Premier League
    const select = harness.routeNativeElement!.querySelector('.country select') as HTMLSelectElement;
    expect([...select.options].map((o) => o.textContent?.trim())).toEqual(['Italia', 'Inghilterra', 'Tutti i paesi']);
    select.value = 'Inghilterra';
    select.dispatchEvent(new Event('change'));
    harness.fixture.detectChanges();
    const english = await nextRequest((r) => r.url.startsWith('/api/matches?view=upcoming'));
    expect(english.request.url).toContain('competitions=ENG-1');
    expect(english.request.url).not.toContain('ITA-A');
    english.flush([]);
    (await nextRequest((r) => r.url.startsWith('/api/matches?view=results'))).flush([]);
    await harness.fixture.whenStable();
    const chips = [...harness.routeNativeElement!.querySelectorAll('.filters .chip')].map((b) => b.textContent?.trim());
    expect(chips).toEqual(['Premier League']);
    localStorage.removeItem('archiebet.matches.filters');
  });

  it('ogni sezione mostra la sua pagina con la fase in cui arriva', async () => {
    const harness = await navigateAs('/gioca', true);
    const page = harness.routeNativeElement!;
    expect(page.querySelector('h1')?.textContent).toContain('Gioca');
    expect(page.querySelector('.phase')?.textContent?.trim()).toBe('6');
    expect(page.querySelector('nav a[aria-current="page"]')?.textContent?.trim()).toBe('Gioca');
  });

  it("i pronostici mostrano la stima migliore e le quote di Sisal ed Eurobet con l'etichetta", async () => {
    const harness = await navigateAs('/pronostici', true);
    const serieA = { code: 'ITA-A', name: 'Serie A', country: 'Italia', tier: 1 };
    const offer = (bookmaker: string, price: number, value: number, verdict: string) => ({ bookmaker, price, value, verdict });
    (await nextRequest('/api/picks')).flush({
      bookmakers: ['Sisal', 'Eurobet'],
      picks: [
        {
          match: {
            id: 7, competition: serieA, season: '2026/27', kickoff_at: '2026-10-17T16:00:00Z', kickoff_has_time: true,
            status: 'scheduled', home: { id: 1, name: 'Milan' }, away: { id: 2, name: 'Inter' },
            home_goals: null, away_goals: null, odds_1x2: null,
          },
          favorite: '2', favorite_probability: 0.4, signals: 1,
          markets: [
            {
              market: '1X2', source: 'Pinnacle', from_model: false,
              probabilities: { '1': 0.32, X: 0.28, '2': 0.4 },
              offers: { '1': [offer('Sisal', 3.4, 0.088, 'valore')], '2': [offer('Eurobet', 2.3, -0.08, 'paga poco')] },
            },
          ],
        },
      ],
    });
    await harness.fixture.whenStable();
    const page = harness.routeNativeElement!;
    expect(page.querySelector('.fav')?.textContent).toContain('2 · Inter');
    expect(page.querySelector('.fav')?.textContent).toContain('40%');
    expect(page.querySelector('.cells .v.valore')?.textContent?.trim()).toBe('Sisal 3.40');
    expect(page.querySelector('.cells .v.poco')?.textContent?.trim()).toBe('Eurobet 2.30');
    expect(page.querySelector('.occ')?.textContent?.trim()).toBe('1 occasione');
    expect(page.querySelector('.source')?.textContent).toContain('Pinnacle');
  });
});
