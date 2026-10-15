import { httpResource } from '@angular/common/http';
import { Component } from '@angular/core';
import { RouterLink } from '@angular/router';
import { Market, pickLabel } from '../core/bets';
import { MatchCard } from '../core/football';
import { kickoffTime, odds, pct, signedPct } from '../core/format';

interface OffLine {
  match: MatchCard;
  market: string;
  selection: string;
  probability: number;
  bookmaker: string;
  price: number;
  value: number;
  suspicious: boolean;
}

/** "Quote fuori linea oggi" (specifiche sezione 3, regola 4, D70). */
@Component({
  selector: 'ab-off-line-card',
  imports: [RouterLink],
  template: `
    <section class="panel card" aria-labelledby="off-title">
      <h2 id="off-title" class="title">Quote fuori linea oggi</h2>
      @if (data.value(); as rows) {
        @if (rows.length) {
          <ul>
            @for (r of rows; track r.match.id + r.market + r.selection + r.bookmaker) {
              <li>
                <span class="muted small">{{ time(r.match.kickoff_at) }} · {{ r.match.competition.name }}</span>
                <a [routerLink]="['/partite', r.match.id]" class="match">{{ r.match.home.name }} – {{ r.match.away.name }}</a>
                <span class="line">
                  <span>{{ label(r) }} · {{ r.bookmaker }} <span class="led">{{ odds(r.price) }}</span></span>
                  <span [class]="r.suspicious ? 'value sus' : 'value'">{{ signed(r.value) }}</span>
                </span>
                <span class="muted small">giusta {{ fair(r.probability) }} ({{ pct(r.probability) }})</span>
                @if (r.suspicious) {
                  <span class="warn small">Sospetta: controlla notizie e formazioni. Se è un errore palese il bookmaker può annullarla.</span>
                }
              </li>
            }
          </ul>
        } @else {
          <p class="muted small">Nessuna quota di Sisal o Eurobet oggi paga l'8% o più sopra il giusto.</p>
        }
      }
    </section>
  `,
  styles: `
    .card { padding: 16px 20px; }
    h2 { margin: 0 0 8px; font-size: 20px; color: var(--amber); }
    ul { margin: 0; padding: 0; list-style: none; }
    li { display: flex; flex-direction: column; gap: 1px; padding: 8px 0; border-top: 1px solid var(--line-row); }
    .match { font-weight: 700; color: var(--text); }
    .line { display: flex; justify-content: space-between; gap: 8px; font-size: 13px; color: var(--text-2); }
    .led { margin-left: 4px; font-size: 17px; color: var(--amber); }
    .value { font-weight: 700; color: var(--value); }
    .value.sus, .warn { color: var(--loss); }
  `,
})
export class OffLineCard {
  protected readonly data = httpResource<OffLine[]>(() => '/api/picks/off-line');
  protected readonly odds = odds;
  protected readonly pct = pct;
  protected readonly signed = signedPct;
  protected readonly time = kickoffTime;

  protected label(r: OffLine): string {
    return pickLabel(r.market as Market, r.selection, r.match);
  }

  protected fair(p: number): string {
    return (1 / p).toFixed(2);
  }
}
