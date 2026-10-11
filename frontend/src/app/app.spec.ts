import { provideHttpClient } from '@angular/common/http';
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
  async function nextRequest(url: string) {
    for (let attempt = 0; attempt < 50; attempt++) {
      const [request] = http.match(url);
      if (request) return request;
      await new Promise((resolve) => setTimeout(resolve));
    }
    throw new Error(`Nessuna richiesta a ${url}`);
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

  it('dopo il login mostra il menu con le quattro sezioni', async () => {
    const harness = await navigateAs('/', true);
    expect(TestBed.inject(Router).url).toBe('/partite');

    const links = [...harness.routeNativeElement!.querySelectorAll('nav a')].map((a) =>
      a.textContent?.trim(),
    );
    expect(links).toEqual(['Partite', 'Le mie schedine', 'Le mie statistiche', 'Gioca']);
  });

  it('ogni sezione mostra la sua pagina con la fase in cui arriva', async () => {
    const harness = await navigateAs('/gioca', true);
    const page = harness.routeNativeElement!;
    expect(page.querySelector('h1')?.textContent).toContain('Gioca');
    expect(page.querySelector('.phase')?.textContent?.trim()).toBe('6');
    expect(page.querySelector('nav a[aria-current="page"]')?.textContent?.trim()).toBe('Gioca');
  });
});
