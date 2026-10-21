import { HttpClient, HttpErrorResponse, httpResource } from '@angular/common/http';
import { Component, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { firstValueFrom } from 'rxjs';

interface RuleOut {
  id: number | null;
  kind: string;
  value: string;
  text: string;
  reason: string;
  source: 'mine' | 'archie';
  active: boolean;
}

interface RulesOut {
  rules: RuleOut[];
  suggestions: RuleOut[];
  style: string | null;
  style_at: string | null;
}

/** Il tuo regolamento personale e il tuo stile di gioco scritto da Archie (Fase 6, D114) */
@Component({
  selector: 'ab-rules-panel',
  imports: [FormsModule],
  template: `
    <section class="panel box rules" aria-labelledby="rules-title">
      <div class="box-head">
        <h2 id="rules-title" class="title box-title">Il tuo regolamento</h2>
        <span class="muted small">Archie lo controlla prima di "L'ho giocata": solo avvisi, mai blocchi</span>
      </div>
      @if (data.value(); as d) {
        <ul class="rule-list">
          @for (r of d.rules; track r.id) {
            <li [class.off]="!r.active">
              <label><input type="checkbox" [checked]="r.active" (change)="toggle(r)" /> {{ r.text }}</label>
              @if (r.reason) { <span class="muted small">· {{ r.reason }}</span> }
              <button type="button" class="link-btn" (click)="remove(r)">togli</button>
            </li>
          } @empty {
            <li class="muted">Nessuna regola. La squadra del cuore (Impostazioni) è sempre esclusa.</li>
          }
        </ul>
        @if (d.suggestions.length) {
          <h3 class="title sub">Archie suggerisce, dai tuoi dati</h3>
          <ul class="rule-list">
            @for (s of d.suggestions; track s.kind + s.value) {
              <li>{{ s.text }} <span class="muted small">· {{ s.reason }}</span>
                <button type="button" class="link-btn" (click)="add(s.kind, s.value, s.reason, 'archie')">aggiungi</button></li>
            }
          </ul>
        }
        <form class="rule-add" (ngSubmit)="addMine()">
          <select name="kind" [(ngModel)]="kind">
            <option value="max_legs">Al massimo N partite per schedina</option>
            <option value="max_total_odds">Quota totale al massimo</option>
            <option value="max_stake">Puntata al massimo (€)</option>
            <option value="avoid_market">Evita un mercato</option>
            <option value="no_low_price">Solo quote non sotto il giusto</option>
          </select>
          @if (kind === 'avoid_market') {
            <select name="market" [(ngModel)]="value">
              <option value="1X2">1X2</option><option value="DC">Doppia chance</option><option value="OU2.5">Under/Over 2.5</option><option value="GG">Gol/No gol</option>
            </select>
          } @else if (kind !== 'no_low_price') {
            <input name="value" [(ngModel)]="value" inputmode="decimal" placeholder="numero" size="6" />
          }
          <button type="submit" class="btn-primary">Aggiungi regola</button>
        </form>
        @if (error(); as e) { <p class="err">{{ e }}</p> }

        <h3 class="title sub">Il tuo stile di gioco</h3>
        @if (d.style) {
          <p class="style">{{ d.style }}</p>
        } @else {
          <p class="muted small">Archie lo scrive dai tuoi numeri: schedine, mercati, campionati, CLV.</p>
        }
        <button type="button" class="btn-primary" [disabled]="writing()" (click)="style()">
          {{ writing() ? 'Archie scrive…' : d.style ? 'Aggiorna (una volta al giorno)' : 'Scrivi il mio stile di gioco' }}
        </button>
      }
    </section>
  `,
  styles: `
    .rules { margin: 20px 0; }
    .rule-list { list-style: none; padding: 0; margin: 6px 0 10px; }
    .rule-list li { padding: 5px 0; border-bottom: 1px solid rgba(255,255,255,0.05); }
    .rule-list li.off { opacity: 0.55; }
    .sub { margin: 14px 0 4px; font-size: 13px; }
    .rule-add { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; }
    select, input { font: inherit; color: inherit; background: rgba(255,255,255,0.04); border: 1px solid var(--line-strong); border-radius: 4px; padding: 4px 6px; }
    .link-btn { margin-left: 8px; background: none; border: none; color: var(--amber); cursor: pointer; font: inherit; font-size: 12px; }
    .style { line-height: 1.55; }
    .err { color: var(--loss); }
  `,
})
export class RulesPanel {
  protected readonly data = httpResource<RulesOut>(() => '/api/rules');
  protected readonly writing = signal(false);
  protected readonly error = signal<string | null>(null);
  protected kind = 'max_legs';
  protected value = '';
  private readonly http = inject(HttpClient);

  protected async add(kind: string, value: string, reason = '', source = 'mine'): Promise<void> {
    this.error.set(null);
    try {
      await firstValueFrom(this.http.post('/api/rules', { kind, value, reason, source }));
      this.data.reload();
    } catch (e) {
      this.error.set(this.message(e, 'Regola non valida.'));
    }
  }

  protected async addMine(): Promise<void> {
    const value = this.kind === 'no_low_price' ? '' : this.value.replace(',', '.').trim();
    await this.add(this.kind, value);
    this.value = '';
  }

  protected async toggle(r: RuleOut): Promise<void> {
    await firstValueFrom(this.http.patch(`/api/rules/${r.id}`, { active: !r.active }));
    this.data.reload();
  }

  protected async remove(r: RuleOut): Promise<void> {
    await firstValueFrom(this.http.delete(`/api/rules/${r.id}`));
    this.data.reload();
  }

  protected async style(): Promise<void> {
    this.writing.set(true);
    this.error.set(null);
    try {
      this.data.set(await firstValueFrom(this.http.post<RulesOut>('/api/rules/style', {})));
    } catch (e) {
      this.error.set(this.message(e, 'Non riuscito: riprova tra poco.'));
    } finally {
      this.writing.set(false);
    }
  }

  private message(e: unknown, fallback: string): string {
    const detail = e instanceof HttpErrorResponse ? e.error?.detail : null;
    return typeof detail === 'string' ? detail : fallback;
  }
}
