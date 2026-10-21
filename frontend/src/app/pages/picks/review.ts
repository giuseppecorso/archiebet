import { httpResource } from '@angular/common/http';
import { Component, computed, signal } from '@angular/core';
import { pct, signedPct } from '../../core/format';
import { REVIEW_PROFILES, Review, Tally, Variant, groupLabel, weekLabel } from '../../core/review';

/** Pagella settimanale (D132): Archie confronta ogni settimana quello che aveva detto con quello che è successo. */
@Component({
  selector: 'ab-review',
  template: `
    @if (review.value(); as r) {
      <section class="panel box" aria-labelledby="rv-state">
        <div class="head">
          <h2 id="rv-state" class="title">Cosa ha deciso Archie</h2>
          <span class="muted small">aggiornata il {{ day(r.computed_at) }} · {{ r.weeks.length }} settimane</span>
        </div>
        <p class="lead">
          @if (corrected().length === 0 && r.state.bench.length === 0) {
            Le sue probabilità reggono il confronto con i risultati: <strong>niente da correggere</strong> e nessun mercato in panchina.
          } @else {
            @if (corrected().length) { Corregge le probabilità di: <strong>{{ corrected().join(', ') }}</strong>. }
            @if (r.state.bench.length) { Tiene fuori dalle multiple: <strong>{{ benched().join(', ') }}</strong>. }
          }
        </p>
        <table class="grid">
          <thead><tr><th>Mercati</th><th>Taratura</th><th>Nelle multiple</th></tr></thead>
          <tbody>
            @for (g of r.state.groups; track g.group) {
              @let b = benchOf(g.group);
              <tr>
                <td>{{ label(g.group) }}</td>
                <td>
                  @if (g.corrected) { <span class="tag fix">corretta</span> }
                  @else if (g.eval_weeks < 4) { <span class="muted">pochi dati ({{ g.eval_weeks }} sett.)</span> }
                  @else { <span class="tag ok">giusta</span> }
                  @if (g.t !== null) { <span class="muted small">t {{ g.t }}</span> }
                </td>
                <td>
                  @if (b?.benched) { <span class="tag bad">in panchina</span> }
                  @else { <span class="tag ok">in campo</span> }
                  @if (b && b.gap !== null) { <span class="muted small">{{ signed(b.gap) }} su {{ b.legs }} gambe</span> }
                </td>
              </tr>
            }
          </tbody>
        </table>
      </section>

      <section class="panel box" aria-labelledby="rv-mult">
        <div class="head">
          <h2 id="rv-mult" class="title">Le multiple, settimana per settimana</h2>
          <div class="chips">
            @for (p of profiles; track p) {
              <button type="button" class="chip" [class.on]="profile() === p" [attr.aria-pressed]="profile() === p" (click)="profile.set(p)">{{ p }}</button>
            }
          </div>
        </div>
        <p class="muted small">
          Una multipla al giorno da 4 partite su Sisal e una su Eurobet, con le quote delle 10 del mattino; 1 € a multipla.
          <strong>Attese</strong> = quante doveva vincerne secondo Archie: se le vinte restano vicine, le sue probabilità sono oneste.
        </p>
        <table class="grid num">
          <thead><tr><th>Settimana</th><th>Giocate</th><th>Vinte</th><th>Attese</th><th>Guadagno</th><th>CLV</th></tr></thead>
          <tbody>
            @for (w of weeksDesc(); track w.week) {
              @let t = tally(w.multiples, profile());
              @if (t && t.played) {
                <tr>
                  <td>{{ week(w.week) }}</td>
                  <td>{{ t.played }}</td>
                  <td>{{ t.won }}</td>
                  <td class="muted">{{ t.expected.toFixed(1) }}</td>
                  <td [class.pos]="t.profit > 0" [class.neg]="t.profit < 0">{{ euro(t.profit) }}</td>
                  <td class="muted">{{ t.clv === null ? '–' : signed(t.clv) }}</td>
                </tr>
              }
            }
          </tbody>
          @if (total(); as t) {
            <tfoot>
              <tr>
                <td>Totale</td><td>{{ t.played }}</td><td>{{ t.won }}</td><td class="muted">{{ t.expected.toFixed(1) }}</td>
                <td [class.pos]="t.profit > 0" [class.neg]="t.profit < 0">{{ euro(t.profit) }}</td>
                <td class="muted">{{ t.clv === null ? '–' : signed(t.clv) }}</td>
              </tr>
            </tfoot>
          }
        </table>
        @if (learnedDiffers()) {
          <p class="small">Con le correzioni di Archie: {{ learnedLine() }}</p>
        }
      </section>

      <section class="panel box" aria-labelledby="rv-prob">
        <div class="head"><h2 id="rv-prob" class="title">Le probabilità, settimana per settimana</h2></div>
        <p class="muted small">Per ogni mercato l'esito che Archie dava più probabile: in media quanto lo dava (atteso) e quante volte è uscito.</p>
        <table class="grid num">
          <thead><tr><th>Settimana</th><th>Partite</th>@for (f of families; track f[0]) { <th>{{ f[1] }}</th> }</tr></thead>
          <tbody>
            @for (w of weeksDesc(); track w.week) {
              <tr>
                <td>{{ week(w.week) }}</td>
                <td>{{ w.matches }}</td>
                @for (f of families; track f[0]) {
                  @let s = score(w, f[0]);
                  <td>
                    @if (s) { {{ pct(s.favorite_expected) }} → <strong [class.pos]="s.favorite_actual >= s.favorite_expected" [class.neg]="s.favorite_actual < s.favorite_expected">{{ pct(s.favorite_actual) }}</strong> }
                    @else { <span class="muted">–</span> }
                  </td>
                }
              </tr>
            }
          </tbody>
        </table>
        <p class="muted small">
          Ogni settimana Archie prova, solo sul passato, se correggere le probabilità di un gruppo le renderebbe più giuste
          (deve migliorare oltre 2,5 errori standard su almeno 4 settimane), e mette in panchina i mercati le cui gambe
          vincono chiaramente meno di quanto dice. Regole fissate prima di guardare i dati (D132).
        </p>
      </section>
    } @else if (review.error()) {
      <p class="muted">La prima pagella arriva con il lavoro settimanale di Archie (entro due ore dall'avvio dell'app).</p>
    } @else {
      <p class="muted small">Archie sta rileggendo le sue settimane…</p>
    }
  `,
  styles: `
    :host { display: grid; gap: 12px; }
    .box { padding: 10px 14px; }
    .head { display: flex; flex-wrap: wrap; align-items: baseline; justify-content: space-between; gap: 6px 12px; margin-bottom: 6px; }
    h2 { margin: 0; font-size: 16px; color: var(--amber); }
    .lead { margin: 0 0 8px; font-size: 13px; }
    p { margin: 4px 0 8px; }
    .grid { width: 100%; border-collapse: collapse; font-size: 12.5px; }
    .grid th { padding: 4px 6px; font-size: 10px; font-weight: 700; letter-spacing: 1px; text-align: left; text-transform: uppercase; color: var(--muted); border-bottom: 1px solid var(--line); }
    .grid td { padding: 4px 6px; border-bottom: 1px solid var(--line-row); white-space: nowrap; }
    .grid.num td + td, .grid.num th + th { text-align: right; }
    .grid tfoot td { font-weight: 700; border-bottom: 0; border-top: 1px solid var(--line); }
    .tag { display: inline-block; margin-right: 6px; padding: 0 6px; font-size: 11px; font-weight: 700; border: 1px solid; border-radius: 3px; }
    .ok { color: var(--value); }
    .fix { color: var(--amber); }
    .bad { color: var(--loss); }
    .pos { color: var(--value); }
    .neg { color: var(--loss); }
    .chips { display: flex; flex-wrap: wrap; gap: 4px; }
    .chip { min-height: 26px; padding: 0 9px; font: inherit; font-size: 11px; font-weight: 600; color: var(--text-2); background: transparent; border: 1px solid var(--line-strong); border-radius: 13px; cursor: pointer; }
    .chip.on { color: var(--amber); background: var(--chip); border-color: var(--amber); }
    @media (max-width: 640px) { .grid { font-size: 11.5px; } .grid td, .grid th { padding: 3px 4px; } }
    :host { overflow-x: auto; }
  `,
})
export class ReviewPage {
  protected readonly review = httpResource<Review>(() => '/api/lab/review');
  protected readonly profiles = REVIEW_PROFILES;
  protected readonly profile = signal('equilibrata');
  protected readonly families: [string, string][] = [['esito', '1X2'], ['gol', 'Gol'], ['angoli', 'Angoli'], ['cartellini', 'Cartellini']];
  protected readonly pct = pct;
  protected readonly signed = signedPct;
  protected readonly label = groupLabel;
  protected readonly week = weekLabel;

  protected readonly weeksDesc = computed(() => [...(this.review.value()?.weeks ?? [])].reverse());
  protected readonly corrected = computed(() => Object.keys(this.review.value()?.state.corrections ?? {}).map(groupLabel));
  protected readonly benched = computed(() => (this.review.value()?.state.bench ?? []).map(groupLabel));
  protected readonly total = computed(() => this.review.value()?.totals.base[this.profile()] ?? null);
  protected readonly learnedDiffers = computed(() => {
    const t = this.review.value()?.totals;
    return !!t && JSON.stringify(t.base[this.profile()]) !== JSON.stringify(t.impara[this.profile()]);
  });
  protected readonly learnedLine = computed(() => {
    const t = this.review.value()?.totals.impara[this.profile()];
    return t ? `${t.won} vinte su ${t.played} (attese ${t.expected.toFixed(1)}), guadagno ${this.euro(t.profit)}` : '';
  });

  protected tally(m: Record<Variant, Record<string, Tally>>, profile: string): Tally | undefined {
    return m.base[profile];
  }

  protected benchOf(group: string) {
    return this.review.value()?.state.bench_tests.find((b) => b.group === group);
  }

  protected score(w: Review['weeks'][number], family: string) {
    return w.families.find((f) => f.family === family);
  }

  protected euro(v: number): string {
    return `${v > 0 ? '+' : ''}${v.toFixed(2).replace('.', ',')} €`;
  }

  protected day(iso: string): string {
    return new Date(iso).toLocaleDateString('it-IT', { day: 'numeric', month: 'long' });
  }
}
