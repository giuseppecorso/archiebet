import { Component, signal } from '@angular/core';

const DISMISSED = 'archiebet.install-dismissed';

/** Evento di Chrome/Edge su Android: permette di aprire la finestra di installazione con un tasto nostro */
interface InstallPrompt extends Event {
  prompt(): Promise<void>;
  userChoice: Promise<{ outcome: 'accepted' | 'dismissed' }>;
}

/**
 * "Installa ArchieBet sul telefono": su Android un tasto apre l'installazione del browser; su iPhone (dove i siti non
 * possono farlo) spiega i due tocchi. Non compare se l'app è già installata o se l'utente l'ha chiuso.
 */
@Component({
  selector: 'ab-install-banner',
  template: `
    @if (mode(); as m) {
      <div class="install" role="region" aria-label="Installa ArchieBet">
        <img src="icon-192.png" alt="" width="40" height="40" />
        @if (m === 'android') {
          <span>Metti ArchieBet nella schermata Home: si apre come un'app.</span>
          <button type="button" class="btn-primary" (click)="install()">Installa</button>
        } @else {
          <span>Per averla come app: tocca <strong>Condividi</strong> <span aria-hidden="true">⎋</span> e poi <strong>"Aggiungi alla schermata Home"</strong>.</span>
        }
        <button type="button" class="x" aria-label="Non ora" (click)="dismiss()">✕</button>
      </div>
    }
  `,
  styles: `
    .install { display: flex; align-items: center; gap: 10px; margin: 0 0 12px; padding: 8px 10px; font-size: 13px; background: var(--panel); border: 1px solid var(--amber); border-radius: 8px; }
    .install img { flex: none; border-radius: 9px; }
    .install span { flex: 1; }
    .install .btn-primary { min-height: 34px; padding: 4px 14px; }
    .x { flex: none; min-width: 32px; min-height: 32px; font-size: 15px; color: var(--muted); background: transparent; border: 0; cursor: pointer; }
  `,
})
export class InstallBanner {
  protected readonly mode = signal<'android' | 'ios' | null>(null);
  private prompt: InstallPrompt | null = null;

  constructor() {
    if (typeof window === 'undefined' || this.dismissed() || this.installed()) return;
    window.addEventListener('beforeinstallprompt', (e) => {
      e.preventDefault(); // niente mini-barra del browser: il tasto è il nostro
      this.prompt = e as InstallPrompt;
      this.mode.set('android');
    });
    window.addEventListener('appinstalled', () => this.mode.set(null));
    const ua = navigator.userAgent;
    if (/iPhone|iPad/.test(ua) && /Safari/.test(ua) && !/CriOS|FxiOS|EdgiOS/.test(ua)) this.mode.set('ios');
  }

  protected async install(): Promise<void> {
    if (!this.prompt) return;
    await this.prompt.prompt();
    const { outcome } = await this.prompt.userChoice;
    this.prompt = null;
    if (outcome === 'accepted') this.mode.set(null);
  }

  protected dismiss(): void {
    this.mode.set(null);
    try {
      localStorage.setItem(DISMISSED, '1');
    } catch {
      // senza memoria del browser ricomparirà alla prossima visita
    }
  }

  private dismissed(): boolean {
    try {
      return localStorage.getItem(DISMISSED) === '1';
    } catch {
      return false;
    }
  }

  private installed(): boolean {
    const standalone = typeof matchMedia === 'function' && matchMedia('(display-mode: standalone)').matches;
    return standalone || (navigator as Navigator & { standalone?: boolean }).standalone === true;
  }
}
