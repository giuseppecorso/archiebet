import { Routes } from '@angular/router';
import { authGuard } from './core/auth.guard';
import { SECTIONS } from './core/sections';
import { Shell } from './layout/shell';
import { Login } from './pages/login/login';
import { SectionPlaceholder } from './pages/section-placeholder/section-placeholder';

export const routes: Routes = [
  { path: 'login', component: Login, title: 'Accedi · ArchieBet' },
  {
    path: '',
    component: Shell,
    canActivate: [authGuard],
    children: [
      { path: '', pathMatch: 'full', redirectTo: 'partite' },
      ...SECTIONS.map((section) => ({
        path: section.path,
        component: SectionPlaceholder,
        title: `${section.label} · ArchieBet`,
        data: { section },
      })),
    ],
  },
  { path: '**', redirectTo: '' },
];
