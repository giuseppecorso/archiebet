import { httpResource } from '@angular/common/http';
import { Component, computed, effect, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { Competition, CompetitionGroup } from '../../core/football';
import { DataStatusBar } from '../../shared/data-status';
import { MatchRow } from '../../shared/match-row';
import { LeagueLogo } from '../../shared/crest';
import { ShowMore } from '../../shared/show-more';

type Tab = 'prossime' | 'risultati';
type Day = 'tutti' | 'oggi' | 'domani' | 'tre';
/** Paese scelto nella tendina; '' = tutti i paesi */
const ALL_COUNTRIES = '';
const STORAGE_KEY = 'archiebet.matches.filters';

/** Partite: elenco per campionato con filtri per giorno, campionato e squadra. Le partite in corso sono nella sezione Live. */
@Component({
  selector: 'ab-matches',
  imports: [DataStatusBar, MatchRow, ShowMore, LeagueLogo, FormsModule],
  templateUrl: './matches.html',
  styleUrl: './matches.scss',
})
export class Matches {
  private readonly saved = readSaved();

  protected readonly tab = signal<Tab>(this.saved.tab === 'risultati' ? 'risultati' : 'prossime');
  protected readonly day = signal<Day>('tutti');
  protected readonly team = signal('');
  protected readonly days: [Day, string][] = [['tutti', 'Tutti'], ['oggi', 'Oggi'], ['domani', 'Domani'], ['tre', 'Prossimi 3 giorni']];
  /** Campionati esclusi dal filtro (così quelli nuovi compaiono da soli) */
  protected readonly hidden = signal<string[]>(this.saved.hidden ?? []);

  protected readonly country = signal<string>(this.saved.country ?? 'Italia');

  protected readonly competitions = httpResource<Competition[]>(() => '/api/competitions', { defaultValue: [] });
  /** Paesi nell'ordine dato dal backend (Italia in testa) */
  protected readonly countries = computed(() => [...new Set(this.competitions.value().map((c) => c.country))]);
  /** Campionati del paese scelto: sono i chip del filtro */
  protected readonly shown = computed(() =>
    this.competitions.value().filter((c) => this.country() === ALL_COUNTRIES || c.country === this.country()),
  );
  protected readonly selected = computed(() => this.shown().filter((c) => !this.hidden().includes(c.code)));

  private readonly query = computed(() => {
    const codes = this.selected().map((c) => c.code);
    return codes.length ? `&competitions=${codes.join(',')}` : null;
  });

  protected readonly upcoming = httpResource<CompetitionGroup[]>(() => {
    const q = this.query();
    return q && this.tab() === 'prossime' ? `/api/matches?view=upcoming${q}` : undefined;
  });
  protected readonly results = httpResource<CompetitionGroup[]>(() => {
    const q = this.query();
    return q && this.tab() === 'risultati' ? `/api/matches?view=results&limit=40${q}` : undefined;
  });
  /** Prossime partite dopo i filtri di giorno e squadra */
  protected readonly upcomingShown = computed(() => this.filterGroups(this.upcoming.value() ?? [], true));
  protected readonly resultsShown = computed(() => this.filterGroups(this.results.value() ?? [], false));

  constructor() {
    effect(() => {
      try {
        localStorage.setItem(STORAGE_KEY, JSON.stringify({ tab: this.tab(), hidden: this.hidden(), country: this.country() }));
      } catch {
        // memoria del browser non disponibile: i filtri valgono solo per questa visita
      }
    });
  }

  private filterGroups(groups: CompetitionGroup[], byDay: boolean): CompetitionGroup[] {
    const team = this.team().trim().toLowerCase();
    const [from, to] = dayWindow(this.day());
    return groups
      .map((g) => ({
        ...g,
        matches: g.matches.filter((m) => {
          const t = new Date(m.kickoff_at).getTime();
          const dayOk = !byDay || (t >= from && t < to);
          const teamOk = !team || `${m.home.name} ${m.away.name}`.toLowerCase().includes(team);
          return dayOk && teamOk;
        }),
      }))
      .filter((g) => g.matches.length);
  }

  /** Gruppi aperti con "Mostra tutte", chiave "prossime-ITA-A" / "risultati-ITA-A" */
  protected readonly openGroups = signal<string[]>([]);
  /** Partite mostrate per campionato quando il gruppo è chiuso */
  protected readonly groupLimit = computed(() => (this.team() || this.day() !== 'tutti' ? 50 : 10));

  protected isGroupOpen(key: string): boolean {
    return this.openGroups().includes(key);
  }

  protected setGroupOpen(key: string, open: boolean): void {
    this.openGroups.update((keys) => (open ? [...keys, key] : keys.filter((k) => k !== key)));
  }

  protected toggle(code: string): void {
    this.hidden.update((h) => (h.includes(code) ? h.filter((c) => c !== code) : [...h, code]));
  }

  /** Nota per i gruppi fermi a una stagione passata (es. Serie C con il piano gratuito di API-Football) */
  protected staleNote(group: CompetitionGroup): string | null {
    const latest = group.matches[0];
    if (!latest) return null;
    const ageDays = (Date.now() - new Date(latest.kickoff_at).getTime()) / 86_400_000;
    return ageDays > 60 ? `Dati fino alla stagione ${latest.season}: la stagione in corso arriverà con il piano completo della fonte` : null;
  }

  protected isOn(code: string): boolean {
    return !this.hidden().includes(code);
  }
}

function readSaved(): { tab?: Tab; hidden?: string[]; country?: string } {
  try {
    return JSON.parse(localStorage.getItem(STORAGE_KEY) ?? '{}');
  } catch {
    return {};
  }
}

/** Finestra di tempo del filtro "giorno" (ora del browser) */
export function dayWindow(day: Day, now: Date = new Date()): [number, number] {
  const midnight = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime();
  const DAY = 86_400_000;
  if (day === 'oggi') return [midnight, midnight + DAY];
  if (day === 'domani') return [midnight + DAY, midnight + 2 * DAY];
  if (day === 'tre') return [midnight, midnight + 3 * DAY];
  return [-Infinity, Infinity];
}
