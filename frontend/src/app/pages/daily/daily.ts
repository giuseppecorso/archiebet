import { httpResource } from '@angular/common/http';
import { Component } from '@angular/core';
import { RouterLink } from '@angular/router';
import { DailyOut, DailySlip } from '../../core/daily';
import { dayLabel, kickoffTime, odds, pct } from '../../core/format';
import { slipImage } from './slip-image';

/** Bacheca Daily (D153): le schedine pubblicate da Archie, appese come foglietti, con le statistiche per tutti. */
@Component({
  selector: 'ab-daily',
  imports: [RouterLink],
  template: `
    @if (data.value(); as d) {
      <p class="intro">
        Ogni mattina alle 10 Archie appende qui le sue schedine. <strong>Una volta pubblicate non cambiano più</strong>:
        sotto trovi quante sono uscite davvero, contro quante dovevano uscire secondo le sue probabilità.
      </p>
      @if (d.today.legs_total) {
        <p class="today">
          Oggi: <strong class="led">{{ d.today.legs_won }}/{{ d.today.legs_closed }}</strong> pronostici azzeccati tra quelli già finiti
          <span class="muted small">({{ d.today.legs_total }} pubblicati)</span>
        </p>
      }

      <div class="cork">
        @for (s of d.board; track s.id) {
          <article class="note" [class]="'note tilt-' + ($index % 4)" [attr.data-status]="s.status">
            <span class="pin" aria-hidden="true"></span>
            <header>
              <h2>{{ s.title }}</h2>
              <span class="when">{{ dayLabel(s.period + 'T12:00:00') }} · pubblicata alle {{ time(s.published_at) }}</span>
            </header>
            <ol>
              @for (l of s.legs; track l.match_id + l.market) {
                <li [attr.data-status]="l.status">
                  <a [routerLink]="['/partite', l.match_id]" class="m">{{ l.home }} – {{ l.away }}</a>
                  <span class="e">{{ capital(l.event) }}</span>
                  <span class="meta">{{ dayLabel(l.kickoff_at) }} {{ time(l.kickoff_at) }} · {{ pct(l.p) }} · quota {{ fmtOdds(l.price) }}</span>
                  <span class="mark" aria-hidden="true">{{ mark(l.status) }}</span>
                </li>
              }
            </ol>
            <footer>
              @if (s.singles) {
                <span>Da giocare singole · 1 € ciascuna</span>
              } @else {
                <span>Quota <strong>{{ fmtOdds(s.total_odds) }}</strong> · esce 1 volta su {{ oneIn(s.win_probability) }}</span>
              }
              <button type="button" class="share" (click)="share(s)">Immagine</button>
            </footer>
            @if (s.status !== 'open') {
              <span class="stamp" [attr.data-status]="s.status">{{ stamp(s.status) }}</span>
            }
          </article>
        } @empty {
          <p class="empty">La bacheca è vuota: le prime schedine arrivano alle 10 del mattino.</p>
        }
      </div>

      <section class="panel box stats" aria-labelledby="st-title">
        <h2 id="st-title" class="title box-title">Statistiche della bacheca</h2>
        <div class="table-wrap">
          <table>
            <thead>
              <tr><th scope="col">Schedina</th><th scope="col">Pubblicate</th><th scope="col">Uscite</th><th scope="col">Attese</th><th scope="col">Pronostici giusti</th><th scope="col">Con 1 €</th></tr>
            </thead>
            <tbody>
              @for (k of d.stats; track k.kind) {
                <tr>
                  <th scope="row">{{ k.title }}</th>
                  <td>{{ k.published }}</td>
                  <td>{{ k.won }}{{ k.kind === 'clv' ? ' pronostici' : '/' + k.closed }}</td>
                  <td class="muted">{{ k.expected.toFixed(1) }}</td>
                  <td>{{ k.legs_won }}/{{ k.legs_closed }}</td>
                  <td [class]="k.profit > 0 ? 'pos' : k.profit < 0 ? 'neg' : ''">{{ money(k.profit) }}</td>
                </tr>
              }
            </tbody>
          </table>
        </div>
        <p class="muted small">"Attese" = quante dovevano uscire sommando le probabilità di Archie: se le uscite restano vicine alle attese, Archie è onesto con le sue percentuali.</p>
      </section>

      @if (d.history.length) {
        <section class="panel box" aria-labelledby="hi-title">
          <h2 id="hi-title" class="title box-title">Le ultime chiuse</h2>
          <ul class="history">
            @for (s of d.history; track s.id) {
              <li [attr.data-status]="s.status">
                <span>{{ s.title }} · {{ dayLabel(s.period + 'T12:00:00') }}</span>
                <span class="small">
                  @for (l of s.legs; track l.match_id + l.market) { <span [attr.data-status]="l.status" class="dot" [title]="l.home + ' – ' + l.away + ': ' + l.event"></span> }
                  <strong>{{ stamp(s.status) }}</strong>
                </span>
              </li>
            }
          </ul>
        </section>
      }
    } @else if (data.isLoading()) {
      <p class="muted">Carico la bacheca…</p>
    }
  `,
  styleUrl: './daily.scss',
})
export class Daily {
  protected readonly data = httpResource<DailyOut>(() => '/api/daily');
  protected readonly pct = pct;
  protected readonly fmtOdds = odds;
  protected readonly dayLabel = dayLabel;
  protected readonly time = (iso: string) => kickoffTime(iso);

  protected capital(text: string): string {
    return text.charAt(0).toUpperCase() + text.slice(1);
  }

  protected oneIn(p: number): string {
    return p > 0 ? String(Math.max(1, Math.round(1 / p))) : '–';
  }

  protected mark(status: string): string {
    return status === 'won' ? '✓' : status === 'lost' ? '✗' : status === 'void' ? '–' : '';
  }

  protected stamp(status: string): string {
    return { won: 'Vinta', lost: 'Persa', void: 'Annullata', done: 'Chiusa', open: 'In corso' }[status] ?? status;
  }

  protected money(n: number): string {
    return (n > 0 ? '+' : '') + n.toLocaleString('it-IT', { style: 'currency', currency: 'EUR' });
  }

  /** Immagine quadrata da condividere (Instagram): sul telefono si apre la condivisione, sul PC si scarica */
  protected async share(s: DailySlip): Promise<void> {
    const blob = await slipImage(s);
    const file = new File([blob], `archiebet-${s.kind}-${s.period}.png`, { type: 'image/png' });
    if (navigator.canShare?.({ files: [file] })) {
      try {
        await navigator.share({ files: [file], title: s.title });
        return;
      } catch {
        // condivisione annullata: si scarica il file
      }
    }
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = file.name;
    a.click();
    setTimeout(() => URL.revokeObjectURL(a.href), 10_000); // subito annullerebbe lo scaricamento
  }

}
