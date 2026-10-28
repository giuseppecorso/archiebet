import { HttpClient } from '@angular/common/http';
import { Component, inject, signal } from '@angular/core';
import { firstValueFrom } from 'rxjs';

type State = 'loading' | 'unsupported' | 'ios-install' | 'denied' | 'off' | 'on';

/** La chiave pubblica (base64url) nel formato che vuole PushManager */
function keyBytes(base64url: string): Uint8Array<ArrayBuffer> {
  const base64 = (base64url + '='.repeat((4 - (base64url.length % 4)) % 4)).replace(/-/g, '+').replace(/_/g, '/');
  const raw = atob(base64);
  const out = new Uint8Array(new ArrayBuffer(raw.length));
  for (let i = 0; i < raw.length; i++) out[i] = raw.charCodeAt(i);
  return out;
}

/** "Avvisami quando escono le schedine" (D158): notifiche Web Push per questo dispositivo. */
@Component({
  selector: 'ab-push-toggle',
  template: `
    <div class="push">
      @switch (state()) {
        @case ('on') {
          <p>🔔 Su questo dispositivo ricevi un avviso quando Archie pubblica le schedine in bacheca.</p>
          <button type="button" class="ghost" (click)="turnOff()" [disabled]="busy()">Spegni gli avvisi</button>
        }
        @case ('off') {
          <p>Vuoi un avviso sul telefono quando escono le schedine della bacheca (ogni mattina alle 10)?</p>
          <button type="button" class="btn-primary" (click)="turnOn()" [disabled]="busy()">Avvisami</button>
        }
        @case ('denied') {
          <p class="muted">Le notifiche sono bloccate per questo sito: riattivale dalle impostazioni del browser (lucchetto accanto all'indirizzo → Notifiche).</p>
        }
        @case ('ios-install') {
          <p class="muted">Su iPhone gli avvisi arrivano solo con ArchieBet installata: tocca Condividi → "Aggiungi alla schermata Home", poi aprila da lì e torna qui.</p>
        }
        @case ('unsupported') {
          <p class="muted">Questo browser non supporta le notifiche (servono Chrome, Edge, Firefox o Safari aggiornati, e l'indirizzo https).</p>
        }
      }
      @if (error(); as e) {
        <p class="err">{{ e }}</p>
      }
    </div>
  `,
  styles: `
    .push { display: flex; flex-wrap: wrap; align-items: center; gap: 8px 14px; }
    .push p { flex: 1 1 260px; margin: 0; }
    .push button { min-height: 36px; padding: 4px 16px; }
    .err { flex-basis: 100%; color: var(--loss); }
  `,
})
export class PushToggle {
  private readonly http = inject(HttpClient);
  protected readonly state = signal<State>('loading');
  protected readonly busy = signal(false);
  protected readonly error = signal<string | null>(null);

  constructor() {
    this.check().catch(() => this.state.set('unsupported'));
  }

  private async registration(): Promise<ServiceWorkerRegistration | null> {
    return 'serviceWorker' in navigator ? ((await navigator.serviceWorker.getRegistration()) ?? null) : null;
  }

  private async check(): Promise<void> {
    const ios = /iPhone|iPad/.test(navigator.userAgent);
    const installed = typeof matchMedia === 'function' && matchMedia('(display-mode: standalone)').matches;
    if (!('PushManager' in window) || !('Notification' in window)) {
      this.state.set(ios && !installed ? 'ios-install' : 'unsupported');
      return;
    }
    if (Notification.permission === 'denied') {
      this.state.set('denied');
      return;
    }
    const sub = await (await this.registration())?.pushManager.getSubscription();
    if (!sub) {
      this.state.set(location.protocol === 'https:' ? 'off' : 'unsupported');
      return;
    }
    const { active } = await firstValueFrom(this.http.post<{ active: boolean }>('/api/push/status', { endpoint: sub.endpoint }));
    this.state.set(active ? 'on' : 'off');
  }

  protected async turnOn(): Promise<void> {
    this.busy.set(true);
    this.error.set(null);
    try {
      if ((await Notification.requestPermission()) !== 'granted') {
        this.state.set(Notification.permission === 'denied' ? 'denied' : 'off');
        return;
      }
      const reg = await this.registration();
      if (!reg) throw new Error('service worker assente');
      const { key } = await firstValueFrom(this.http.get<{ key: string }>('/api/push/key'));
      const sub = (await reg.pushManager.getSubscription()) ?? (await reg.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: keyBytes(key) }));
      await firstValueFrom(this.http.post('/api/push/subscribe', sub.toJSON()));
      this.state.set('on');
    } catch {
      this.error.set('Non sono riuscito ad attivare gli avvisi: riprova tra poco.');
    } finally {
      this.busy.set(false);
    }
  }

  protected async turnOff(): Promise<void> {
    this.busy.set(true);
    try {
      const sub = await (await this.registration())?.pushManager.getSubscription();
      if (sub) {
        await firstValueFrom(this.http.post('/api/push/unsubscribe', { endpoint: sub.endpoint }));
        await sub.unsubscribe();
      }
      this.state.set('off');
    } finally {
      this.busy.set(false);
    }
  }
}
