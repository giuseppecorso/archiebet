import { Routes } from '@angular/router';
import { authGuard } from './core/auth.guard';
import { SECTIONS } from './core/sections';
import { Shell } from './layout/shell';
import { Login } from './pages/login/login';
import { MatchPage } from './pages/match/match';
import { LabLeagues } from './pages/lab/lab-leagues';
import { LabTeams } from './pages/lab/lab-teams';
import { Bets } from './pages/bets/bets';
import { NewBet } from './pages/bets/new-bet';
import { Matches } from './pages/matches/matches';
import { SettingsPage } from './pages/settings/settings';
import { Radar } from './pages/radar/radar';
import { Stats } from './pages/stats/stats';
import { SectionPlaceholder } from './pages/section-placeholder/section-placeholder';

/** Sezioni già costruite; le altre mostrano la pagina provvisoria */
const BUILT: Record<string, Routes[number]['component']> = { partite: Matches, radar: Radar, schedine: Bets, statistiche: Stats, impostazioni: SettingsPage };

export const routes: Routes = [
  { path: 'login', component: Login, title: 'Accedi · ArchieBet' },
  {
    path: '',
    component: Shell,
    canActivate: [authGuard],
    children: [
      { path: '', pathMatch: 'full', redirectTo: 'partite' },
      { path: 'partite/:id', component: MatchPage, title: 'Partita · ArchieBet' },
      { path: 'schedine/nuova', component: NewBet, title: 'Registra una giocata · ArchieBet' },
      { path: 'schedine/:id', component: Bets, title: 'Le mie schedine · ArchieBet' },
      { path: 'laboratorio', pathMatch: 'full', redirectTo: 'laboratorio/campionati' },
      { path: 'laboratorio/campionati', component: LabLeagues, title: 'Laboratorio · Campionati · ArchieBet' },
      { path: 'laboratorio/squadre', component: LabTeams, title: 'Laboratorio · Squadre · ArchieBet' },
      { path: 'laboratorio/squadre/:id', component: LabTeams, title: 'Laboratorio · Squadra · ArchieBet' },
      ...SECTIONS.filter((section) => section.path !== 'laboratorio').map((section) => ({
        path: section.path,
        component: BUILT[section.path] ?? SectionPlaceholder,
        title: `${section.label} · ArchieBet`,
        data: { section },
      })),
    ],
  },
  { path: '**', redirectTo: '' },
];
