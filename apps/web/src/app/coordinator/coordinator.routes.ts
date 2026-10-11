import { Routes } from '@angular/router';
import { CoordinatorLayoutComponent } from './layouts/coordinator-layout.component';

export const COORDINATOR_ROUTES: Routes = [
  {
    path: '',
    component: CoordinatorLayoutComponent,
    children: [
      {
        path: '',
        redirectTo: 'command',
        pathMatch: 'full',
      },
      {
        path: 'login',
        loadComponent: () => import('./pages/login/coordinator-login.component').then(m => m.CoordinatorLoginComponent),
      },
      {
        path: 'command',
        loadComponent: () => import('./pages/command/coordinator-command.component').then(m => m.CoordinatorCommandComponent),
      },
    ],
  },
];
