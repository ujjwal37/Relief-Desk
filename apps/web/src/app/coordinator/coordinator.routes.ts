import { Routes } from '@angular/router';
import { CoordinatorLayoutComponent } from './layouts/coordinator-layout.component';
import { coordinatorAuthGuard } from '../core/guards/coordinator-auth.guard';

export const COORDINATOR_ROUTES: Routes = [
  {
    path: 'login',
    loadComponent: () => import('./pages/login/coordinator-login.component').then(m => m.CoordinatorLoginComponent),
  },
  {
    path: '',
    component: CoordinatorLayoutComponent,
    canActivate: [coordinatorAuthGuard],
    children: [
      {
        path: '',
        redirectTo: 'command',
        pathMatch: 'full',
      },
      {
        path: 'command',
        loadComponent: () => import('./pages/command/coordinator-command.component').then(m => m.CoordinatorCommandComponent),
      },
      {
        path: 'teams',
        loadComponent: () => import('./pages/teams/coordinator-teams.component').then(m => m.CoordinatorTeamsComponent),
      },
      {
        path: 'live',
        loadComponent: () => import('./pages/live/live-map.component').then(m => m.LiveMapComponent),
      },
      {
        path: 'alerts',
        loadComponent: () => import('./pages/alerts/coordinator-alerts.component').then(m => m.CoordinatorAlertsComponent),
      },
      {
        path: 'benchmark',
        loadComponent: () => import('./pages/benchmark/coordinator-benchmark.component').then(m => m.CoordinatorBenchmarkComponent),
      },
    ],
  },
];
