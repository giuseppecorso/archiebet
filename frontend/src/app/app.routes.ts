import { inject } from '@angular/core';
import { Router, Routes } from '@angular/router';
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
  { path: 'login', component: Login, title: 'Accedi · Archie' },
  {
    path: '',
    component: Shell,
    canActivate: [authGuard],
    children: [
      { path: '', pathMatch: 'full', loadComponent: () => import('./pages/home/home').then((m) => m.Home), title: 'Oggi · Archie' },
      { path: 'partite', component: Matches, title: 'Partite · Archie', data: { section: SECTIONS[0] } },
      { path: 'partite/:id', loadComponent: () => import('./pages/match/match').then((m) => m.MatchPage), title: 'Partita · Archie' },
      { path: 'profilo', loadComponent: () => import('./pages/profile/profile').then((m) => m.ProfilePage), title: 'Il mio profilo · Archie' },
      { path: 'schedine/nuova', loadComponent: () => import('./pages/bets/new-bet').then((m) => m.NewBet), title: 'Registra una giocata · Archie' },
      { path: 'schedine/:id', loadComponent: BUILT['schedine'], title: 'Le mie schedine · Archie' },
      { path: 'radar', redirectTo: () => '/pronostici?tab=occasioni' },
      { path: 'gioca', redirectTo: 'simulatore' },
      { path: 'diretta', redirectTo: () => inject(Router).parseUrl('/partite?stato=live') }, // Diretta e Partite sono una sezione sola
      { path: 'live', redirectTo: () => inject(Router).parseUrl('/partite?stato=live') },
      { path: 'chiedi', redirectTo: 'partite' }, // le domande si fanno nella pagina della partita
      { path: 'lab', loadComponent: () => import('./pages/ball-home/ball-home').then((m) => m.BallHome), title: 'Bozza nuova home · Archie' }, // pagina di prova
      { path: 'laboratorio', pathMatch: 'full', redirectTo: 'laboratorio/campionati' },
      { path: 'laboratorio/campionati', loadComponent: () => import('./pages/lab/lab-leagues').then((m) => m.LabLeagues), title: 'Laboratorio · Campionati · Archie' },
      { path: 'laboratorio/impara', loadComponent: () => import('./pages/lab/lab-learning').then((m) => m.LabLearning), title: 'Laboratorio · Cosa impara Archie · Archie' },
      { path: 'laboratorio/squadre', loadComponent: labTeams, title: 'Laboratorio · Squadre · Archie' },
      { path: 'laboratorio/squadre/:id', loadComponent: labTeams, title: 'Laboratorio · Squadra · Archie' },
      ...SECTIONS.filter((section) => section.path !== 'laboratorio' && section.path !== 'partite').map((section) => ({
        path: section.path,
        loadComponent: BUILT[section.path] ?? placeholder,
        title: `${section.label} · Archie`,
        data: { section },
      })),
    ],
  },
  { path: '**', redirectTo: '' },
];
