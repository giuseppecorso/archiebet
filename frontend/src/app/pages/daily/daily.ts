import { httpResource } from '@angular/common/http';
import { Component, computed, signal } from '@angular/core';
import { RouterLink } from '@angular/router';
import { balanceOption, monthsOption, oddsOption } from '../../core/charts';
import { DailyOut, DailySlip } from '../../core/daily';
import { dayLabel, kickoffTime, odds, pct } from '../../core/format';
import { Chart } from '../../shared/chart';
import { PushToggle } from '../../shared/push-toggle';
import { lineup, rowSizes } from './lineup';
import { slipImage } from './slip-image';

/** Bacheca Daily (D153): le schedine pubblicate da Archie, appese come foglietti, con le statistiche per tutti. */
@Component({
  selector: 'ab-daily',
  imports: [Chart, PushToggle, RouterLink],
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

      @if (d.board.length) {
        <div class="pitch" [style.--rows]="rows(d.board.length)" role="group" aria-label="Le giocate di Archie in campo">
          <span class="line half" aria-hidden="true"></span>
          <span class="line circle" aria-hidden="true"></span>
          <span class="line area top" aria-hidden="true"></span>
          <span class="line area bottom" aria-hidden="true"></span>
          @for (s of d.board; track s.id; let i = $index) {
            <button type="button" class="player" [attr.data-status]="s.status" [class.on]="current(d)?.id === s.id" [attr.aria-pressed]="current(d)?.id === s.id"
                    [style.left.%]="spots(d.board.length)[i].x" [style.top.%]="spots(d.board.length)[i].y" (click)="selected.set(s.id)">
              <span class="shirt">{{ s.legs.length }}</span>
              <span class="name">{{ s.title }}</span>
            </button>
          }
        </div>
        <p class="pitch-hint muted small">Ogni giocatore è una giocata di Archie: il numero sulla maglia dice quante partite ha dentro. Toccalo per leggerla.</p>
      }
      <div class="sheet">
        @if (current(d); as s) {
          <article class="note" [attr.data-status]="s.status">
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
                  @if (l.recheck; as r) {
                    <span class="recheck" role="note">
                      <b>Archie ricontrolla</b> (in prova): il mercato è cambiato. Questo pronostico è sceso dal {{ pct(r.p_before) }} al {{ pct(r.p_now) }};
                      ora è più probabile <b>{{ r.event }}</b> ({{ pct(r.p_new) }}).
                    </span>
                  }
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
              <span class="played" title="D192: ogni schedina del Daily si gioca da sola e finisce nelle tue statistiche">Giocata da sola · 1 €{{ s.singles ? ' a pronostico' : '' }}</span>
              <button type="button" class="share" (click)="share(s)">Immagine</button>
            </footer>
            @if (s.status !== 'open') {
              <span class="stamp" [attr.data-status]="s.status">{{ stampOf(s) }}</span>
            }
          </article>
        } @else {
          <p class="empty">Il campo è vuoto: le prime giocate entrano alle 10 del mattino.</p>
        }
      </div>

      <p class="next muted small">
        <strong>Quando escono:</strong> ogni giorno alle 10 la schedina del giorno, il colpo, la schedina 6–10 e la schedina del CLV ·
        il venerdì il weekend e il sistemone · il lunedì la settimana e la pazza della settimana.
      </p>

      <section class="panel box stats" aria-labelledby="st-title">
        <h2 id="st-title" class="title box-title">Statistiche della bacheca</h2>
        <div class="kpis">
          <div class="kpi"><span class="label">Schedine pubblicate</span><span class="led">{{ totals(d).published }}</span></div>
          <div class="kpi"><span class="label">Pronostici giusti</span><span class="led">{{ totals(d).won }}<span class="small muted">/{{ totals(d).closed }}</span></span><span class="muted small">{{ pct(totals(d).closed ? totals(d).won / totals(d).closed : null) }}</span></div>
          <div class="kpi"><span class="label">Con 1 € a schedina</span><span [class]="'led ' + (totals(d).profit > 0 ? 'pos' : totals(d).profit < 0 ? 'neg' : '')">{{ money(totals(d).profit) }}</span></div>
        </div>
        <div class="charts">
          <div class="chart-card">
            <h3 class="title chart-title">Se avessi giocato 1 € su ogni schedina</h3>
            @if ((d.charts?.days?.length ?? 0) > 1) {
              <ab-chart [option]="balanceChart()" label="Utile cumulato giocando 1 euro su ogni schedina" />
            } @else {
              <p class="muted small">Il grafico compare dopo almeno due giorni di schedine chiuse.</p>
            }
          </div>
          <div class="chart-card">
            <h3 class="title chart-title">Schedine vinte e perse, mese per mese</h3>
            @if (d.charts?.months?.length) {
              <ab-chart [option]="monthsChart()" label="Schedine vinte e perse per mese" />
            } @else {
              <p class="muted small">Ancora nessuna schedina chiusa.</p>
            }
          </div>
          <div class="chart-card">
            <h3 class="title chart-title">Pronostici giusti per schedina</h3>
            @if (hasBars(d.charts?.by_kind)) {
              <ab-chart [option]="kindChart()" label="Pronostici azzeccati per tipo di schedina, contro quelli attesi" />
            } @else {
              <p class="muted small">Ancora nessun pronostico chiuso.</p>
            }
          </div>
          <div class="chart-card">
            <h3 class="title chart-title">Pronostici giusti per fascia di quota</h3>
            @if (hasBars(d.charts?.by_odds)) {
              <ab-chart [option]="oddsChart()" label="Pronostici azzeccati per fascia di quota, contro quelli attesi" />
            } @else {
              <p class="muted small">Ancora nessun pronostico chiuso.</p>
            }
          </div>
        </div>
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
        <p class="muted small">"Attese" = quante dovevano uscire sommando le probabilità di Archie: se le uscite restano vicine alle attese, Archie è onesto con le sue percentuali. "Con 1 €": dove manca la quota di un bookmaker si usa quella giusta meno il 6% di margine.</p>
      </section>

      @if (d.history.length) {
        <details class="archive">
          <summary class="title">Archivio dell'ultima settimana <span class="muted small">({{ d.history.length }})</span></summary>
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
  protected readonly data = httpResource<DailyOut>(() => '/api/daily');
  /** La giocata aperta sotto il campo (null = la prima) */
  protected readonly selected = signal<number | null>(null);
  protected current(d: DailyOut): DailySlip | undefined {
    return d.board.find((s) => s.id === this.selected()) ?? d.board[0];
  }
  protected readonly spots = lineup;
  protected rows(players: number): number {
    return rowSizes(players).length + 1;
  }
  protected readonly pct = pct;
  protected readonly fmtOdds = odds;
  protected readonly dayLabel = dayLabel;
  protected readonly time = (iso: string) => kickoffTime(iso);

  /** Grafici (D173): tutte le schedine chiuse, anche quelle uscite dall'archivio */
  private readonly charts = computed(() => (this.data.hasValue() ? this.data.value().charts : undefined));
  protected readonly balanceChart = computed(() => balanceOption(this.charts()?.days ?? []));
  protected readonly monthsChart = computed(() => monthsOption(this.charts()?.months ?? []));
  protected readonly kindChart = computed(() => oddsOption(this.charts()?.by_kind ?? [], { expected: 'Attesi da Archie', prefix: '', rotate: 35, marker: 26 }));
  protected readonly oddsChart = computed(() => oddsOption(this.charts()?.by_odds ?? [], { expected: 'Attesi da Archie' }));

  protected hasBars(bands: { selections: number }[] | undefined): boolean {
    return (bands ?? []).some((b) => b.selections > 0);
  }

  protected totals(d: DailyOut): { published: number; won: number; closed: number; profit: number } {
    return d.stats.reduce((t, k) => ({ published: t.published + k.published, won: t.won + k.legs_won, closed: t.closed + k.legs_closed, profit: t.profit + k.profit }), { published: 0, won: 0, closed: 0, profit: 0 });
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

  protected hasSources(d: DailyOut): boolean {
    return (d.by_source ?? []).some((x) => x.closed > 0);
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
