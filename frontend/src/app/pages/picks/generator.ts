import { httpResource } from '@angular/common/http';
import { KeyValuePipe } from '@angular/common';
import { Component, computed, inject, signal } from '@angular/core';
import { RouterLink } from '@angular/router';
import { Competition } from '../../core/football';
import { dayLabel, kickoffTime, odds, pct } from '../../core/format';
import { Horizon } from '../../core/multiple';
import { Offer } from '../../core/picks';
import { SlipService } from '../../core/slip';
import { StudyLeg, StudyMultiple } from '../../core/study';
import { Crest } from '../../shared/crest';
import { OfferButton } from '../../shared/offer-button';
import { WhyPopup } from '../../shared/why-popup';

type Level = 'cauto' | 'equilibrato' | 'rischioso';

const LEVELS: { key: Level; label: string; hint: string }[] = [
  { key: 'cauto', label: 'Cauto', hint: 'pronostici che secondo lo studio escono 3 volte su 4 o più' },
  { key: 'equilibrato', label: 'Equilibrato', hint: 'pronostici al 55–72%: più coraggio, quote più alte' },
  { key: 'rischioso', label: 'Rischioso', hint: 'pronostici al 35–55%: escono meno spesso, pagano di più' },
];
const HORIZONS: [Horizon, string][] = [
  ['today', 'Oggi'],
  ['tomorrow', 'Domani'],
  ['2days', 'Oggi e domani'],
  ['3days', 'Prossimi 3 giorni'],
  ['week', 'Prossimi 7 giorni'],
];

/** "Archie, fammi una multipla": i pronostici studiati da Archie (D137), ognuno con il suo perché. */
@Component({
  selector: 'ab-generator',
  imports: [Crest, KeyValuePipe, OfferButton, RouterLink, WhyPopup],
  template: `
    <section class="panel box form" aria-labelledby="gen-title">
      <h2 id="gen-title" class="title">Archie, fammi una multipla</h2>
      <div class="chips" role="group" aria-label="Livello">
        @for (l of levels; track l.key) {
          <button type="button" class="chip" [class.on]="level() === l.key" [attr.aria-pressed]="level() === l.key" (click)="restart(); level.set(l.key)">{{ l.label }}</button>
        }
      </div>
      <p class="hint muted small">{{ hint() }}</p>
      <div class="row">
        <label>Partite
          <span class="legs-row">
            <button type="button" class="chip" [class.on]="auto()" [attr.aria-pressed]="auto()" [disabled]="!!target()" (click)="restart(); auto.set(!auto())" title="Archie aggiunge partite finché la multipla esce abbastanza spesso per il livello">Decide Archie</button>
            <input type="number" min="1" max="30" [value]="legs()" [disabled]="!!target() || auto()" (change)="restart(); legs.set(clamp(+$any($event.target).value))" aria-label="Numero di partite" />
          </span>
        </label>
        <label>Quota obiettivo
          <input type="number" min="1.1" step="any" placeholder="es. 50" [value]="target() ?? ''" (change)="restart(); target.set(toTarget($any($event.target).value))" />
        </label>
        <label>Puntata €
          <input type="number" min="0.5" step="0.5" [value]="stake()" (input)="stake.set(+$any($event.target).value || 0)" />
        </label>
        <label>Quando
          <select (change)="restart(); horizon.set($any($event.target).value)">
            @for (h of horizons; track h[0]) { <option [value]="h[0]" [selected]="horizon() === h[0]">{{ h[1] }}</option> }
          </select>
        </label>
        <label>Tema
          <select (change)="restart(); theme.set($any($event.target).value)">
            @for (t of themes.value() | keyvalue: keep; track t.key) { <option [value]="t.key" [selected]="theme() === t.key">{{ t.value }}</option> }
          </select>
        </label>
        <label>Campionato
          <select (change)="restart(); competition.set($any($event.target).value)">
            <option value="">Tutti</option>
            @for (c of competitions.value(); track c.code) { <option [value]="c.code">{{ c.country }} · {{ c.name }}</option> }
          </select>
        </label>
      </div>
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
                <div class="offers">
                  @for (o of offers(l); track o.bookmaker) {
                    <ab-offer [match]="l.match" [market]="l.market" [pick]="l.selection" [offer]="o" />
                  } @empty {
                    <span class="muted small">quota giusta {{ fair(l.p_archie) }}</span>
                  }
                </div>
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
            <p class="muted small warn">Con queste scelte Archie arriva solo a quota {{ fmtOdds(r.total_odds) }}: prova più giorni, tutti i campionati o un livello più rischioso.</p>
          }
          <div class="actions">
            @if (totalsList(r).length) {
              <button type="button" class="btn-primary" (click)="toSlip(r, totalsList(r)[0][0])">Metti nella schedina ({{ totalsList(r)[0][0] }})</button>
            }
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
    .box { padding: 10px 14px; }
    h2 { margin: 0 0 8px; font-size: 16px; color: var(--amber); }
    .chips { display: flex; flex-wrap: wrap; gap: 4px; }
    .chip { min-height: 30px; padding: 1px 12px; font: inherit; font-size: 13px; font-weight: 600; color: var(--text-2); background: transparent; border: 1px solid var(--line-strong); border-radius: 15px; cursor: pointer; }
    .chip.on { color: var(--amber); background: var(--chip); border-color: var(--amber); }
    .legs-row { display: flex; gap: 6px; align-items: center; }
    .legs-row input { width: 64px; }
    .chip:disabled { opacity: 0.4; cursor: default; }
    .hint { margin: 6px 0 8px; }
    .row { display: flex; flex-wrap: wrap; gap: 10px; }
    label { display: flex; flex-direction: column; gap: 4px; font-size: 10px; font-weight: 700; letter-spacing: 1px; color: var(--muted); text-transform: uppercase; }
    select, input { min-height: 30px; padding: 2px 8px; font: inherit; font-size: 13px; color: var(--text); background: var(--bg-deep); border: 1px solid var(--line-strong); border-radius: 4px; }
    input { width: 70px; }
    .legs { margin: 0; padding: 0; list-style: none; }
    .legs li { padding: 8px 0; border-bottom: 1px solid var(--line-row); }
    .when { display: block; }
    .match { display: inline-flex; align-items: center; gap: 6px; font-weight: 700; color: var(--text); text-decoration: none; }
    .pick-line { display: flex; align-items: baseline; justify-content: space-between; gap: 8px; margin-top: 2px; }
    .event { font-size: 14px; font-weight: 600; color: var(--amber); }
    .prob { font-size: 16px; }
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
  protected readonly horizons = HORIZONS;
  protected readonly level = signal<Level>('equilibrato');
  protected readonly legs = signal(4);
  protected readonly horizon = signal<Horizon>('2days');
  protected readonly competition = signal('');
  protected readonly theme = signal('tutte');
  /** Quota totale voluta (es. 50): Archie aggiunge partite finché ci arriva */
  protected readonly target = signal<number | null>(null);
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
  protected readonly result = httpResource<StudyMultiple>(() => {
    const params = new URLSearchParams({ level: this.level(), legs: String(this.legs()), horizon: this.horizon() });
    if (this.competition()) params.set('competitions', this.competition());
    if (this.theme() !== 'tutte') params.set('theme', this.theme());
    if (this.target()) params.set('target', String(this.target()));
    else if (this.auto()) params.set('auto', 'true');
    if (this.excluded().length) params.set('exclude', this.excluded().join(','));
    return `/api/study/multiple?${params}`;
  });

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

  protected fair(p: number): string {
    return odds(1 / p);
  }

  protected oneIn(p: number): string {
    return p > 0 ? (1 / p).toFixed(p > 0.1 ? 1 : 0) : '–';
  }

  /** Le quote del bookmaker come pulsanti della schedina; la differenza con lo studio è solo un'informazione */
  protected offers(l: StudyLeg): Offer[] {
    return Object.entries(l.prices).map(([bookmaker, price]) => ({ bookmaker, price, value: l.p_archie * price - 1, verdict: 'nella norma' }));
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

  protected toSlip(r: StudyMultiple, bookmaker: string): void {
    for (const l of r.legs) {
      if (!this.slip.has(l.match.id, l.market, l.selection, bookmaker)) {
        this.slip.toggle({ match: l.match, market: l.market, pick: l.selection, odds: l.prices[bookmaker], bookmaker });
      }
    }
    this.slip.stake.set(String(this.stake())); // la puntata scelta qui passa alla schedina
    this.slip.open.set(true);
  }
}
