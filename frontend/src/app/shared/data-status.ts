import { HttpClient, httpResource } from '@angular/common/http';
import { Component, computed, effect, inject, signal } from '@angular/core';
import { ago, dayLabel } from '../core/format';
import { DataStatus } from '../core/status';

/** Oltre questo tempo senza un aggiornamento riuscito, la fonte si segnala in ambra */
const STALE_HOURS = 12;

/**
 * Barra "Stato dei dati": quando è stato aggiornato tutto, fin dove arrivano i risultati di ogni campionato,
 * quante partite hanno la previsione di Archie. Pulsante "Aggiorna ora" per non aspettare il giro automatico.
 */
@Component({
  selector: 'ab-data-status',
  template: `
    @if (status.value(); as s) {
      <section class="bar" aria-label="Stato dei dati">
        <span class="title head">Dati</span>
        <span [class.warn]="stale()">aggiornati {{ lastUpdate() }}</span>
        @for (c of s.competitions; track c.competition.code) {
          @if (c.next_match_at || c.awaiting_results) {
            <span class="comp" [class.warn]="c.awaiting_results > 0">
              {{ c.competition.name }}: risultati fino a {{ c.last_result_at ? day(c.last_result_at) : '–' }}
              @if (c.awaiting_results > 0) {
                ({{ c.awaiting_results }} in arrivo)
              }
            </span>
          }
        }
        <span>previsioni {{ s.upcoming_with_prediction }}/{{ s.upcoming }}</span>
        <button type="button" class="refresh" [disabled]="s.syncing || starting()" (click)="refresh()">
          {{ s.syncing || starting() ? 'Aggiornamento…' : 'Aggiorna ora' }}
        </button>
        <button type="button" class="link" [attr.aria-expanded]="open()" (click)="open.set(!open())">
          {{ open() ? 'Nascondi' : 'Dettagli' }}
        </button>
      </section>
      @if (open()) {
        <ul class="details" aria-label="Fonti dei dati">
          @for (src of s.sources; track src.source) {
            <li>
              <strong>{{ src.label }}</strong>:
              @if (!src.configured) {
                non configurata
              } @else {
                ultimo aggiornamento riuscito {{ ago(src.last_ok_at) }}
                @if (src.last_run_ok === false) {
                  <span class="warn">· l'ultimo tentativo non è riuscito</span>
                } @else if (src.message) {
                  · {{ src.message }}
                }
              }
            </li>
          }
        </ul>
      }
    }
  `,
  styles: `
    .bar {
      display: flex; flex-wrap: wrap; align-items: center; gap: 6px 14px; margin-bottom: 14px; padding: 8px 14px;
      font-size: 12px; color: var(--muted); background: var(--panel); border: 1px solid var(--line); border-radius: 6px;
    }
    .head { font-size: 16px; color: var(--text-2); }
    .warn { color: var(--amber); }
    .refresh, .link {
      min-height: 30px; padding: 2px 10px; font: inherit; font-size: 12px; font-weight: 600; cursor: pointer;
      border-radius: 4px; background: transparent;
    }
    .refresh { margin-left: auto; color: var(--amber); border: 1px solid var(--line-strong); }
    .refresh:hover:not(:disabled) { border-color: var(--amber); }
    .refresh:disabled { color: var(--muted); cursor: default; }
    .link { color: var(--muted); border: 0; text-decoration: underline; }
    .details { margin: -6px 0 14px; padding: 8px 14px 8px 30px; font-size: 12px; color: var(--muted); }
    .details strong { color: var(--text-2); font-weight: 600; }
  `,
})
export class DataStatusBar {
  private readonly http = inject(HttpClient);
  protected readonly status = httpResource<DataStatus>(() => '/api/status');
  protected readonly open = signal(false);
  protected readonly starting = signal(false);
  protected readonly ago = ago;
  protected readonly day = dayLabel;

  /** L'aggiornamento riuscito più vecchio tra le fonti configurate: è lui che dice quanto sono freschi i dati */
  private readonly oldestOk = computed(() => {
    const sources = this.status.value()?.sources.filter((s) => s.configured) ?? [];
    if (!sources.length || sources.some((s) => !s.last_ok_at)) return null;
    return sources.map((s) => s.last_ok_at as string).sort()[0];
  });
  protected readonly lastUpdate = computed(() => ago(this.oldestOk()));
  protected readonly stale = computed(() => {
    const oldest = this.oldestOk();
    return !oldest || Date.now() - new Date(oldest).getTime() > STALE_HOURS * 3600_000;
  });

  constructor() {
    // Mentre l'aggiornamento è in corso ricontrolla ogni 3 secondi; alla fine ricarica la pagina dei dati
    effect((onCleanup) => {
      if (!this.status.value()?.syncing && !this.starting()) return;
      const timer = setInterval(() => this.status.reload(), 3000);
      onCleanup(() => clearInterval(timer));
    });
  }

  protected refresh(): void {
    this.starting.set(true);
    this.http.post<{ started: boolean }>('/api/status/refresh', {}).subscribe({
      next: () => {
        this.status.reload();
        // Il server segna "in corso" appena il lavoro parte: dopo il primo controllo decide lui
        setTimeout(() => this.starting.set(false), 3500);
      },
      error: () => this.starting.set(false),
    });
  }
}
