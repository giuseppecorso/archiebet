import { Routes } from '@angular/router';
import { authGuard } from './core/auth.guard';
import { SECTIONS } from './core/sections';
import { Shell } from './layout/shell';
import { Login } from './pages/login/login';
import { Matches } from './pages/matches/matches';

type LoadComponent = NonNullable<Routes[number]['loadComponent']>;

/**
 * Sezioni già costruite; le altre mostrano la pagina provvisoria.
 * Tutte le pagine tranne login e dashboard si scaricano solo quando servono (lazy loading): l'avvio resta leggero.
 */
const BUILT: Record<string, LoadComponent> = {
  pronostici: () => import('./pages/picks/picks').then((m) => m.Picks),
  schedine: () => import('./pages/bets/bets').then((m) => m.Bets),
  statistiche: () => import('./pages/stats/stats').then((m) => m.Stats),
  impostazioni: () => import('./pages/settings/settings').then((m) => m.SettingsPage),
  simulatore: () => import('./pages/play/play').then((m) => m.Play),
};
const placeholder: LoadComponent = () => import('./pages/section-placeholder/section-placeholder').then((m) => m.SectionPlaceholder);
const labTeams: LoadComponent = () => import('./pages/lab/lab-teams').then((m) => m.LabTeams);

export const routes: Routes = [
  { path: 'login', component: Login, title: 'Accedi · ArchieBet' },
  {
    path: '',
    component: Shell,
    canActivate: [authGuard],
    children: [
      { path: '', pathMatch: 'full', loadComponent: () => import('./pages/home/home').then((m) => m.Home), title: 'Oggi · ArchieBet' },
      { path: 'partite', component: Matches, title: 'Partite · ArchieBet', data: { section: SECTIONS[0] } },
      { path: 'partite/:id', loadComponent: () => import('./pages/match/match').then((m) => m.MatchPage), title: 'Partita · ArchieBet' },
      { path: 'schedine/nuova', loadComponent: () => import('./pages/bets/new-bet').then((m) => m.NewBet), title: 'Registra una giocata · ArchieBet' },
      { path: 'schedine/:id', loadComponent: BUILT['schedine'], title: 'Le mie schedine · ArchieBet' },
      { path: 'radar', redirectTo: () => '/pronostici?tab=occasioni' },
      { path: 'gioca', redirectTo: 'simulatore' },
      { path: 'diretta', loadComponent: () => import('./pages/live/live').then((m) => m.DirettaPage), title: 'Diretta · ArchieBet' },
      { path: 'live', redirectTo: 'diretta' },
      { path: 'chiedi', loadComponent: () => import('./pages/ask/ask').then((m) => m.AskPage), title: 'Chiedi ad Archie · ArchieBet' },
      { path: 'laboratorio', pathMatch: 'full', redirectTo: 'laboratorio/campionati' },
      { path: 'laboratorio/campionati', loadComponent: () => import('./pages/lab/lab-leagues').then((m) => m.LabLeagues), title: 'Laboratorio · Campionati · ArchieBet' },
      { path: 'laboratorio/impara', loadComponent: () => import('./pages/lab/lab-learning').then((m) => m.LabLearning), title: 'Laboratorio · Cosa impara Archie · ArchieBet' },
      { path: 'laboratorio/squadre', loadComponent: labTeams, title: 'Laboratorio · Squadre · ArchieBet' },
      { path: 'laboratorio/squadre/:id', loadComponent: labTeams, title: 'Laboratorio · Squadra · ArchieBet' },
      ...SECTIONS.filter((section) => section.path !== 'laboratorio' && section.path !== 'partite').map((section) => ({
        path: section.path,
        loadComponent: BUILT[section.path] ?? placeholder,
        title: `${section.label} · ArchieBet`,
        data: { section },
      })),
    ],
  },
  { path: '**', redirectTo: '' },
];
