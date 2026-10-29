import { httpResource } from '@angular/common/http';
import { Component, computed } from '@angular/core';
import { RouterLink } from '@angular/router';
import { Bet, euro, pickLabel } from '../../core/bets';
import { CompetitionGroup } from '../../core/football';
import { kickoffTime, longDate, odds, pct, signedPct } from '../../core/format';
import { RadarOut } from '../../core/radar';
import { ArchieTv } from '../../shared/archie-tv';
import { MatchRow } from '../../shared/match-row';

const ITALY_FIRST = ['ITA-A', 'ITA-B', 'ITA-C-A', 'ITA-C-B', 'ITA-C-C'];

/** Home "Oggi": partite di oggi, occasioni del momento, le tue giocate in corso e ArchieTV. */
@Component({
  selector: 'ab-home',
  imports: [RouterLink, MatchRow, ArchieTv],
  templateUrl: './home.html',
  styleUrl: './home.scss',
})
export class Home {
  protected readonly fmt = { kickoffTime, longDate, odds, pct, signedPct, euro, pickLabel };
  protected readonly today = new Date().toISOString();

  protected readonly upcoming = httpResource<CompetitionGroup[]>(() => '/api/matches?view=upcoming&limit=200', { defaultValue: [] });
  protected readonly radar = httpResource<RadarOut>(() => '/api/radar');
  protected readonly bets = httpResource<Bet[]>(() => '/api/bets', { defaultValue: [] });

  /** Partite di oggi, l'Italia in testa, al massimo 12 */
  /** Il pronostico più solido di Archie per ogni partita di oggi */
  protected readonly headlines = httpResource<Record<number, { event: string; p_archie: number }>>(() => '/api/study/headlines?horizon=today', { defaultValue: {} });
  protected readonly todayMatches = computed(() => {
    const picks = this.headlines.value();
    const end = new Date();
    end.setHours(24, 0, 0, 0);
    const groups = this.upcoming.value();
    const rank = (code: string) => (ITALY_FIRST.includes(code) ? ITALY_FIRST.indexOf(code) : 99);
    return groups
      .flatMap((g) => g.matches)
      .filter((m) => new Date(m.kickoff_at).getTime() < end.getTime())
      .filter((m) => !!m.odds_1x2 || !!picks[m.id]) // solo partite con le quote o con un pronostico di Archie
      .sort((a, b) => rank(a.competition.code) - rank(b.competition.code) || Number(!a.odds_1x2) - Number(!b.odds_1x2) || a.kickoff_at.localeCompare(b.kickoff_at))
      .slice(0, 12);
  });
  protected readonly occasions = computed(() => (this.radar.value()?.upcoming ?? []).filter((o) => !o.secondary).slice(0, 5));
  protected readonly openBets = computed(() => this.bets.value().filter((b) => b.status === 'open').slice(0, 4));
}
