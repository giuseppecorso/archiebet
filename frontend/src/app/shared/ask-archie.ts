import { HttpClient, HttpErrorResponse, httpResource } from '@angular/common/http';
import { Component, computed, inject, input, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { firstValueFrom } from 'rxjs';
import { AuthService } from '../core/auth.service';

/** Una domanda con la risposta di Archie (API /api/ask, Fase 6) */
export interface AskAnswer {
  id: number;
  question: string;
  answer: string;
  match_id: number | null;
  created_at: string;
}

/** Testo della risposta in HTML semplice: grassetti (**…**) ed elenchi (righe che iniziano con "- "). Tutto il resto è testo. */
export function answerHtml(text: string): string {
  const esc = text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  const bold = esc.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
  const out: string[] = [];
  let list: string[] = [];
  const flush = () => {
    if (list.length) out.push('<ul>' + list.map((l) => `<li>${l}</li>`).join('') + '</ul>');
    list = [];
  };
  for (const line of bold.split('\n')) {
    const t = line.trim();
    if (t.startsWith('- ')) {
      list.push(t.slice(2));
    } else {
      flush();
      if (t) out.push(`<p>${t}</p>`);
    }
  }
  flush();
  return out.join('');
}

/**
 * "Chiedi ad Archie": domanda libera in italiano. Archie legge i dati dell'app con i suoi strumenti (partite, schede,
 * occasioni, notizie, le tue giocate) e risponde. Con matchId la domanda riguarda quella partita.
 */
@Component({
  selector: 'ab-ask-archie',
  imports: [FormsModule],
  template: `
    @if (admin()) {
    <section class="panel box ask" aria-labelledby="ask-title">
      <div class="box-head">
        <h2 id="ask-title" class="title box-title">Chiedi ad Archie</h2>
      </div>
      <form (ngSubmit)="send()" class="ask-form">
        <textarea name="q" rows="2" [(ngModel)]="question" [placeholder]="placeholder()" maxlength="600" [disabled]="busy()"></textarea>
        <button type="submit" class="btn-primary" [disabled]="busy() || question.trim().length < 3">{{ busy() ? 'Archie ci pensa…' : 'Chiedi' }}</button>
      </form>
      @if (error(); as e) {
        <p class="ask-error">{{ e }}</p>
      }
      @for (a of answers.value() ?? []; track a.id; let first = $first) {
        <div class="qa" [class.old]="!first">
          <p class="q">{{ a.question }}</p>
          <div class="a" [innerHTML]="html(a.answer)"></div>
        </div>
      }
    </section>
    } @else {
      <p class="muted small">Chiedi ad Archie usa l'AI a pagamento: è riservato all'amministratore.</p>
    }
  `,
  styles: `
    .ask { margin: 20px 0; }
    .ask-form { display: flex; gap: 10px; align-items: stretch; flex-wrap: wrap; }
    textarea {
      flex: 1 1 280px; min-height: 52px; padding: 8px 10px; font: inherit; color: inherit; resize: vertical;
      background: rgba(255, 255, 255, 0.04); border: 1px solid var(--line-strong); border-radius: 4px;
    }
    .ask-error { color: var(--loss); }
    .qa { margin-top: 14px; padding-top: 10px; border-top: 1px solid rgba(255, 255, 255, 0.06); }
    .qa.old { opacity: 0.75; }
    .q { margin: 0 0 6px; font-weight: 700; color: var(--amber); }
    .a { line-height: 1.55; }
    .a :is(p, ul) { margin: 0 0 8px; }
    .a ul { padding-left: 20px; }
  `,
})
export class AskArchie {
  readonly matchId = input<number | null>(null);
  readonly placeholder = input('Es. "Come arriva il Bari a domenica?" oppure "Ci sono occasioni nel weekend?"');
  protected question = '';
  protected readonly busy = signal(false);
  protected readonly error = signal<string | null>(null);
  /** Solo l'amministratore usa l'AI: gli amici non consumano la sua spesa */
  private readonly auth = inject(AuthService);
  protected readonly admin = computed(() => !!this.auth.user()?.is_admin);
  protected readonly answers = httpResource<AskAnswer[]>(() => (!this.admin() ? undefined : this.matchId() ? `/api/ask?match_id=${this.matchId()}` : '/api/ask'));
  protected readonly html = answerHtml;
  private readonly http = inject(HttpClient);

  protected async send(): Promise<void> {
    const q = this.question.trim();
    if (q.length < 3) return;
    this.busy.set(true);
    this.error.set(null);
    try {
      const a = await firstValueFrom(this.http.post<AskAnswer>('/api/ask', { question: q, match_id: this.matchId() }));
      this.answers.set([a, ...(this.answers.value() ?? [])]);
      this.question = '';
    } catch (e) {
      const detail = e instanceof HttpErrorResponse ? e.error?.detail : null;
      this.error.set(typeof detail === 'string' ? detail : 'Archie non ha risposto: riprova tra poco.');
    } finally {
      this.busy.set(false);
    }
  }
}
