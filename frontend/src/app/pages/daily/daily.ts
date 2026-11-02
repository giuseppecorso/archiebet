import { HttpClient, httpResource } from '@angular/common/http';
import { Component, inject, signal } from '@angular/core';
import { firstValueFrom } from 'rxjs';
import { Bet } from '../../core/bets';
import { RouterLink } from '@angular/router';
import { DailyLeg, DailyOut, DailySlip } from '../../core/daily';
import { SlipLeg, SlipService } from '../../core/slip';
import { dayLabel, kickoffTime, odds, pct } from '../../core/format';
import { PushToggle } from '../../shared/push-toggle';
import { slipImage } from './slip-image';

/** Bacheca Daily (D153): le schedine pubblicate da Archie, appese come foglietti, con le statistiche per tutti. */
@Component({
  selector: 'ab-daily',
  imports: [PushToggle, RouterLink],
  template: `
    @if (data.value(); as d) {
      <p class="intro">
        Ogni mattina alle 10 Archie appende qui le sue schedine. <strong>Una volta pubblicate non cambiano più</strong>:
        sotto trovi quante sono uscite davvero, contro quante dovevano uscire secondo le sue probabilità.
      </p>
      <div class="panel box notify"><ab-push-toggle /></div>
      @if (d.today.legs_total) {
        <p class="today">
          Oggi: <strong class="led">{{ d.today.legs_won }}/{{ d.today.legs_closed }}</strong> pronostici azzeccati tra quelli già finiti
          <span class="muted small">({{ d.today.legs_total }} pubblicati)</span>
        </p>
      }

      @if (playableSlips(d).length) {
        <div class="panel box play-all">
          <span>Gioca in un colpo tutte le schedine aperte di oggi</span>
          <label>€ a schedina <input type="number" inputmode="decimal" min="0.5" step="0.5" [value]="allStake()" (input)="allStake.set(+$any($event.target).value || 0)" /></label>
          <button type="button" class="btn-primary" (click)="playAll(d)" [disabled]="busy() || allStake() <= 0">Gioca tutte</button>
          @if (allMsg(); as m) {
            <p class="small" [class.err]="!m.ok" role="status">{{ m.text }}</p>
          }
        </div>
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
                  <span class="meta">{{ dayLabel(l.kickoff_at) }} {{ time(l.kickoff_at) }} · {{ pct(l.p) }} · quota {{ fmtOdds(l.price) }}@if (l.score) { · <strong>finita {{ l.score }}</strong> }</span>
                  <span class="mark" aria-hidden="true">{{ mark(l.status) }}</span>
                </li>
              }
            </ol>
            <footer>
              @if (s.singles) {
                <span>Da giocare singole · 1 € ciascuna</span>
              } @else if (s.system) {
                <span>Sistema <strong>{{ s.system }} su {{ s.legs.length }}</strong> · con almeno {{ s.system }} giuste incassi qualcosa:
                  {{ pct(s.win_probability) }} delle volte · con 1 € al massimo {{ fmtOdds(s.total_odds) }} €</span>
              } @else if (s.kind === 'pazza') {
                <span>Quota <strong>{{ fmtOdds(s.total_odds) }}</strong> · esce circa 1 volta su {{ oneIn(s.win_probability) }}: è un gioco, punta poco</span>
              } @else {
                <span>Quota <strong>{{ fmtOdds(s.total_odds) }}</strong> · esce 1 volta su {{ oneIn(s.win_probability) }}</span>
              }
              @if (playable(s).length) {
                <button type="button" class="share play" (click)="play(s)">Gioca</button>
              }
              <button type="button" class="share" (click)="share(s)">Immagine</button>
            </footer>
            @if (s.status !== 'open') {
              <span class="stamp" [attr.data-status]="s.status">{{ stampOf(s) }}</span>
            }
          </article>
        } @empty {
          <p class="empty">La bacheca è vuota: le prime schedine arrivano alle 10 del mattino.</p>
        }
      </div>

      <p class="next muted small">
        <strong>Quando escono:</strong> ogni giorno alle 10 la schedina del giorno, il colpo e la schedina del CLV ·
        il venerdì il weekend e il sistemone · il lunedì la settimana e la pazza della settimana.
      </p>

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
        @if (hasSources(d)) {
          <ul class="sources">
            @for (x of d.by_source; track x.label) {
              @if (x.closed) {
                <li><strong>{{ x.label }}</strong>: {{ x.won }} azzeccati su {{ x.closed }} <span class="muted small">(attesi {{ x.expected }})</span></li>
              }
            }
          </ul>
        }
        <p class="muted small">"Attese" = quante dovevano uscire sommando le probabilità di Archie: se le uscite restano vicine alle attese, Archie è onesto con le sue percentuali.</p>
      </section>

      @if (d.history.length) {
        <details class="archive">
          <summary class="title">Archivio delle schedine <span class="muted small">({{ d.history.length }})</span></summary>
          <div class="cork small-cork">
            @for (s of d.history.slice(0, archiveAll() ? undefined : ARCHIVE_SHOWN); track s.id) {
              <article class="note mini" [attr.data-status]="s.status">
                <header>
                  <h2>{{ s.title }}</h2>
                  <span class="when">{{ dayLabel(s.period + 'T12:00:00') }}</span>
                </header>
                <ol>
                  @for (l of s.legs; track l.match_id + l.market) {
                    <li [attr.data-status]="l.status">
                      <span class="m">{{ l.home }} – {{ l.away }} @if (l.score) { <strong class="score">{{ l.score }}</strong> }</span>
                      <span class="e">{{ capital(l.event) }}</span>
                      <span class="mark" aria-hidden="true">{{ mark(l.status) }}</span>
                    </li>
                  }
                </ol>
                <span class="stamp" [attr.data-status]="s.status">{{ stampOf(s) }}</span>
              </article>
            }
          </div>
          @if (d.history.length > ARCHIVE_SHOWN) {
            <button type="button" class="more" (click)="archiveAll.set(!archiveAll())">{{ archiveAll() ? 'Mostra meno' : 'Mostra le più vecchie (' + (d.history.length - ARCHIVE_SHOWN) + ')' }}</button>
          }
        </details>
      }
    } @else if (data.isLoading()) {
      <p class="muted">Carico la bacheca…</p>
    }
  `,
  styleUrl: './daily.scss',
})
export class Daily {
  private readonly slip = inject(SlipService);
  private readonly http = inject(HttpClient);
  protected readonly data = httpResource<DailyOut>(() => '/api/daily');
  protected readonly pct = pct;
  protected readonly fmtOdds = odds;
  protected readonly dayLabel = dayLabel;
  protected readonly time = (iso: string) => kickoffTime(iso);

  /** Pronostici ancora da giocare (partita non iniziata) */
  protected playable(s: DailySlip): DailyLeg[] {
    return s.status === 'open' ? s.legs.filter((l) => l.status === 'open' && new Date(l.kickoff_at).getTime() > Date.now()) : [];
  }

  /** Mette la schedina nella Schedina: lì si sceglie simulata o reale e l'importo. Il sistema resta tale se tutte le partite sono ancora da giocare. */
  protected play(s: DailySlip): void {
    const legs = this.playable(s);
    const team = (name: string) => ({ id: 0, name }) as SlipLeg['match']['home'];
    this.slip.fill(
      legs.map((l) => ({
        match: { id: l.match_id, home: team(l.home), away: team(l.away), kickoff_at: l.kickoff_at, competition: { name: l.competition } as SlipLeg['match']['competition'] },
        market: l.market,
        pick: l.selection,
        odds: l.price,
        bookmaker: null,
      })),
      s.system && legs.length === s.legs.length ? s.system : null,
    );
  }

  protected capital(text: string): string {
    return text.charAt(0).toUpperCase() + text.slice(1);
  }

  protected oneIn(p: number): string {
    return p > 0 ? String(Math.max(1, Math.round(1 / p))) : '–';
  }

  protected mark(status: string): string {
    return status === 'won' ? '✓' : status === 'lost' ? '✗' : status === 'void' ? '–' : '';
  }

  /** Timbro: per le singole (CLV) quante sono uscite, per le altre vinta o persa */
  protected stampOf(s: DailySlip): string {
    if (s.singles && s.status === 'done') {
      const closed = s.legs.filter((l) => l.status === 'won' || l.status === 'lost');
      return `${closed.filter((l) => l.status === 'won').length} su ${closed.length}`;
    }
    return { won: 'Vinta', lost: 'Persa', void: 'Annullata', done: 'Chiusa', open: 'In corso' }[s.status] ?? s.status;
  }

  protected readonly ARCHIVE_SHOWN = 6;
  protected readonly archiveAll = signal(false);
  protected readonly allStake = signal(5);
  protected readonly busy = signal(false);
  protected readonly allMsg = signal<{ ok: boolean; text: string } | null>(null);

  protected hasSources(d: DailyOut): boolean {
    return (d.by_source ?? []).some((x) => x.closed > 0);
  }

  protected playableSlips(d: DailyOut): DailySlip[] {
    return d.board.filter((s) => this.playable(s).length);
  }

  /** Firma di una giocata: le sue partite ed esiti, in ordine (per riconoscere una schedina già giocata) */
  private signature(legs: { match_id: number; market: string; pick: string }[]): string {
    return legs.map((l) => `${l.match_id}:${l.market}:${l.pick}`).sort().join('|');
  }

  /** Registra tutte le schedine aperte della bacheca; salta quelle già giocate (stesse partite ed esiti) */
  protected async playAll(d: DailyOut): Promise<void> {
    this.busy.set(true);
    this.allMsg.set(null);
    try {
      const mine = await firstValueFrom(this.http.get<Bet[]>('/api/bets'));
      const done = new Set(mine.map((b) => this.signature(b.selections.map((s) => ({ match_id: s.match.id, market: s.market, pick: s.pick })))));
      let played = 0;
      let skipped = 0;
      for (const s of this.playableSlips(d)) {
        const legs = this.playable(s);
        const groups = s.singles ? legs.map((l) => [l]) : [legs];
        for (const g of groups) {
          const sig = this.signature(g.map((l) => ({ match_id: l.match_id, market: l.market, pick: l.selection })));
          if (done.has(sig)) {
            skipped++;
            continue;
          }
          await firstValueFrom(this.http.post('/api/bets', {
            stake: this.allStake().toFixed(2),
            note: s.title,
            selections: g.map((l) => ({ match_id: l.match_id, market: l.market, pick: l.selection, odds: l.price.toFixed(3) })),
            system: s.system && g.length === s.legs.length ? s.system : null,
          }));
          done.add(sig);
          played++;
        }
      }
      this.allMsg.set(
        played
          ? { ok: true, text: `Fatto: ${played} giocate registrate${skipped ? `, ${skipped} saltate perché le avevi già giocate` : ''}. Le trovi in Il mio Archie.` }
          : { ok: false, text: 'Le avevi già giocate tutte: nessuna giocata nuova.' },
      );
    } catch {
      this.allMsg.set({ ok: false, text: 'Qualcosa non è andato: alcune giocate potrebbero non essere state registrate. Controlla in Il mio Archie.' });
    } finally {
      this.busy.set(false);
    }
  }

  protected money(n: number): string {
    return (n > 0 ? '+' : '') + n.toLocaleString('it-IT', { style: 'currency', currency: 'EUR' });
  }

  /** Immagine quadrata da condividere (Instagram): sul telefono si apre la condivisione, sul PC si scarica */
  protected async share(s: DailySlip): Promise<void> {
    const blob = await slipImage(s);
    const file = new File([blob], `archie-${s.kind}-${s.period}.png`, { type: 'image/png' });
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
