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
    ],
  },
];
