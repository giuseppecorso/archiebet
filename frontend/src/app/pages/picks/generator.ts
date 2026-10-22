import { httpResource } from '@angular/common/http';
import { Component, WritableSignal, computed, signal } from '@angular/core';
import { Competition } from '../../core/football';
import { Horizon, MultiplesOut } from '../../core/multiple';
import { Review } from '../../core/review';
import { MultipleView } from '../../shared/multiple-view';
import { RouterLink } from '@angular/router';

type Profile = 'molto tranquilla' | 'tranquilla' | 'equilibrata' | 'coraggiosa' | 'spericolata' | 'caccia al clv' | 'personalizzata';

/** Livelli di rischio (D130), dal più prudente al più spinto, più quello personalizzato */
const PROFILES: { key: Profile; label: string; hint: string }[] = [
  { key: 'molto tranquilla', label: 'Molto tranquilla', hint: "partite all'80% o più, quota totale 1,5–2,5" },
  { key: 'tranquilla', label: 'Tranquilla', hint: 'partite al 70% o più, quota 2–3,5' },
  { key: 'equilibrata', label: 'Equilibrata', hint: 'partite al 65% o più, quota 3–5' },
  { key: 'coraggiosa', label: 'Coraggiosa', hint: 'partite al 45% o più, quota 5–15, scelta per valore' },
  { key: 'spericolata', label: 'Spericolata', hint: 'partite al 30% o più, quota 15–60, scelta per valore: vince raramente' },
  {
    key: 'caccia al clv',
    label: 'Caccia al CLV',
    hint: "solo quote sopra il giusto secondo la regola delle Occasioni (l'unica provata sul passato), scelte per CLV atteso; se non bastano, meno partite",
  },
  { key: 'personalizzata', label: 'Personalizzata', hint: 'scegli tu probabilità minima per partita, quota totale e cosa privilegiare' },
];
const HORIZONS: [Horizon, string][] = [
  ['today', 'Oggi'],
  ['tomorrow', 'Domani'],
  ['2days', 'Oggi e domani'],
  ['3days', 'Prossimi 3 giorni'],
  ['week', 'Prossimi 7 giorni'],
  ['range', 'Scegli le date…'],
];
/** Le quote arrivano fino a 7 giorni prima */
const MAX_DAYS_AHEAD = 7;

/** Giorno locale in formato AAAA-MM-GG, spostato di "offset" giorni da oggi */
function isoDay(offset = 0): string {
  const d = new Date();
  d.setDate(d.getDate() + offset);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
}

/** Mercati e famiglie (angoli e cartellini con tutte le linee, D131) */
const MARKETS: [string, string][] = [
  ['1X2', '1X2'],
  ['DC', 'Doppia chance'],
  ['OU0.5', 'U/O 0.5'],
  ['OU1.5', 'U/O 1.5'],
  ['OU2.5', 'U/O 2.5'],
  ['OU3.5', 'U/O 3.5'],
  ['OU4.5', 'U/O 4.5'],
  ['GG', 'Goal/NoGoal'],
  ['gol squadra', 'Gol squadra'],
  ['angoli', 'Angoli'],
  ['cartellini', 'Cartellini'],
];

/** "Archie, fammi una multipla" (specifiche sezione 5): varianti della multipla del giorno, calcolate dal codice. */
@Component({
  selector: 'ab-generator',
  imports: [MultipleView, RouterLink],
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
        @if (track(); as t) {
          <p class="hint small track">
            Pagella delle ultime 4 settimane: vinte <strong>{{ t.won }}</strong> su {{ t.played }} (Archie ne attendeva {{ t.expected.toFixed(1) }}).
            <a [routerLink]="[]" [queryParams]="{ tab: 'pagella' }">Vedi la pagella</a>
          </p>
        }
        @if (profile() === 'personalizzata') {
          <div class="row custom">
            <label>Ogni partita almeno
              <span class="inline"><input type="range" min="20" max="95" step="5" [value]="minProb()" (input)="minProb.set(+$any($event.target).value)" />
                <strong class="led">{{ minProb() }}%</strong></span>
            </label>
            <label>Quota totale da
              <input type="number" min="1.2" max="200" step="0.5" [value]="minTotal()" (change)="minTotal.set(+$any($event.target).value || 2)" />
            </label>
            <label>a
              <input type="number" min="1.2" max="200" step="0.5" [value]="maxTotal()" (change)="maxTotal.set(+$any($event.target).value || 6)" />
            </label>
            <label>Privilegia
              <select [value]="by()" (change)="by.set($any($event.target).value)">
                <option value="probabilita" [selected]="by() === 'probabilita'">vincere più spesso</option>
                <option value="valore" [selected]="by() === 'valore'">il valore atteso</option>
              </select>
            </label>
          </div>
        }
      </fieldset>

      <div class="row">
        <label>Partite
          <select [value]="legs()" (change)="legs.set(+$any($event.target).value)">
            @for (n of [2, 3, 4, 5, 6]; track n) { <option [value]="n" [selected]="n === legs()">{{ n }}</option> }
          </select>
        </label>
        <label>Quando
          <select [value]="horizon()" (change)="horizon.set($any($event.target).value)">
            @for (h of horizons; track h[0]) { <option [value]="h[0]" [selected]="horizon() === h[0]">{{ h[1] }}</option> }
          </select>
        </label>
        @if (horizon() === 'range') {
          <label>Dal
            <input type="date" class="day" [min]="firstDay" [max]="lastDay" [value]="dateFrom()"
                   (change)="setFrom($any($event.target).value)" />
          </label>
          <label>Al
            <input type="date" class="day" [min]="dateFrom()" [max]="lastDay" [value]="dateTo()"
                   (change)="dateTo.set($any($event.target).value || dateFrom())" />
          </label>
        }
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
          empty="Con queste scelte non c'è una multipla sensata." />
      } @else if (result.isLoading()) {
        <p class="muted small">Archie sta provando le combinazioni…</p>
      } @else if (result.error()) {
        <p class="warn">Il generatore non risponde: controlla che il backend sia acceso.</p>
      }
    </section>
  `,
  styles: `
    :host { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); gap: 12px; align-items: start; }
    @media (max-width: 860px) { :host { grid-template-columns: 1fr; } }
    .box { padding: 10px 14px; }
    h2 { margin: 0 0 12px; font-size: 16px; color: var(--amber); }
    fieldset { margin: 0 0 10px; padding: 0; border: 0; }
    legend { margin-bottom: 6px; font-size: 11px; font-weight: 700; letter-spacing: 1px; color: var(--muted); text-transform: uppercase; }
    .chips { display: flex; flex-wrap: wrap; gap: 4px; }
    .chip {
      min-height: 26px; padding: 1px 10px; font: inherit; font-size: 11.5px; font-weight: 600; color: var(--text-2);
      background: transparent; border: 1px solid var(--line-strong); border-radius: 13px; cursor: pointer;
    }
    .chip.on { color: var(--amber); background: var(--chip); border-color: var(--amber); }
    .hint { margin: 6px 0 0; }
    .track { color: var(--text-2); }
    .row { display: flex; flex-wrap: wrap; gap: 12px; margin-bottom: 14px; }
    label { display: flex; flex-direction: column; gap: 4px; font-size: 11px; font-weight: 700; letter-spacing: 1px; color: var(--muted); text-transform: uppercase; }
    select, input {
      min-height: 30px; padding: 2px 8px; font: inherit; font-size: 13px; color: var(--text);
      background: var(--bg-deep); border: 1px solid var(--line-strong); border-radius: 4px;
    }
    input { width: 90px; }
    .custom { margin: 10px 0 0; }
    .inline { display: flex; align-items: center; gap: 8px; }
    input[type='range'] { width: 150px; accent-color: var(--amber); }
    input.day { width: 150px; color-scheme: dark; }
    .warn { color: var(--loss); }
  `,
})
export class Generator {
  protected readonly profiles = PROFILES;
  protected readonly markets = MARKETS;
  protected readonly horizons = HORIZONS;
  protected readonly firstDay = isoDay();
  protected readonly lastDay = isoDay(MAX_DAYS_AHEAD);
  protected readonly profile = signal<Profile>('equilibrata');
  /** Profilo personalizzato */
  protected readonly minProb = signal(60);
  protected readonly minTotal = signal(2);
  protected readonly maxTotal = signal(6);
  protected readonly by = signal<'probabilita' | 'valore'>('probabilita');
  protected readonly legs = signal(4);
  protected readonly horizon = signal<Horizon>('week');
  protected readonly dateFrom = signal(isoDay());
  protected readonly dateTo = signal(isoDay(2));
  protected readonly stake = signal(10);
  protected readonly selectedMarkets = signal<string[]>(MARKETS.map((m) => m[0]));
  protected readonly selectedComps = signal<string[]>([]);

  protected readonly competitions = httpResource<Competition[]>(() => '/api/competitions', { defaultValue: [] });
  protected readonly hint = computed(() => PROFILES.find((p) => p.key === this.profile())!.hint);
  /** Come è andato questo livello di rischio nelle ultime 4 settimane (pagella D132) */
  private readonly review = httpResource<Review>(() => '/api/lab/review');
  protected readonly track = computed(() => {
    const weeks = this.review.value()?.weeks.slice(-4) ?? [];
    const rows = weeks.map((w) => w.multiples.base[this.profile()]).filter((t) => !!t);
    if (!rows.length) return null;
    return rows.reduce((a, t) => ({ played: a.played + t.played, won: a.won + t.won, expected: a.expected + t.expected }), { played: 0, won: 0, expected: 0 });
  });

  protected readonly result = httpResource<MultiplesOut>(() => {
    const params = new URLSearchParams({ horizon: this.horizon(), profile: this.profile(), legs: String(this.legs()) });
    if (this.horizon() === 'range') {
      params.set('date_from', this.dateFrom());
      params.set('date_to', this.dateTo());
    }
    if (this.selectedMarkets().length < MARKETS.length) params.set('markets', this.selectedMarkets().join(','));
    if (this.profile() === 'personalizzata') {
      params.set('min_probability', String(this.minProb() / 100));
      params.set('min_total', String(this.minTotal()));
      params.set('max_total', String(this.maxTotal()));
      params.set('by', this.by());
    }
    if (this.selectedComps().length) params.set('competitions', this.selectedComps().join(','));
    return this.selectedMarkets().length ? `/api/picks/multiple?${params}` : undefined;
  });

  /** Il primo giorno non può superare l'ultimo: se succede, l'ultimo lo segue */
  protected setFrom(day: string): void {
    if (!day) return;
    this.dateFrom.set(day);
    if (this.dateTo() < day) this.dateTo.set(day);
  }

  protected isOn(list: string[], key: string): boolean {
    return list.includes(key);
  }

  protected toggle(list: WritableSignal<string[]>, key: string): void {
    list.update((l) => (l.includes(key) ? l.filter((k) => k !== key) : [...l, key]));
  }
}
