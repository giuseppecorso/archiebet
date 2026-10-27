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

  it('dopo il login mostra il menu e le partite del giorno, con tendine per giorno e campionato', async () => {
    const harness = await navigateAs('/partite', true);

    const links = [...harness.routeNativeElement!.querySelectorAll('nav.nav a')].map((a) => a.textContent?.trim());
    expect(links).toEqual(['Home', 'Partite', 'Pronostici', 'Il mio Archie']); // Diretta dentro Partite

    const serieA = { code: 'ITA-A', name: 'Serie A', country: 'Italia', tier: 1 };
    const premier = { code: 'ENG-1', name: 'Premier League', country: 'Inghilterra', tier: 1 };
    (await nextRequest('/api/competitions')).flush([serieA, premier]);
    (await nextRequest((r) => r.url.startsWith('/api/bets/on-matches'))).flush([]);
    const today = await nextRequest((r) => r.url.startsWith('/api/matches?view=day'));
    expect(today.request.url).not.toContain('competitions='); // tutti i campionati
    today.flush([
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
    await harness.fixture.whenStable();
    const page = harness.routeNativeElement!;
    expect(page.textContent).not.toContain('Prossime'); // niente più divisione tra prossime e risultati

    const row = page.querySelector('ab-diretta-row a.row') as HTMLAnchorElement;
    expect(row.textContent).toContain('Napoli');
    expect(row.textContent).toContain('20:45'); // 18:45 UTC in ora italiana
    expect(row.getAttribute('href')).toBe('/partite/7'); // toccando la riga si apre la partita

    // Tendina dei campionati: Premier League
    const [daySelect, compSelect] = [...page.querySelectorAll('.toolbar select')] as HTMLSelectElement[];
    expect(daySelect.options.length).toBe(11); // da 3 giorni fa a 7 giorni avanti
    expect([...compSelect.options].map((o) => o.textContent?.trim())).toEqual(['Tutti i campionati', 'Italia · Serie A', 'Inghilterra · Premier League']);
    compSelect.value = 'ENG-1';
    compSelect.dispatchEvent(new Event('change'));
    harness.fixture.detectChanges();
    const english = await nextRequest((r) => r.url.startsWith('/api/matches?view=day'));
    expect(english.request.url).toContain('competitions=ENG-1');
    english.flush([]);
    await harness.fixture.whenStable();
    localStorage.removeItem('archiebet.matches.competition');
  });

  it('la home mostra le partite di oggi, le occasioni e ArchieTV', async () => {
    const harness = await navigateAs('/', true);
    expect(TestBed.inject(Router).url).toBe('/');
    (await nextRequest((r) => r.url.startsWith('/api/matches?view=upcoming'))).flush([]);
    (await nextRequest('/api/radar')).flush({ threshold: 0.02, max_price: 4, playable: [], simulation_bookmakers: [], upcoming: [], recent: [], live: null, live_secondary: null });
    (await nextRequest('/api/bets')).flush([]);
    (await nextRequest('/api/tv')).flush([
      { video_id: 'abc', title: 'Highlights Inter-Milan', channel: 'Serie A', published: '2026-10-20T21:00:00+00:00', thumbnail: 'https://i.ytimg.com/vi/abc/hqdefault.jpg' },
    ]);
    await harness.fixture.whenStable();
    const page = harness.routeNativeElement!;
    expect(page.querySelector('.hero h1')?.textContent).toContain('Oggi');
    expect(page.querySelector('ab-archie-tv')?.textContent).toContain('Highlights Inter-Milan');
    expect(page.querySelector('nav.nav a[aria-current="page"]')?.textContent?.trim()).toBe('Home');
  });

  it('la diretta mostra risultati, marcatori e cronaca come un sito di risultati (D133)', async () => {
    const harness = await navigateAs('/live', true); // i vecchi indirizzi portano a Partite, sulle partite in diretta
    expect(TestBed.inject(Router).url).toBe('/partite?stato=live');
    (await nextRequest('/api/competitions')).flush([]);
    (await nextRequest((r) => r.url.startsWith('/api/bets/on-matches'))).flush([
      { match_id: 2, bet_id: 5, legs: 3, market: '1X2', pick: '1', state: 'losing', probability: 0.21 },
    ]);
    const serieA = { code: 'ITA-A', name: 'Serie A', country: 'Italia', tier: 1 };
    const team = (id: number, name: string) => ({ id, name });
    const card = (id: number, extra: object) => ({
      id, competition: serieA, season: '2026/27', kickoff_at: '2026-10-21T18:45:00Z', kickoff_has_time: true,
      home: team(1, 'Inter'), away: team(2, 'Milan'), home_goals: null, away_goals: null, odds_1x2: null, ...extra,
    });
    const goal = { minute: 20, extra: null, side: 'home', kind: 'goal', player: 'Lautaro Martínez', other: 'Barella', detail: 'Normal Goal' };
    (await nextRequest((r) => r.url.startsWith('/api/matches?view=day'))).flush([
      { competition: serieA, matches: [
        card(1, { status: 'finished', home_goals: 1, away_goals: 0, ht_home_goals: 1, ht_away_goals: 0, highlights: [goal] }),
        card(2, { status: 'scheduled', live: { status: '2H', minute: 67, home_goals: 0, away_goals: 0 } }),
      ] },
    ]);
    await harness.fixture.whenStable();
    const page = harness.routeNativeElement!;
    expect(page.querySelectorAll('ab-diretta-row').length).toBe(1); // si apre già su "In diretta"
    expect(page.querySelector('ab-diretta-row .mine')?.textContent).toContain('sta perdendo (21%)'); // la mia multipla su questa partita (D155)
    expect(page.querySelector('.chips .count')?.textContent).toBe('1');
    ([...page.querySelectorAll('.chips .chip')] as HTMLButtonElement[]).find((b) => b.textContent?.includes('Tutte'))!.click();
    harness.fixture.detectChanges();
    const rows = [...page.querySelectorAll('ab-diretta-row')];
    expect(rows.length).toBe(2);
    expect(rows[0].querySelector('.scorers')?.textContent).toContain("Martínez 20'"); // marcatori sotto la riga
    expect(rows[0].textContent).toContain('Finale');
    expect(rows[0].textContent).toContain('(1-0)');
    expect(rows[1].querySelector('.live')?.textContent).toContain("67'");

    ([...page.querySelectorAll('.chips .chip')] as HTMLButtonElement[]).find((b) => b.textContent?.includes('In diretta'))!.click();
    harness.fixture.detectChanges();
    expect(page.querySelectorAll('ab-diretta-row').length).toBe(1);

    expect(page.querySelector('ab-diretta-row a.row')?.getAttribute('href')).toBe('/partite/2'); // la cronaca sta nella pagina della partita
    expect(page.querySelector('nav.nav a[aria-current="page"]')?.textContent?.trim()).toBe('Partite');
  });

  it('la bacheca Daily appende le schedine di Archie con le statistiche (D153)', async () => {
    const harness = await navigateAs('/pronostici', true); // la scheda principale di Pronostici
    const leg = { match_id: 9, kickoff_at: '2026-10-30T18:00:00Z', competition: 'Serie A', home: 'Inter', away: 'Milan', market: 'GG', selection: 'yes',
                  event: 'segnano entrambe', p: 0.66, price: 1.7, status: 'won' };
    const slip = { id: 1, kind: 'giorno', title: 'La schedina del giorno', period: '2026-10-30', published_at: '2026-10-30T09:00:00Z', singles: false,
                   legs: [leg], total_odds: 1.7, win_probability: 0.66, status: 'won' };
    (await nextRequest('/api/daily')).flush({
      board: [slip], today: { legs_won: 1, legs_closed: 1, legs_total: 1 },
      stats: [{ kind: 'giorno', title: 'La schedina del giorno', published: 1, closed: 1, won: 1, expected: 0.66, legs_won: 1, legs_closed: 1, profit: 0.7 }],
      history: [slip],
    });
    await harness.fixture.whenStable();
    const page = harness.routeNativeElement!;
    expect(page.querySelector('.note h2')?.textContent).toContain('La schedina del giorno');
    expect(page.querySelector('.note .e')?.textContent).toContain('Segnano entrambe');
    expect(page.querySelector('.stamp')?.textContent).toContain('Vinta');
    expect(page.querySelector('.stats tbody')?.textContent).toContain('+0,70');
  });

  it('il generatore propone pronostici studiati con il perché e ne genera altri (D137)', async () => {
    const harness = await navigateAs('/pronostici?tab=multipla', true);
    const serieB = { code: 'ITA-B', name: 'Serie B', country: 'Italia', tier: 2 };
    (await nextRequest('/api/competitions')).flush([serieB]);
    (await nextRequest('/api/study/themes')).flush({ tutte: 'Tutte', coppe: 'Competizioni internazionali' });
    const first = await nextRequest((r) => r.url.startsWith('/api/study/multiple'));
    expect(first.request.url).toBe('/api/study/multiple?level=equilibrato&legs=4&horizon=2days&auto=true'); // Archie decide quante partite
    const leg = {
      match: { id: 9, competition: serieB, season: '2026/27', kickoff_at: '2026-10-25T13:00:00Z', kickoff_has_time: true, status: 'scheduled',
               home: { id: 1, name: 'Brescia' }, away: { id: 2, name: 'Cittadella' }, home_goals: null, away_goals: null, odds_1x2: null },
      market: '1T_TGH0.5', selection: 'over', market_label: 'gol casa Under/Over 0.5 primo tempo', event: 'Brescia segna nel primo tempo',
      level: 'equilibrato', p_archie: 0.71, p_model: 0.64, evidence: [8, 9, 6, 8],
      reasons: ['«Brescia segna nel primo tempo»: è successo in 8 su 9 partite in casa del Brescia e in 6 su 8 in trasferta del Cittadella.'],
      prices: {},
    };
    first.flush({ level: 'equilibrato', legs: [leg], win_probability: 0.71, totals: {}, more: true });
    await harness.fixture.whenStable();
    const page = harness.routeNativeElement!;
    expect(page.querySelector('.event')?.textContent).toContain('Brescia segna nel primo tempo');
    expect(page.querySelector('.why-dlg')?.textContent).toContain('8 su 9 partite in casa del Brescia'); // il perché sta nel popup
    expect(page.querySelector('.offers')?.textContent).toContain("quota da cercare sull'app");
    expect(page.querySelector('nav.nav a[aria-current="page"]')?.textContent?.trim()).toBe('Pronostici');

    (page.querySelector('.again') as HTMLButtonElement).click(); // un'altra multipla, con altre partite
    harness.fixture.detectChanges();
    const second = await nextRequest((r) => r.url.startsWith('/api/study/multiple'));
    expect(second.request.url).toContain('exclude=9');
    second.flush({ level: 'equilibrato', legs: [], win_probability: 0, totals: {}, more: false });
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
