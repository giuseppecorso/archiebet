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
    expect(links).toEqual(['Partite', 'Le mie schedine', 'Le mie statistiche', 'Laboratorio', 'Gioca']);

    const serieA = { code: 'ITA-A', name: 'Serie A', country: 'Italia', tier: 1 };
    (await nextRequest('/api/competitions')).flush([serieA]);
    const upcoming = await nextRequest((r) => r.url.startsWith('/api/matches?view=upcoming'));
    expect(upcoming.request.url).toContain('competitions=ITA-A');
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
    await harness.fixture.whenStable();

    const bar = harness.routeNativeElement!.querySelector('ab-data-status')!.textContent!;
    expect(bar).toContain('previsioni 3/5');
    expect(bar).toContain('(8 in arrivo)');

    const row = harness.routeNativeElement!.querySelector('ab-match-row a') as HTMLAnchorElement;
    expect(row.textContent).toContain('Napoli');
    expect(row.textContent).toContain('20:45'); // 18:45 UTC in ora italiana
    expect(row.textContent).toContain('1.44');
    expect(row.getAttribute('href')).toBe('/partite/7');
  });

  it('ogni sezione mostra la sua pagina con la fase in cui arriva', async () => {
    const harness = await navigateAs('/gioca', true);
    const page = harness.routeNativeElement!;
    expect(page.querySelector('h1')?.textContent).toContain('Gioca');
    expect(page.querySelector('.phase')?.textContent?.trim()).toBe('6');
    expect(page.querySelector('nav a[aria-current="page"]')?.textContent?.trim()).toBe('Gioca');
  });
});
