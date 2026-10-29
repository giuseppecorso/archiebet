import { HttpClient, HttpErrorResponse, httpResource } from '@angular/common/http';
import { Component, effect, inject, signal } from '@angular/core';
import { Router } from '@angular/router';
import { firstValueFrom } from 'rxjs';

interface AccountOut {
  username: string;
  display_name: string | null;
  email: string | null;
  created_at: string;
}

function message(e: unknown, fallback: string): string {
  if (e instanceof HttpErrorResponse) {
    const d = e.error?.detail;
    if (typeof d === 'string') return d;
    if (Array.isArray(d)) return 'Controlla i campi: email valida, password di almeno 10 caratteri.';
  }
  return fallback;
}

/** I tuoi dati (D162): nome utente, nome da mostrare, email, cambio password. */
@Component({
  selector: 'ab-account-card',
  template: `
    <section class="panel box acc" aria-labelledby="acc-title">
      <h2 id="acc-title" class="title box-title">I tuoi dati</h2>
      @if (data.value(); as a) {
        <p class="muted small">Nome utente per entrare: <strong>{{ a.username }}</strong> (non si cambia)</p>
        <div class="fields">
          <label><span class="label">Nome da mostrare</span>
            <input [value]="name()" (input)="name.set($any($event.target).value)" maxlength="60" placeholder="es. Giuse" /></label>
          <label><span class="label">Email (facoltativa)</span>
            <input type="email" [value]="email()" (input)="email.set($any($event.target).value)" maxlength="120" placeholder="nome@esempio.it" /></label>
        </div>
        <button type="button" class="btn-primary" (click)="save()" [disabled]="busy()">Salva i dati</button>

        <h3 class="title sub">Cambia password</h3>
        <div class="fields">
          <label><span class="label">Password attuale</span>
            <input type="password" autocomplete="current-password" [value]="oldPw()" (input)="oldPw.set($any($event.target).value)" /></label>
          <label><span class="label">Nuova password (almeno 10 caratteri)</span>
            <input type="password" autocomplete="new-password" [value]="newPw()" (input)="newPw.set($any($event.target).value)" /></label>
        </div>
        <button type="button" class="ghost" (click)="changePassword()" [disabled]="busy() || newPw().length < 10 || !oldPw()">Cambia password</button>
      }
      @if (msg(); as m) {
        <p class="small" [class.err]="!m.ok" role="status">{{ m.text }}</p>
      }
    </section>
  `,
  styles: `
    .acc { margin-bottom: 12px; }
    .fields { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 10px 14px; margin: 10px 0; }
    label { display: flex; flex-direction: column; gap: 4px; }
    input { min-height: 36px; padding: 4px 10px; font: inherit; color: var(--text); background: var(--bg-deep); border: 1px solid var(--line-strong); border-radius: 4px; }
    button { min-height: 36px; padding: 4px 16px; }
    .sub { margin: 18px 0 0; font-size: 15px; }
    .err { color: var(--loss); }
  `,
})
export class AccountCard {
  private readonly http = inject(HttpClient);
  private readonly router = inject(Router);
  protected readonly data = httpResource<AccountOut>(() => '/api/auth/account');
  protected readonly name = signal('');
  protected readonly email = signal('');
  protected readonly oldPw = signal('');
  protected readonly newPw = signal('');
  protected readonly busy = signal(false);
  protected readonly msg = signal<{ ok: boolean; text: string } | null>(null);

  constructor() {
    effect(() => {
      const a = this.data.value();
      if (!a) return;
      this.name.set(a.display_name ?? '');
      this.email.set(a.email ?? '');
    });
  }

  protected async save(): Promise<void> {
    this.busy.set(true);
    try {
      await firstValueFrom(this.http.put('/api/auth/account', { display_name: this.name(), email: this.email() }));
      this.msg.set({ ok: true, text: 'Dati salvati.' });
    } catch (e) {
      this.msg.set({ ok: false, text: message(e, 'Salvataggio non riuscito.') });
    } finally {
      this.busy.set(false);
    }
  }

  protected async changePassword(): Promise<void> {
    this.busy.set(true);
    try {
      await firstValueFrom(this.http.post('/api/auth/password', { old: this.oldPw(), new: this.newPw() }));
      this.msg.set({ ok: true, text: 'Password cambiata: rientra con quella nuova.' });
      setTimeout(() => void this.router.navigateByUrl('/login'), 1500);
    } catch (e) {
      this.msg.set({ ok: false, text: message(e, 'Cambio password non riuscito.') });
    } finally {
      this.busy.set(false);
    }
  }
}
