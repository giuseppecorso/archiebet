import { httpResource } from '@angular/common/http';
import { Component, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { SlipService } from '../../core/slip';
import { odds, pct } from '../../core/format';
import { StrategiesOut, SystemRow, systemRows } from '../../core/strategies';
import { StudyLeg, StudyMultiple } from '../../core/study';

type Level = 'cauto' | 'equilibrato' | 'rischioso';
type When = 'today' | 'tomorrow' | '3days';

/** La quota con cui si gioca un pronostico: la migliore dei bookmaker, la media, o quella stimata da Archie. */
export function legOdds(l: StudyLeg): number {
  const best = Math.max(0, ...Object.values(l.prices ?? {}));
  return +(best > 1 ? best : (l.avg_price ?? 1 / l.p_archie)).toFixed(2);
}

/** Scheda Strategie (D189, D194): costruisci un sistema sui pronostici di Archie; le strategie famose messe alla prova. */
@Component({
  selector: 'ab-strategies',
  imports: [FormsModule],
  template: `
    <section class="panel box" aria-labelledby="h-system">
      <h2 id="h-system" class="box-title">Costruisci a sistema</h2>
      <p class="muted small">Archie sceglie le partite; tu scegli quante devono uscire. Meno ne servono, più spesso vinci, ma vinci meno.</p>

      <div class="controls">
        <label>Livello
          <select [ngModel]="level()" (ngModelChange)="level.set($event)">
            <option value="cauto">Cauto</option>
            <option value="equilibrato">Equilibrato</option>
            <option value="rischioso">Rischioso</option>
          </select>
        </label>
        <label>Partite
          <select [ngModel]="legs()" (ngModelChange)="legs.set(+$event)">
            @for (n of [3, 4, 5, 6]; track n) { <option [value]="n">{{ n }}</option> }
          </select>
        </label>
        <label>Quando
          <select [ngModel]="when()" (ngModelChange)="when.set($event)">
            <option value="today">Oggi</option>
            <option value="tomorrow">Domani</option>
            <option value="3days">Prossimi 3 giorni</option>
          </select>
        </label>
        <label>Puntata (€)
          <input type="number" min="1" step="1" [ngModel]="stake()" (ngModelChange)="stake.set(+$event || 0)" />
        </label>
      </div>

      @if (picks.isLoading()) {
        <p class="muted small">Archie sceglie le partite…</p>
      } @else if (picks.error()) {
        <p class="muted small">Adesso non riesco a scegliere le partite: riprova tra poco.</p>
      } @else if (picks.value(); as r) {
        @if (r.legs.length < 3) {
          <p class="muted small">Troppe poche partite per un sistema in questo periodo: prova "Prossimi 3 giorni".</p>
        } @else {
          <ol class="legs">
            @for (l of r.legs; track l.match.id) {
              <li>
                <span class="what"><b>{{ l.event }}</b><small>{{ l.match.home.name }} – {{ l.match.away.name }}</small></span>
                <span class="nums"><span class="led">{{ fmt.odds(legOdds(l)) }}</span><small>{{ fmt.pct(l.p_archie) }}</small></span>
              </li>
            }
          </ol>

          <table class="systems">
            <thead>
              <tr><th>Ne devono uscire</th><th>Giocate</th><th>Probabilità di vincere</th><th>Vincita minima</th><th>Vincita massima</th></tr>
            </thead>
            <tbody>
              @for (s of rows(); track s.k) {
                <tr [class.on]="chosen() === s.k" (click)="chosen.set(s.k)" tabindex="0" (keydown.enter)="chosen.set(s.k)">
                  <td>{{ s.k === r.legs.length ? 'tutte (multipla)' : s.k + ' su ' + r.legs.length }}</td>
                  <td>{{ s.combos }} da {{ money(s.perBet) }}</td>
                  <td class="led">{{ fmt.pct(s.pWin) }}</td>
                  <td>{{ money(s.min) }}</td>
                  <td>{{ money(s.max) }}</td>
                </tr>
              }
            </tbody>
          </table>
          <button type="button" class="btn-primary" [disabled]="!chosenRow()" (click)="play(r)">
            Metti in schedina{{ chosenRow() ? ' (' + label(chosenRow()!, r.legs.length) + ')' : '' }}
          </button>
        }
      }
    </section>

    <section class="panel box" aria-labelledby="h-market">
      <h2 id="h-market" class="box-title">Strategie del mercato alla prova</h2>
      @if (results.value(); as d) {
        <p class="muted small">
          Le strategie più famose, provate da Archie su {{ (d.tuning?.matches ?? 0) + (d.confirm?.matches ?? 0) }} partite di 10 campionati
          (regole fissate prima di guardare i risultati). I numeri sono quelli delle stagioni di controllo {{ d.confirm?.from }}–{{ d.confirm?.to }}.
        </p>
        <ul class="cards">
          @for (s of d.strategies; track s.key) {
            <li class="card" [class.good]="s.passed">
              <div class="card-head">
                <b>{{ s.name }}</b>
                <span class="tag" [class.pass]="s.passed">{{ s.passed ? 'Funziona' : 'Non funziona' }}</span>
              </div>
              <p class="small muted">{{ s.how }}</p>
              <p class="big">Vince <b class="led">{{ hits(s.confirm.hit_rate) }}</b> volte su 100 <span class="muted small">a quota media {{ fmt.odds(s.confirm.avg_price) }}</span></p>
              <p class="small">
                Per ogni 100 € giocati tornano <b>{{ back(s.confirm.roi?.mean) }} €</b>
                <span class="muted">· {{ s.confirm.n }} giocate · quota {{ s.price }}</span>
              </p>
              @if (s.beats_close) {
                <p class="small note">Batte la quota di chiusura: segnale buono, ma le giocate sono ancora poche per esserne sicuri.</p>
              }
            </li>
          }
        </ul>
      } @else if (results.isLoading()) {
        <p class="muted small">Carico…</p>
      }
    </section>
  `,
  styles: `
    :host { display: grid; gap: 12px; }
    .box { padding: 16px 18px; }
    .box-title { margin: 0 0 4px; font: 700 18px var(--font-title); text-transform: uppercase; letter-spacing: 0.04em; }
    .controls { display: flex; flex-wrap: wrap; gap: 10px; margin: 12px 0; }
    .controls label { display: grid; gap: 4px; font-size: 12px; color: var(--muted); }
    .controls select, .controls input { min-height: 38px; min-width: 110px; padding: 6px 10px; color: var(--text); background: var(--bg); border: 1px solid var(--line-strong); border-radius: 8px; }
    .legs { margin: 0 0 12px; padding: 0; list-style: none; }
    .legs li { display: flex; gap: 10px; justify-content: space-between; padding: 8px 0; border-top: 1px solid var(--line-row); }
    .what { display: grid; } .what small, .nums small { color: var(--muted); font-size: 12px; }
    .nums { display: grid; text-align: right; }
    .systems { width: 100%; border-collapse: collapse; font-size: 13px; margin-bottom: 12px; }
    .systems th { text-align: left; font-weight: 600; color: var(--muted); font-size: 11px; padding: 6px 4px; }
    .systems td { padding: 9px 4px; border-top: 1px solid var(--line-row); }
    .systems tr { cursor: pointer; }
    .systems tr.on td { background: rgba(255, 143, 38, 0.12); }
    @media (max-width: 520px) { .systems th:nth-child(4), .systems td:nth-child(4) { display: none; } }
    .cards { display: grid; grid-template-columns: repeat(auto-fill, minmax(260px, 1fr)); gap: 10px; margin: 12px 0 0; padding: 0; list-style: none; }
    .card { padding: 12px 14px; border: 1px solid var(--line); border-radius: 12px; background: var(--panel-head); }
    .card.good { border-color: var(--win); }
    .card p { margin: 6px 0 0; }
    .card-head { display: flex; justify-content: space-between; gap: 8px; align-items: baseline; }
    .tag { flex: none; padding: 2px 8px; border-radius: 999px; font-size: 11px; font-weight: 700; color: var(--loss); border: 1px solid var(--loss); }
    .tag.pass { color: var(--win); border-color: var(--win); }
    .big { font-size: 15px; }
    .note { color: var(--win); }
  `,
})
export class Strategies {
  private readonly slip = inject(SlipService);
  protected readonly fmt = { odds, pct };
  protected readonly legOdds = legOdds;

  protected readonly level = signal<Level>('equilibrato');
  protected readonly legs = signal(4);
  protected readonly when = signal<When>('3days');
  protected readonly stake = signal(10);
  protected readonly chosen = signal<number | null>(null);

  protected readonly picks = httpResource<StudyMultiple>(() => `/api/study/multiple?level=${this.level()}&legs=${this.legs()}&horizon=${this.when()}`);
  protected readonly results = httpResource<StrategiesOut>(() => '/api/strategies');

  protected readonly rows = computed<SystemRow[]>(() => {
    const r = this.picks.value();
    return r ? systemRows(r.legs.map((l) => ({ p: l.p_archie, odds: legOdds(l) })), Math.max(this.stake(), 0)) : [];
  });
  protected readonly chosenRow = computed(() => this.rows().find((r) => r.k === this.chosen()) ?? null);

  protected money(v: number): string {
    return v.toLocaleString('it-IT', { style: 'currency', currency: 'EUR' });
  }

  protected hits(rate: number | null): string {
    return rate == null ? '–' : Math.round(rate * 100).toString();
  }

  /** Quanto torna su 100 € giocati (rendimento 0 = 100 €) */
  protected back(roi: number | null | undefined): string {
    return roi == null ? '–' : Math.round(100 * (1 + roi)).toString();
  }

  protected label(row: SystemRow, n: number): string {
    return row.k === n ? 'multipla' : `sistema ${row.k} su ${n}`;
  }

  protected play(r: StudyMultiple): void {
    const row = this.chosenRow();
    if (!row) return;
    this.slip.fill(
      r.legs.map((l) => ({ match: l.match, market: l.market, pick: l.selection, odds: legOdds(l), bookmaker: null })),
      row.k === r.legs.length ? null : row.k,
    );
    this.slip.stake.set(String(this.stake()));
  }
}
