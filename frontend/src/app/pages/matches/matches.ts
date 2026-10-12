import { httpResource } from '@angular/common/http';
import { Component, computed, effect, signal } from '@angular/core';
import { Competition, CompetitionGroup } from '../../core/football';
import { DataStatusBar } from '../../shared/data-status';
import { MatchRow } from '../../shared/match-row';
import { ShowMore } from '../../shared/show-more';

type Tab = 'tutte' | 'prossime' | 'risultati';
const STORAGE_KEY = 'archiebet.matches.filters';

/** Dashboard "Partite": elenco per campionato con filtri. Multipla, schedina e ArchieTV arrivano nelle fasi successive. */
@Component({
  selector: 'ab-matches',
  imports: [DataStatusBar, MatchRow, ShowMore],
  templateUrl: './matches.html',
  styleUrl: './matches.scss',
})
export class Matches {
  private readonly saved = readSaved();

  protected readonly tab = signal<Tab>(this.saved.tab ?? 'tutte');
  /** Campionati esclusi dal filtro (così quelli nuovi compaiono da soli) */
  protected readonly hidden = signal<string[]>(this.saved.hidden ?? []);

  protected readonly competitions = httpResource<Competition[]>(() => '/api/competitions', { defaultValue: [] });
  protected readonly selected = computed(() =>
    this.competitions.value().filter((c) => !this.hidden().includes(c.code)),
  );

  private readonly query = computed(() => {
    const codes = this.selected().map((c) => c.code);
    return codes.length ? `&competitions=${codes.join(',')}` : null;
  });

  protected readonly upcoming = httpResource<CompetitionGroup[]>(() => {
    const q = this.query();
    return q && this.tab() !== 'risultati' ? `/api/matches?view=upcoming${q}` : undefined;
  });
  protected readonly results = httpResource<CompetitionGroup[]>(() => {
    const q = this.query();
    const limit = this.tab() === 'tutte' ? 10 : 40;
    return q && this.tab() !== 'prossime' ? `/api/matches?view=results&limit=${limit}${q}` : undefined;
  });

  constructor() {
    effect(() => {
      try {
        localStorage.setItem(STORAGE_KEY, JSON.stringify({ tab: this.tab(), hidden: this.hidden() }));
      } catch {
        // memoria del browser non disponibile: i filtri valgono solo per questa visita
      }
    });
  }

  /** Gruppi aperti con "Mostra tutte", chiave "prossime-ITA-A" / "risultati-ITA-A" */
  protected readonly openGroups = signal<string[]>([]);
  /** Partite mostrate per campionato quando il gruppo è chiuso */
  protected readonly groupLimit = computed(() => (this.tab() === 'tutte' ? 5 : 10));

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

function readSaved(): { tab?: Tab; hidden?: string[] } {
  try {
    return JSON.parse(localStorage.getItem(STORAGE_KEY) ?? '{}');
  } catch {
    return {};
  }
}
