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
        <span class="fresh" [class.warn]="stale()">aggiornati {{ lastUpdate() }}</span>
        @for (f of failing(); track f.source) {
          <span class="warn small">{{ f.label }} ferme a {{ ago(f.last_ok_at) }}</span>
        }
        <!-- Tabellone che scorre: i campionati passano da destra a sinistra (fermo col mouse sopra o con "riduci movimento") -->
        <div class="ticker" aria-label="Risultati per campionato">
          <div class="track">
            @for (copy of [0, 1]; track copy) {
              <div class="lap" [attr.aria-hidden]="copy === 1">
                @for (c of shown(); track c.competition.code) {
                  <span class="comp" [class.late]="c.awaiting_results > 0">
                    <span class="dot" aria-hidden="true"></span>
                    <strong>{{ c.competition.name }}</strong> risultati fino a {{ c.last_result_at ? day(c.last_result_at) : '–' }}
                    @if (c.awaiting_results > 0) {
                      · {{ c.awaiting_results }} in arrivo
                    }
                  </span>
                }
              </div>
            }
          </div>
        </div>
        <span class="small">previsioni {{ s.upcoming_with_prediction }}/{{ s.upcoming }}</span>
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
      display: flex; align-items: center; gap: 6px 14px; margin-bottom: 14px; padding: 8px 14px;
      font-size: 12px; color: var(--muted); background: var(--panel); border: 1px solid var(--line); border-radius: 6px;
    }
    @media (max-width: 860px) { .bar { flex-wrap: wrap; } .ticker { order: 9; flex-basis: 100%; } }
    .head { font-size: 16px; color: var(--amber); }
    .fresh, .small { white-space: nowrap; }
    .ticker {
      flex: 1; min-width: 0; overflow: hidden; padding: 4px 0; background: var(--bg-ticker); border-radius: 4px;
      mask-image: linear-gradient(90deg, transparent, #000 4%, #000 96%, transparent);
    }
    .track { display: flex; width: max-content; animation: scroll 60s linear infinite; }
    .ticker:hover .track { animation-play-state: paused; }
    @media (prefers-reduced-motion: reduce) { .track { animation: none; } .ticker { overflow-x: auto; } }
    @keyframes scroll { to { transform: translateX(-50%); } }
    .lap { display: flex; gap: 26px; padding-right: 26px; }
    .comp { white-space: nowrap; color: var(--text-2); }
    .comp strong { color: var(--text); font-weight: 600; }
    .dot { display: inline-block; width: 7px; height: 7px; margin-right: 6px; border-radius: 50%; background: var(--value); box-shadow: 0 0 6px var(--value); }
    .comp.late .dot { background: var(--amber); box-shadow: 0 0 6px var(--amber); }
    .comp.late { color: var(--amber); }
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

  private readonly configured = computed(() => this.status.value()?.sources.filter((s) => s.configured) ?? []);
  /** Ultimo giro di aggiornamento (anche se una fonte non ha risposto: quella si segnala a parte) */
  private readonly lastRun = computed(() => {
    const runs = this.configured().map((s) => s.last_run_at).filter((t): t is string => !!t);
    return runs.length ? runs.sort().at(-1)! : null;
  });
  protected readonly lastUpdate = computed(() => ago(this.lastRun()));
  protected readonly stale = computed(() => {
    const last = this.lastRun();
    return !last || Date.now() - new Date(last).getTime() > STALE_HOURS * 3600_000;
  });
  /** Fonti il cui ultimo tentativo non è riuscito */
  protected readonly failing = computed(() => this.configured().filter((s) => s.last_run_ok === false));
  /** Campionati con partite in programma o risultati attesi */
  protected readonly shown = computed(() =>
    (this.status.value()?.competitions ?? []).filter((c) => c.next_match_at || c.awaiting_results),
  );

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
