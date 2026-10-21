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

  afterEach(() => {
    // La dashboard chiede sempre anche le partite in corso (D92): qui non ce ne sono
    http.match((r) => r.url.startsWith('/api/matches?view=live')).forEach((r) => r.flush([]));
    // ... e lo storico di Chiedi ad Archie (Fase 6)
    http.match((r) => r.url.startsWith('/api/ask')).forEach((r) => r.flush([]));
    // ... e il regolamento nelle statistiche (Fase 6)
    http.match((r) => r.url === '/api/rules').forEach((r) => r.flush({ rules: [], suggestions: [], style: null, style_at: null }));
    http.verify();
  });

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
    (await nextRequest((r) => r.url.startsWith('/api/matches?view=live'))).flush([]); // nessuna partita in corso
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
    (await nextRequest('/api/picks/off-line')).flush([
      {
        match: legMatch(7, 'Napoli', 'Frosinone'), market: '1X2', selection: '2', probability: 0.18, bookmaker: 'Eurobet',
        price: 7.0, value: 0.26, suspicious: true,
      },
    ]);
    (await nextRequest((r) => r.url.startsWith('/api/ask'))).flush([]); // storico di Chiedi ad Archie: vuoto
    await harness.fixture.whenStable();
    const offLine = harness.routeNativeElement!.querySelector('ab-off-line-card')!.textContent!;
    expect(offLine).toContain('2 · Frosinone');
    expect(offLine).toContain('+26,0%');
    expect(offLine).toContain('Sospetta');
    const card = harness.routeNativeElement!.querySelector('ab-multiple-card')!.textContent!;
    expect(card).toContain('1 · Napoli');
    expect(card).toContain('3.40'); // quota totale
    expect(card).toContain('34,00 €'); // vincita con 10 €
    expect(card).toContain('1 volta su 3,6');
    expect(card).toContain('Nessuna multipla con valore'); // onestà: senza valore lo dice
    expect(card).toContain('Su Eurobet non c');

    const bar = harness.routeNativeElement!.querySelector('ab-data-status')!.textContent!;
    expect(bar).toContain('previsioni 3/5');
    expect(bar).toContain('· 8 in arrivo');

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
    (await nextRequest((r) => r.url.startsWith('/api/matches?view=live'))).flush([]); // nessuna partita in corso
    await harness.fixture.whenStable();
    const chips = [...harness.routeNativeElement!.querySelectorAll('.filters .chip')].map((b) => b.textContent?.trim());
    expect(chips).toEqual(['Premier League']);
    localStorage.removeItem('archiebet.matches.filters');
  });

  it('la sezione Gioca (Fase 6) mostra simulatore e sfida', async () => {
    const harness = await navigateAs('/gioca', true);
    (await nextRequest('/api/play/matches')).flush([]);
    (await nextRequest((r) => r.url.startsWith('/api/play/challenge'))).flush({ stake: 10, rows: [], standings: [] });
    await harness.fixture.whenStable();
    const page = harness.routeNativeElement!;
    expect(page.querySelector('h1')?.textContent).toContain('Gioca');
    expect(page.textContent).toContain('Simulatore partita');
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
    expect(page.querySelector('.cells .v.valore')?.textContent?.trim()).toBe('+ Sisal 3.40');
    expect(page.querySelector('.cells .v.poco')?.textContent?.trim()).toBe('Eurobet 2.30');
    expect(page.querySelector('.occ')?.textContent?.trim()).toBe('1 occasione');
    expect(page.querySelector('.source')?.textContent).toContain('Pinnacle');
  });

  it('il generatore manda le scelte al backend e mostra la multipla', async () => {
    const harness = await navigateAs('/pronostici?tab=multipla', true);
    const serieA = { code: 'ITA-A', name: 'Serie A', country: 'Italia', tier: 1 };
    const premier = { code: 'ENG-1', name: 'Premier League', country: 'Inghilterra', tier: 1 };
    (await nextRequest('/api/competitions')).flush([serieA, premier]);
    const first = await nextRequest((r) => r.url.startsWith('/api/picks/multiple'));
    expect(first.request.url).toBe('/api/picks/multiple?horizon=week&profile=equilibrata&legs=4'); // tutti i mercati e campionati: niente filtri
    first.flush({ horizon: 'week', profile: 'equilibrata', legs: 4, multiples: [], missing: ['Sisal', 'Eurobet'] });
    await harness.fixture.whenStable();
    const page = harness.routeNativeElement!;
    expect(page.querySelector('ab-generator')!.textContent).toContain("non c'è una multipla sensata");

    const click = (text: string) =>
      ([...page.querySelectorAll('ab-generator button')] as HTMLButtonElement[]).find((b) => b.textContent?.trim() === text)!.click();
    click('Più coraggiosa');
    click('Goal/NoGoal'); // tolto dai mercati
    click('Premier League'); // solo Premier
    harness.fixture.detectChanges();
    const second = await nextRequest((r) => r.url.startsWith('/api/picks/multiple'));
    const url = new URL(second.request.url, 'http://x');
    expect(url.searchParams.get('profile')).toBe('coraggiosa');
    expect(url.searchParams.get('markets')).toBe('1X2,DC,OU2.5');
    expect(url.searchParams.get('competitions')).toBe('ENG-1');
    second.flush({ horizon: 'week', profile: 'coraggiosa', legs: 4, missing: [], multiples: [] });
    await harness.fixture.whenStable();
  });

  it("tu contro Archie: fiuto e giocate d'accordo o contrarie", async () => {
    const harness = await navigateAs('/statistiche', true);
    const empty = { bets: 0, open: 0, settled: 0, won: 0, staked: '0', returned: '0', profit: '0', roi: null, win_rate: null, avg_clv: null, clv_count: 0 };
    (await nextRequest((r) => r.url.startsWith('/api/bets/summary'))).flush({ period: 'all', real: empty, simulated: empty });
    (await nextRequest('/api/budget')).flush({ week_staked: '0', week_budget: null, month_staked: '0', month_budget: null, warnings: [] });
    (await nextRequest((r) => r.url.startsWith('/api/bets/breakdown'))).flush({
      by_size: [], by_bookmaker: [], by_market: [], by_competition: [],
      habits: { bets: 0, avg_stake: null, avg_odds: null, multiple_share: null, avg_selections: null, top_market: null, top_bookmaker: null, top_teams: [] },
    });
    const versus = await nextRequest((r) => r.url.startsWith('/api/bets/versus'));
    expect(versus.request.url).toBe('/api/bets/versus?kind=real&period=all');
    versus.flush({
      judged: 40, without_archie: 2, skill: 3.2, skill_std_error: 2.9,
      agreed: { n: 25, won: 14, expected_wins: 12.1, roi: 0.08, avg_value: 0.04 },
      disagreed: { n: 15, won: 6, expected_wins: 6.7, roi: -0.12, avg_value: -0.07 },
    });
    (await nextRequest('/api/rules')).flush({ rules: [], suggestions: [], style: null, style_at: null }); // regolamento (Fase 6)
    await harness.fixture.whenStable();
    const section = harness.routeNativeElement!.querySelector('[aria-labelledby="versus-title"]')!.textContent!;
    expect(section).toContain('+3,2');
    expect(section).toContain('dentro il caso'); // 3,2 < 2 × 2,9
    expect(section).toContain("Archie d'accordo");
    expect(section).toContain('+8,0%');
    expect(section).toContain('2 selezioni chiuse non hanno una previsione');
  });
});
