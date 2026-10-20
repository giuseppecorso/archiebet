import { Component, computed, effect, input, signal } from '@angular/core';
import { RouterLink } from '@angular/router';
import { Market, pickLabel } from '../core/bets';
import { MatchCard } from '../core/football';
import { dayLabel, kickoffTime, odds, pct, signedPct } from '../core/format';
import { MultiplesOut } from '../core/multiple';
import { Crest } from './crest';

/** Una multipla calcolata da Archie (D68): gambe, numeri e avviso onesto se non ha valore. */
@Component({
  selector: 'ab-multiple-view',
  imports: [RouterLink, Crest],
  template: `
    @let d = data();
    @if (d.multiples.length > 1) {
      <div class="books" role="tablist" aria-label="Bookmaker">
        @for (m of d.multiples; track m.bookmaker; let i = $index) {
          <button type="button" role="tab" [attr.aria-selected]="index() === i" (click)="index.set(i)">{{ m.bookmaker }}</button>
        }
      </div>
    }
    @if (current(); as m) {
      @if (d.multiples.length === 1) {
        <span class="muted small">su {{ m.bookmaker }}</span>
      }
      <ol class="legs">
        @for (l of m.legs; track l.match.id) {
          <li>
            <span class="when muted small">{{ day(l.match.kickoff_at) }} {{ time(l.match.kickoff_at) }} · {{ l.match.competition.name }}</span>
            <a [routerLink]="['/partite', l.match.id]" class="match"><ab-crest [team]="l.match.home" [size]="18" /> {{ l.match.home.name }} – {{ l.match.away.name }} <ab-crest [team]="l.match.away" [size]="18" /></a>
            <span class="pick">{{ label(l.market, l.selection, l.match) }}</span>
            <span class="nums"><span class="muted small">{{ pct(l.probability) }}</span><span class="led">{{ odds(l.price) }}</span></span>
          </li>
        }
      </ol>
      <dl class="stats">
        <div><dt>Quota</dt><dd class="led">{{ odds(m.price) }}</dd></div>
        <div><dt>Con {{ stake() }} €</dt><dd class="led">{{ win(m.price) }} €</dd></div>
        <div><dt>Vinci</dt><dd>{{ pct(m.win_probability) }} <span class="muted small">· 1 volta su {{ oneIn(m.one_in) }}</span></dd></div>
        <div><dt>Vivo all'ultima</dt><dd>{{ pct(m.alive_before_last) }}</dd></div>
        <div><dt>Valore atteso</dt><dd [class]="m.expected_value >= 0 ? 'pos' : 'neg'">{{ signed(m.expected_value) }}</dd></div>
      </dl>
      @if (m.with_value) {
        <p class="note pos">Tutte le partite hanno valore: Archie la giocherebbe.</p>
      } @else {
        <p class="note">
          Nessuna multipla con valore: questa è la migliore con quote nella norma. Il margine dei bookmaker si moltiplica:
          giocata sempre, nel lungo periodo fa perdere circa il {{ loss(m.expected_value) }} di quanto giochi.
          Rifatta su 5 stagioni passate, la multipla del giorno è uscita quanto previsto (72 volte contro 72 attese) e ha reso −9,6%.
        </p>
      }
      @if (d.missing.length) {
        <p class="muted small">Su {{ d.missing.join(' e ') }} non c'è una multipla sensata.</p>
      }
    } @else {
      <p class="muted">{{ empty() }}</p>
    }
  `,
  styles: `
    .books { display: flex; width: fit-content; margin-bottom: 8px; border: 1px solid var(--line-strong); border-radius: 4px; overflow: hidden; }
    .books button {
      min-height: 30px; padding: 2px 10px; font: inherit; font-size: 12px; font-weight: 600;
      color: var(--text-2); background: transparent; border: 0; cursor: pointer;
    }
    .books button + button { border-left: 1px solid var(--line-strong); }
    .books button[aria-selected='true'] { color: var(--bg); background: var(--text); }
    .legs { margin: 8px 0 0; padding: 0; list-style: none; }
    .legs li { display: grid; grid-template-columns: 1fr auto; gap: 0 8px; padding: 8px 0; border-top: 1px solid var(--line-row); }
    .legs .when { grid-column: 1 / -1; }
    .legs .match { display: inline-flex; align-items: center; gap: 6px; font-weight: 700; color: var(--text); }
    .legs .pick { grid-column: 1; font-size: 13px; color: var(--text-2); }
    .legs .nums { grid-column: 2; grid-row: 2 / span 2; align-self: center; text-align: right; }
    .legs .led { margin-left: 6px; font-size: 18px; color: var(--amber); }
    .stats { display: grid; grid-template-columns: repeat(auto-fill, minmax(130px, 1fr)); gap: 6px; margin: 10px 0 0; }
    .stats div { padding: 6px 8px; background: var(--bg-deep); border: 1px solid var(--line-strong); border-radius: 4px; }
    .stats dt { font-size: 10px; font-weight: 700; letter-spacing: 1px; color: var(--muted); text-transform: uppercase; }
    .stats dd { margin: 2px 0 0; font-weight: 700; }
    .stats .led { font-size: 18px; color: var(--amber); }
    .pos { color: var(--value); }
    .neg { color: var(--loss); }
    .note { margin: 10px 0 0; font-size: 12px; color: var(--text-2); }
    .note.pos { color: var(--value); }
  `,
})
export class MultipleView {
  readonly data = input.required<MultiplesOut>();
  readonly stake = input(10);
  /** Testo quando non c'è nessuna multipla */
  readonly empty = input('Nessuna multipla sensata: meglio non giocare, o guardare le singole nei Pronostici.');

  protected readonly index = signal(0);
  protected readonly current = computed(() => {
    const list = this.data().multiples;
    return list[Math.min(this.index(), list.length - 1)];
  });
  protected readonly odds = odds;
  protected readonly pct = pct;
  protected readonly signed = signedPct;
  protected readonly day = dayLabel;
  protected readonly time = kickoffTime;

  constructor() {
    // Dati nuovi (altro orizzonte o altri filtri): si riparte dal primo bookmaker
    effect(() => {
      this.data();
      this.index.set(0);
    });
  }

  protected label(market: string, selection: string, match: MatchCard): string {
    return pickLabel(market as Market, selection, match);
  }

  protected win(price: number): string {
    return (price * this.stake()).toLocaleString('it-IT', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  }

  protected oneIn(n: number): string {
    return n.toLocaleString('it-IT', { maximumFractionDigits: 1 });
  }

  /** Perdita attesa in percentuale, senza segno: −0.078 → "7,8%" */
  protected loss(expectedValue: number): string {
    return signedPct(-expectedValue).replace('+', '');
  }
}
