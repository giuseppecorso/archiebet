import { httpResource } from '@angular/common/http';
import { Component, WritableSignal, computed, signal } from '@angular/core';
import { Competition } from '../../core/football';
import { MultiplesOut } from '../../core/multiple';
import { MultipleView } from '../../shared/multiple-view';

type Profile = 'tranquilla' | 'equilibrata' | 'coraggiosa';

const PROFILES: { key: Profile; label: string; hint: string }[] = [
  { key: 'tranquilla', label: 'Più tranquilla', hint: 'partite al 70% o più, quota 2–3,5' },
  { key: 'equilibrata', label: 'Equilibrata', hint: 'partite al 65% o più, quota 3–5' },
  { key: 'coraggiosa', label: 'Più coraggiosa', hint: 'partite al 45% o più, quota 5–15, scelta per valore' },
];
const MARKETS: [string, string][] = [
  ['1X2', '1X2'],
  ['DC', 'Doppia chance'],
  ['OU2.5', 'Under/Over 2.5'],
  ['GG', 'Goal/NoGoal'],
];

/** "Archie, fammi una multipla" (specifiche sezione 5): varianti della multipla del giorno, calcolate dal codice. */
@Component({
  selector: 'ab-generator',
  imports: [MultipleView],
  template: `
    <section class="panel box form" aria-labelledby="gen-title">
      <h2 id="gen-title" class="title">Archie, fammi una multipla</h2>

      <fieldset>
        <legend>Rischio</legend>
        <div class="chips">
          @for (p of profiles; track p.key) {
            <button type="button" class="chip" [class.on]="profile() === p.key" [attr.aria-pressed]="profile() === p.key"
                    (click)="profile.set(p.key)" [title]="p.hint">{{ p.label }}</button>
          }
        </div>
        <p class="hint muted small">{{ hint() }}</p>
      </fieldset>

      <div class="row">
        <label>Partite
          <select [value]="legs()" (change)="legs.set(+$any($event.target).value)">
            @for (n of [2, 3, 4, 5, 6]; track n) { <option [value]="n" [selected]="n === legs()">{{ n }}</option> }
          </select>
        </label>
        <label>Quando
          <select [value]="horizon()" (change)="horizon.set($any($event.target).value)">
            <option value="today" [selected]="horizon() === 'today'">Oggi</option>
            <option value="week" [selected]="horizon() === 'week'">Prossimi 7 giorni</option>
          </select>
        </label>
        <label>Importo €
          <input type="number" min="1" max="1000" step="1" [value]="stake()" (input)="stake.set(+$any($event.target).value || 10)" />
        </label>
      </div>

      <fieldset>
        <legend>Mercati</legend>
        <div class="chips">
          @for (m of markets; track m[0]) {
            <button type="button" class="chip" [class.on]="isOn(selectedMarkets(), m[0])" [attr.aria-pressed]="isOn(selectedMarkets(), m[0])"
                    (click)="toggle(selectedMarkets, m[0])">{{ m[1] }}</button>
          }
        </div>
      </fieldset>

      <fieldset>
        <legend>Campionati</legend>
        <div class="chips">
          @for (c of competitions.value(); track c.code) {
            <button type="button" class="chip" [class.on]="isOn(selectedComps(), c.code)" [attr.aria-pressed]="isOn(selectedComps(), c.code)"
                    (click)="toggle(selectedComps, c.code)">{{ c.name }}</button>
          }
        </div>
        <p class="hint muted small">Nessun campionato scelto = tutti.</p>
      </fieldset>
    </section>

    <section class="panel box result" aria-live="polite" aria-label="Multipla proposta">
      @if (result.value(); as d) {
        <ab-multiple-view [data]="d" [stake]="stake()"
          empty="Con queste scelte non c'è una multipla sensata. Prova meno partite, più mercati, un altro rischio o tutta la settimana." />
      } @else if (result.isLoading()) {
        <p class="muted small">Archie sta provando le combinazioni…</p>
      } @else if (result.error()) {
        <p class="warn">Il generatore non risponde: controlla che il backend sia acceso.</p>
      }
    </section>
  `,
  styles: `
    :host { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); gap: 20px; align-items: start; }
    @media (max-width: 860px) { :host { grid-template-columns: 1fr; } }
    .box { padding: 16px 20px; }
    h2 { margin: 0 0 12px; font-size: 20px; color: var(--amber); }
    fieldset { margin: 0 0 14px; padding: 0; border: 0; }
    legend { margin-bottom: 6px; font-size: 11px; font-weight: 700; letter-spacing: 1px; color: var(--muted); text-transform: uppercase; }
    .chips { display: flex; flex-wrap: wrap; gap: 6px; }
    .chip {
      min-height: 32px; padding: 2px 12px; font: inherit; font-size: 12px; font-weight: 600; color: var(--text-2);
      background: transparent; border: 1px solid var(--line-strong); border-radius: 16px; cursor: pointer;
    }
    .chip.on { color: var(--amber); background: var(--chip); border-color: var(--amber); }
    .hint { margin: 6px 0 0; }
    .row { display: flex; flex-wrap: wrap; gap: 12px; margin-bottom: 14px; }
    label { display: flex; flex-direction: column; gap: 4px; font-size: 11px; font-weight: 700; letter-spacing: 1px; color: var(--muted); text-transform: uppercase; }
    select, input {
      min-height: 34px; padding: 2px 8px; font: inherit; font-size: 14px; color: var(--text);
      background: var(--bg-deep); border: 1px solid var(--line-strong); border-radius: 4px;
    }
    input { width: 90px; }
    .warn { color: var(--loss); }
  `,
})
export class Generator {
  protected readonly profiles = PROFILES;
  protected readonly markets = MARKETS;
  protected readonly profile = signal<Profile>('equilibrata');
  protected readonly legs = signal(4);
  protected readonly horizon = signal<'today' | 'week'>('week');
  protected readonly stake = signal(10);
  protected readonly selectedMarkets = signal<string[]>(MARKETS.map((m) => m[0]));
  protected readonly selectedComps = signal<string[]>([]);

  protected readonly competitions = httpResource<Competition[]>(() => '/api/competitions', { defaultValue: [] });
  protected readonly hint = computed(() => PROFILES.find((p) => p.key === this.profile())!.hint);

  protected readonly result = httpResource<MultiplesOut>(() => {
    const params = new URLSearchParams({ horizon: this.horizon(), profile: this.profile(), legs: String(this.legs()) });
    if (this.selectedMarkets().length < MARKETS.length) params.set('markets', this.selectedMarkets().join(','));
    if (this.selectedComps().length) params.set('competitions', this.selectedComps().join(','));
    return this.selectedMarkets().length ? `/api/picks/multiple?${params}` : undefined;
  });

  protected isOn(list: string[], key: string): boolean {
    return list.includes(key);
  }

  protected toggle(list: WritableSignal<string[]>, key: string): void {
    list.update((l) => (l.includes(key) ? l.filter((k) => k !== key) : [...l, key]));
  }
}
