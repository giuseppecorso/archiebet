import { httpResource } from '@angular/common/http';
import { KeyValuePipe } from '@angular/common';
import { Component, computed, inject, signal } from '@angular/core';
import { RouterLink } from '@angular/router';
import { Competition } from '../../core/football';
import { dayLabel, kickoffTime, odds, pct } from '../../core/format';
import { SlipService } from '../../core/slip';
import { StudyLeg, StudyMultiple } from '../../core/study';
import { Crest } from '../../shared/crest';
import { MultiPick, PickOption } from '../../shared/multi-pick';
import { WhyPopup } from '../../shared/why-popup';

type Level = 'cauto' | 'equilibrato' | 'rischioso';

const LEVELS: { key: Level; label: string; hint: string }[] = [
  { key: 'cauto', label: 'Cauto', hint: 'pronostici che secondo lo studio escono 3 volte su 4 o più' },
  { key: 'equilibrato', label: 'Equilibrato', hint: 'pronostici al 55–72%: più coraggio, quote più alte' },
  { key: 'rischioso', label: 'Rischioso', hint: 'pronostici al 35–55%: escono meno spesso, pagano di più' },
];

/** Livello dei pronostici per un moltiplicatore: poche partite e non troppo azzardate */
export function levelFor(target: number, legs: number | null = null): Level {
  if (legs) {
    const perLeg = target ** (1 / legs); // quota media di ogni partita per arrivare al moltiplicatore
    return perLeg <= 1.45 ? 'cauto' : perLeg <= 1.9 ? 'equilibrato' : 'rischioso';
  }
  return target <= 3 ? 'cauto' : target <= 20 ? 'equilibrato' : 'rischioso';
}

/** I prossimi giorni come opzioni (Oggi, Domani, ven 30/10…) */
function nextDays(n: number): PickOption[] {
  const out: PickOption[] = [];
  for (let i = 0; i < n; i++) {
    const d = new Date();
    d.setDate(d.getDate() + i);
    const value = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
    const label = i === 0 ? 'Oggi' : i === 1 ? 'Domani' : d.toLocaleDateString('it-IT', { weekday: 'long', day: 'numeric', month: 'numeric' });
    out.push({ value, label });
  }
  return out;
}

/** "Archie, fammi una multipla": i pronostici studiati da Archie (D137), ognuno con il suo perché. */
@Component({
  selector: 'ab-generator',
  imports: [Crest, KeyValuePipe, MultiPick, RouterLink, WhyPopup],
  template: `
    <section class="panel box form" aria-labelledby="gen-title">
      <h2 id="gen-title" class="title">Archie, fammi una multipla</h2>
      <div class="chips" role="group" aria-label="Livello">
        @for (l of levels; track l.key) {
          <button type="button" class="chip" [class.on]="level() === l.key" [attr.aria-pressed]="level() === l.key" [class.locked-chip]="!!target()" (click)="target() ? lockNote.set(levelNote()) : level.set(l.key)">{{ l.label }}</button>
        }
      </div>
      <p class="hint muted small">{{ target() ? levelNote() : hint() }}</p>
      <div class="row">
        <label>Numero partite della multipla
          <span class="legs-row">
            <button type="button" class="chip" [class.on]="auto()" [attr.aria-pressed]="auto()" (click)="auto.set(!auto()); lockNote.set(null)" title="Archie aggiunge partite finché la multipla esce abbastanza spesso per il livello">Decide Archie</button>
            <input type="number" inputmode="numeric" min="1" max="30" [value]="lockedLegs() ? '' : legs()" [placeholder]="lockedLegs() ? 'auto' : ''" [readonly]="!!lockedLegs()" [class.locked]="!!lockedLegs()" (focus)="lockedLegs() && lockNote.set(lockedLegs())" (click)="lockedLegs() && lockNote.set(lockedLegs())" (input)="legs.set(clamp(+$any($event.target).value))" aria-label="Numero di partite" />
          </span>
        </label>
      </div>
      <div class="row">
        <div class="field">Moltiplicatore
          <span class="range">
            <span class="muted">da</span>
            <input type="number" inputmode="decimal" min="1.1" step="any" placeholder="8" [value]="target() ?? ''" (input)="target.set(toTarget($any($event.target).value))" aria-label="Moltiplicatore da" />
            <span class="muted">a</span>
            <input type="number" inputmode="decimal" min="1.1" step="any" placeholder="12" [value]="targetMax() ?? ''" (input)="targetMax.set(toTarget($any($event.target).value))" aria-label="Moltiplicatore a" />
          </span>
        </div>
        <label>Puntata €
          <input type="number" inputmode="decimal" min="0.5" step="0.5" [value]="stake()" (input)="stake.set(+$any($event.target).value || 0)" />
        </label>
      </div>
      <p class="hint muted small">Moltiplicatore: quante volte vuoi moltiplicare la puntata, da… a… (da 8 a 12 = 5 € diventano 40-60 €; il secondo si può lasciare vuoto). Con «Decide Archie» sceglie lui quante partite; spento, usa esattamente il numero che scrivi.</p>
      @if ((lockedLegs() || target()) && lockNote(); as note) {
        <p class="lock-note" role="status">{{ note }}</p>
      }
      <div class="row grid2">
        <div class="field">Giorni
          <ab-multi-pick label="Giorni" [options]="dayOptions" allLabel="Prossimi 7 giorni" [(selected)]="days" />
        </div>
        <label>Tema
          <select (change)="theme.set($any($event.target).value)">
            @for (t of themes.value() | keyvalue: keep; track t.key) { <option [value]="t.key" [selected]="theme() === t.key">{{ t.value }}</option> }
          </select>
        </label>
        <div class="field wide">Campionati
          <ab-multi-pick label="Campionati" [options]="leagueOptions()" allLabel="Tutti" [(selected)]="leagues" />
        </div>
      </div>
      <button type="button" class="btn-primary generate" (click)="generate()">{{ changed() ? 'Genera la multipla' : 'Genera di nuovo' }}</button>
      @if (changed()) {
        <p class="hint muted small">Hai cambiato le scelte: premi Genera per vedere la multipla nuova.</p>
      }
    </section>

    <section class="panel box result" aria-live="polite" aria-label="Multipla studiata">
      @if (result.value(); as r) {
        @if (r.legs.length) {
          <ol class="legs">
            @for (l of r.legs; track l.match.id) {
              <li>
                <span class="when muted small">{{ day(l.match.kickoff_at) }} {{ time(l.match.kickoff_at) }} · {{ l.match.competition.name }}</span>
                <a class="match" [routerLink]="['/partite', l.match.id]"><ab-crest [team]="l.match.home" [size]="16" /> {{ l.match.home.name }} – {{ l.match.away.name }} <ab-crest [team]="l.match.away" [size]="16" /></a>
                <div class="pick-line">
                  <span class="event">{{ capital(l.event) }}</span>
                  <span class="led prob" title="Probabilità dello studio di Archie">{{ pct(l.p_archie) }}</span>
                </div>
                <span class="price muted small">
                  @if (l.avg_price) { quota media <strong>{{ fmtOdds(l.avg_price) }}</strong> } @else { quota stimata da Archie <strong>{{ fmtOdds(1 / l.p_archie) }}</strong> }
                </span>
                <ab-why [title]="capital(l.event)" [reasons]="l.reasons" />
              </li>
            }
          </ol>
          <div class="totals">
            <span>Esce tutta: <strong>{{ pct(r.win_probability) }}</strong> <span class="muted small">· circa 1 volta su {{ oneIn(r.win_probability) }}</span></span>
            @for (t of totalsList(r); track t[0]) {
              <span>Quota totale {{ t[0] }}: <strong class="led">{{ fmtOdds(t[1]) }}</strong> <span class="muted small">· con {{ stake() }} € vinci <strong>{{ money(stake() * t[1]) }}</strong></span></span>
            } @empty {
              <span>Quota totale stimata: <strong class="led">{{ fmtOdds(r.total_odds) }}</strong> <span class="muted small">· con {{ stake() }} € circa {{ money(stake() * r.total_odds) }} (alcune quote vanno cercate sull'app)</span></span>
            }
          </div>
          @if (target() && !r.target_reached) {
            <p class="muted small warn">Con queste scelte Archie arriva a quota {{ fmtOdds(r.total_odds) }}, fuori da quella chiesta: prova più giorni, più campionati o un intervallo più largo.</p>
          }
          <div class="actions">
            <button type="button" class="btn-primary" (click)="play(r)">Gioca questa multipla</button>
            <button type="button" class="again" [disabled]="!r.more" (click)="another(r)">Genera un'altra multipla</button>
          </div>
          @if (!target() && !auto() && r.legs.length < legs()) {
            <p class="muted small">Archie ha trovato solo {{ r.legs.length }} partite da proporre a questo livello: le altre non hanno un pronostico su cui modello e campo sono d'accordo.</p>
          }
          <p class="muted small note">La percentuale è quella dello studio di Archie (modello dei gol e fatti del campo), non quella delle quote.</p>
        } @else {
          <p class="muted">Nessuna partita da proporre con queste scelte: prova più giorni, un altro livello o tutti i campionati.</p>
          @if (excluded().length) {
            <button type="button" class="again" (click)="restart()">Ricomincia dalle migliori</button>
          }
        }
      } @else if (result.isLoading()) {
        <p class="muted small">Archie sta studiando le partite…</p>
      } @else if (result.error()) {
        <p class="warn">Il generatore non risponde: controlla che il backend sia acceso.</p>
      }
    </section>
  `,
  styles: `
    :host { display: grid; grid-template-columns: minmax(0, 340px) minmax(0, 1fr); gap: 12px; align-items: start; }
    @media (max-width: 860px) { :host { grid-template-columns: 1fr; } }
    .box { padding: 16px 18px; }
    h2 { margin: 0 0 8px; font-size: 16px; color: var(--amber); }
    .chips { display: flex; flex-wrap: wrap; gap: 4px; }
    .chip { min-height: 30px; padding: 1px 12px; font: inherit; font-size: 13px; font-weight: 600; color: var(--text-2); background: transparent; border: 1px solid var(--line-strong); border-radius: 15px; cursor: pointer; }
    .chip.on { color: var(--amber); background: var(--chip); border-color: var(--amber); }
    .legs-row { display: flex; gap: 6px; align-items: center; }
    .legs-row input { width: 64px; }
    input.locked { opacity: 0.45; text-decoration: line-through; cursor: not-allowed; border-style: dashed; }
    .lock-note { margin: 0 0 8px; padding: 6px 10px; font-size: 12px; color: var(--amber); border-left: 3px solid var(--amber); background: rgb(255 200 40 / 0.06); }
    .chip:disabled { opacity: 0.4; cursor: default; }
    .hint { margin: 6px 0 8px; }
    .row { display: flex; flex-wrap: wrap; gap: 10px; margin-bottom: 8px; }
    .row label, .row .field { min-width: 120px; }
    .row .wide { flex: 1 1 100%; }
    .row.grid2 { display: grid; grid-template-columns: 1fr 1fr; }
    .row.grid2 .wide { grid-column: 1 / -1; }
    .row.grid2 select { width: 100%; }
    .range { display: flex; align-items: center; gap: 6px; font-size: 13px; letter-spacing: 0; text-transform: none; }
    .range input { width: 64px; }
    .field ab-multi-pick { letter-spacing: 0; text-transform: none; font-weight: 400; }
    .generate { display: block; min-height: 38px; margin: 8px auto 0; padding: 6px 26px; font-size: 15px; }
    .chip.locked-chip { opacity: 0.45; border-style: dashed; }
    label, .field { display: flex; flex-direction: column; gap: 4px; font-size: 10px; font-weight: 700; letter-spacing: 1px; color: var(--muted); text-transform: uppercase; }
    select, input { min-height: 30px; padding: 2px 8px; font: inherit; font-size: 13px; color: var(--text); background: var(--bg-deep); border: 1px solid var(--line-strong); border-radius: 4px; }
    input { width: 70px; }
    .legs { margin: 0; padding: 0; list-style: none; }
    .legs li { padding: 8px 0; border-bottom: 1px solid var(--line-row); }
    .when { display: block; }
    .match { display: inline-flex; align-items: center; gap: 6px; font-weight: 700; color: var(--text); text-decoration: none; }
    .pick-line { display: flex; align-items: baseline; justify-content: space-between; gap: 8px; margin-top: 2px; }
    .event { font-size: 14px; font-weight: 600; color: var(--amber); }
    .prob { font-size: 16px; }
    .price { display: block; margin: 2px 0 4px; }
    .price strong { color: var(--text); }
    .offers { display: flex; flex-wrap: wrap; gap: 4px; margin-top: 4px; }
    .why { margin-top: 4px; font-size: 12px; color: var(--text-2); }
    .why summary { color: var(--muted); cursor: pointer; }
    .why p { margin: 3px 0 0 10px; }
    .totals { display: flex; flex-wrap: wrap; gap: 6px 18px; margin: 10px 0 6px; font-size: 13px; }
    .totals .led { font-size: 15px; }
    .actions { display: flex; flex-wrap: wrap; gap: 8px; }
    .again { min-height: 34px; padding: 4px 12px; font: inherit; font-size: 13px; font-weight: 600; color: var(--amber); background: transparent; border: 1px solid var(--amber); border-radius: 4px; cursor: pointer; }
    .again:disabled { opacity: 0.4; cursor: default; }
    .note { margin-top: 8px; }
    .warn { color: var(--loss); }
  `,
})
export class Generator {
  private readonly slip = inject(SlipService);
  protected readonly levels = LEVELS;
  protected readonly level = signal<Level>('equilibrato');
  protected readonly legs = signal(4);
  /** Giorni scelti (AAAA-MM-GG); nessuno = prossimi 7 giorni */
  protected readonly dayOptions: PickOption[] = nextDays(7);
  protected readonly days = signal<string[]>(this.dayOptions.slice(0, 2).map((d) => d.value));
  /** Campionati scelti (codici); nessuno = tutti */
  protected readonly leagues = signal<string[]>([]);
  protected readonly theme = signal('tutte');
  /** Quota totale voluta (es. 50): Archie aggiunge partite finché ci arriva */
  protected readonly target = signal<number | null>(null);
  /** Moltiplicatore massimo ("da 8 a 12"); vuoto = nessun limite */
  protected readonly targetMax = signal<number | null>(null);
  protected readonly stake = signal(5);
  /** Consigliato: Archie decide quante partite (probabilità che esca almeno 40%, 20% o 8% secondo il livello) */
  protected readonly auto = signal(true);
  /** Partite già proposte: "genera un'altra multipla" le salta */
  protected readonly excluded = signal<number[]>([]);

  protected readonly competitions = httpResource<Competition[]>(() => '/api/competitions', { defaultValue: [] });
  protected readonly themes = httpResource<Record<string, string>>(() => '/api/study/themes', { defaultValue: { tutte: 'Tutte' } });
  /** I temi nell'ordine del server */
  protected readonly keep = () => 0;
  protected readonly hint = computed(() => LEVELS.find((l) => l.key === this.level())!.hint);
  /** Le scelte come parametri della richiesta (senza le partite già proposte) */
  private readonly choices = computed(() => {
    const target = this.target();
    const params = new URLSearchParams({ level: target ? levelFor(target, this.auto() ? null : this.legs()) : this.level(), legs: String(this.legs()) });
    if (this.days().length) params.set('days', [...this.days()].sort().join(','));
    else params.set('horizon', 'week');
    if (this.leagues().length) params.set('competitions', this.leagues().join(','));
    if (this.theme() !== 'tutte') params.set('theme', this.theme());
    if (this.target()) params.set('target', String(this.target()));
    if (this.target() && this.targetMax()) params.set('target_max', String(this.targetMax()));
    if (this.auto()) params.set('auto', 'true'); // con il moltiplicatore: Archie decide quante partite; spento = esattamente quelle scelte
    return params.toString();
  });
  /** Le scelte usate dall'ultima multipla: cambiano solo con "Genera" */
  /** Perché il numero di partite non si può scrivere (null = si può) */
  protected readonly lockedLegs = computed(() =>
    this.auto() ? 'È attivo «Decide Archie»: toccalo per spegnerlo e scegliere tu quante partite.' : null);
  protected readonly lockNote = signal<string | null>(null);
  /** Con il moltiplicatore il livello lo sceglie Archie */
  protected readonly levelNote = computed(() => {
    const t = this.target();
    if (!t) return '';
    const lv = levelFor(t, this.auto() ? null : this.legs());
    return this.auto()
      ? `Con il moltiplicatore il livello lo sceglie Archie: per ${t} usa pronostici ${lv}.`
      : `${this.legs()} partite per arrivare a ${t}: Archie usa pronostici ${lv} e sceglie la combinazione più probabile.`;
  });
  protected readonly leagueOptions = computed<PickOption[]>(() => {
    const all = (this.competitions.value() ?? []).map((c) => ({ value: c.code, label: c.name, group: c.country }));
    const first = [...new Set(all.map((o) => o.group))]; // ogni paese una volta sola, nell'ordine in cui compare
    return [...all].sort((x, y) => first.indexOf(x.group) - first.indexOf(y.group));
  });
  private readonly applied = signal(this.choices());
  protected readonly changed = computed(() => this.applied() !== this.choices());
  protected readonly result = httpResource<StudyMultiple>(() => {
    const params = new URLSearchParams(this.applied());
    if (this.excluded().length) params.set('exclude', this.excluded().join(','));
    return `/api/study/multiple?${params}`;
  });

  protected generate(): void {
    this.restart();
    this.applied.set(this.choices());
    this.result.reload();
  }

  protected readonly pct = pct;
  protected readonly fmtOdds = odds;
  protected readonly day = dayLabel;
  protected readonly time = (iso: string) => kickoffTime(iso);

  protected toTarget(v: string): number | null {
    const n = Number(String(v).replace(',', '.'));
    return n > 1 ? Math.min(n, 100000) : null;
  }

  protected money(n: number): string {
    return n.toLocaleString('it-IT', { style: 'currency', currency: 'EUR' });
  }

  protected clamp(n: number): number {
    return Math.min(30, Math.max(1, Math.round(n) || 1));
  }

  protected capital(text: string): string {
    return text.charAt(0).toUpperCase() + text.slice(1);
  }

  protected oneIn(p: number): string {
    return p > 0 ? (1 / p).toFixed(p > 0.1 ? 1 : 0) : '–';
  }

  protected totalsList(r: StudyMultiple): [string, number][] {
    return Object.entries(r.totals);
  }

  protected another(r: StudyMultiple): void {
    this.excluded.update((ids) => [...ids, ...r.legs.map((l) => l.match.id)]);
  }

  protected restart(): void {
    this.excluded.set([]);
  }

  /** Mette la multipla nella Schedina: quota del bookmaker se c'è, altrimenti la media, altrimenti quella stimata da Archie
   * (nella Schedina si può correggere con quella vera prima di registrare). */
  protected play(r: StudyMultiple): void {
    const bookmaker = this.totalsList(r)[0]?.[0] ?? null;
    this.slip.fill(
      r.legs.map((l) => ({
        match: l.match,
        market: l.market,
        pick: l.selection,
        odds: +((bookmaker ? l.prices[bookmaker] : null) ?? l.avg_price ?? 1 / l.p_archie).toFixed(2),
        bookmaker,
      })),
    );
    this.slip.stake.set(String(this.stake())); // la puntata scelta qui passa alla schedina
  }
}
