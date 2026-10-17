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
        path: 'home',
        redirectTo: 'command',
        pathMatch: 'full',
      },
      {
        path: 'situation',
        loadComponent: () => import('./pages/situation/coordinator-situation.component').then(m => m.CoordinatorSituationComponent),
      },
      {
        path: 'overview',
        loadComponent: () => import('./pages/overview/coordinator-overview.component').then(m => m.CoordinatorOverviewComponent),
      },
      {
        path: 'command',
        loadComponent: () => import('./pages/command/coordinator-command.component').then(m => m.CoordinatorCommandComponent),
      },
      {
        path: 'agent',
        loadComponent: () => import('./pages/agent/coordinator-agent.component').then(m => m.CoordinatorAgentComponent),
      },
      {
        path: 'teams',
        loadComponent: () => import('./pages/teams/coordinator-teams.component').then(m => m.CoordinatorTeamsComponent),
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
