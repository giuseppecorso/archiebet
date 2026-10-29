import { httpResource } from '@angular/common/http';
import { Component, computed } from '@angular/core';
import { MIO_ARCHIE_TABS } from '../../core/sections';
import { dayLabel, pct } from '../../core/format';
import { CoinsCard } from '../../shared/coins-card';
import { Subnav } from '../../shared/subnav';

interface ProfileOut {
  username: string;
  display_name: string | null;
  since: string;
  bets: number;
  won: number;
  lost: number;
  coins: number;
  premium_until: string;
  premium_active: boolean;
  specialty: { name: string; won: number; closed: number } | null;
  badges: { key: string; title: string; text: string; got: boolean }[];
  months: { month: string; bets: number; won: number; coins: number }[];
  team: string | null;
  team_record: { picks: number; won: number; lost: number } | null;
}

interface LeaderRow {
  username: string;
  coins: number;
  bets: number;
  hit_rate: number | null;
  me: boolean;
}

const MONTHS = ['gen', 'feb', 'mar', 'apr', 'mag', 'giu', 'lug', 'ago', 'set', 'ott', 'nov', 'dic'];
const ICONS: Record<string, string> = { prima: '🎯', dieci: '📒', serie: '🔥', colpo: '💥', cento: '🪙', mille: '🏆' };

/** Il tuo profilo (D161): chi sei, monete, specialità, traguardi, andamento, squadra del cuore, classifica tra amici. */
@Component({
  selector: 'ab-profile',
  imports: [CoinsCard, Subnav],
  template: `
    <h1 class="title page-title">Il mio Archie</h1>
    <ab-subnav [items]="tabs" label="Il mio Archie" />

    @if (data.value(); as p) {
      <section class="panel box who">
        <img src="archie-512.png" alt="" width="56" height="56" />
        <div>
          <h2 class="title name">{{ p.display_name || p.username }}</h2>
          <p class="muted small">Gioca con Archie da {{ day(p.since).toLowerCase() }} · {{ p.bets }} giocate · {{ p.won }} vinte · {{ p.lost }} perse</p>
          @if (p.specialty; as s) {
            <p class="spec">La tua specialità: <strong>{{ s.name }}</strong>&nbsp;<span class="muted small">({{ s.won }} azzeccati su {{ s.closed }})</span></p>
          } @else {
            <p class="muted small">La tua specialità compare dopo 5 pronostici chiusi dello stesso tipo.</p>
          }
        </div>
      </section>

      <ab-coins-card />

      <section class="panel box">
        <h2 class="title box-title">Traguardi</h2>
        <ul class="badges">
          @for (b of p.badges; track b.key) {
            <li [class.got]="b.got" [title]="b.text">
              <span class="ico" aria-hidden="true">{{ icon(b.key) }}</span>
              <strong>{{ b.title }}</strong>
              <span class="small muted">{{ b.got ? 'Fatto!' : b.text }}</span>
            </li>
          }
        </ul>
      </section>

      <section class="panel box">
        <h2 class="title box-title">Classifica tra amici</h2>
        <ol class="board">
          @for (r of leaders.value(); track r.username; let i = $index) {
            <li [class.me]="r.me">
              <span class="pos">{{ i + 1 }}</span>
              <span class="who-name">{{ r.username }}</span>
              <span class="small muted">{{ r.bets }} giocate · {{ r.hit_rate == null ? '–' : pct(r.hit_rate) + ' azzeccati' }}</span>
              <span class="led">{{ r.coins }} 🪙</span>
            </li>
          }
        </ol>
      </section>

      <section class="panel box">
        <h2 class="title box-title">Andamento</h2>
        @if (p.months.length) {
          <div class="chart" role="img" [attr.aria-label]="'Monete per mese'">
            @for (m of p.months; track m.month) {
              <div class="col">
                <span class="val small">{{ m.coins }}</span>
                <span class="bar" [style.height.%]="barHeight(m.coins)"></span>
                <span class="lab small muted">{{ monthLabel(m.month) }}</span>
                <span class="sub small muted">{{ m.won }}/{{ m.bets }}</span>
              </div>
            }
          </div>
          <p class="muted small">Monete guadagnate ogni mese; sotto, giocate vinte su giocate fatte.</p>
        } @else {
          <p class="muted">Ancora nessuna giocata: il grafico si riempie mese dopo mese.</p>
        }
      </section>

      <section class="panel box">
        <h2 class="title box-title">La tua squadra</h2>
        @if (p.team) {
          @if (p.team_record; as t) {
            <p><strong>{{ p.team }}</strong>: {{ t.picks }} pronostici sulle sue partite · {{ t.won }} azzeccati · {{ t.lost }} sbagliati</p>
          }
        } @else {
          <p class="muted">Scegli la squadra del cuore nelle Impostazioni (icona in alto a destra) per vedere come vanno i tuoi pronostici sulle sue partite.</p>
        }
      </section>
    }
  `,
  styles: `
    .panel { margin-bottom: 12px; }
    .who { display: flex; gap: 14px; align-items: center; }
    .who img { border-radius: 12px; }
    .name { margin: 0; font-size: 22px; color: var(--amber); }
    .who p { margin: 2px 0; }
    .badges { display: grid; grid-template-columns: repeat(auto-fill, minmax(150px, 1fr)); gap: 8px; margin: 0; padding: 0; list-style: none; }
    .badges li { display: flex; flex-direction: column; gap: 2px; padding: 8px 10px; border: 1px dashed var(--line-strong); border-radius: 8px; opacity: 0.55; }
    .badges li.got { opacity: 1; border-style: solid; border-color: var(--amber); }
    .ico { font-size: 22px; }
    .board { margin: 0; padding: 0; list-style: none; }
    .board li { display: grid; grid-template-columns: 24px 1fr auto; gap: 2px 10px; align-items: baseline; padding: 6px 0; border-bottom: 1px solid var(--line-row); }
    .board li .small { grid-column: 2; }
    .board li .led { grid-column: 3; grid-row: 1 / span 2; }
    .board li.me .who-name { color: var(--amber); font-weight: 700; }
    .pos { grid-row: 1 / span 2; font-weight: 700; color: var(--muted); }
    .chart { display: flex; align-items: flex-end; gap: 10px; height: 160px; padding-top: 10px; overflow-x: auto; }
    .col { display: flex; flex-direction: column; align-items: center; justify-content: flex-end; min-width: 38px; height: 100%; }
    .bar { width: 22px; min-height: 2px; background: var(--amber); border-radius: 3px 3px 0 0; }
  `,
})
export class ProfilePage {
  protected readonly tabs = MIO_ARCHIE_TABS;
  protected readonly data = httpResource<ProfileOut>(() => '/api/profile');
  protected readonly leaders = httpResource<LeaderRow[]>(() => '/api/profile/leaderboard', { defaultValue: [] });
  protected readonly pct = pct;
  protected readonly day = dayLabel;
  private readonly maxCoins = computed(() => Math.max(1, ...(this.data.value()?.months ?? []).map((m) => m.coins)));

  protected icon(key: string): string {
    return ICONS[key] ?? '⭐';
  }

  protected barHeight(coins: number): number {
    return Math.round((coins / this.maxCoins()) * 70);
  }

  protected monthLabel(month: string): string {
    const [y, m] = month.split('-');
    return `${MONTHS[+m - 1]} ${y.slice(2)}`;
  }
}
