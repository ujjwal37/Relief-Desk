import { Routes } from '@angular/router';

export const routes: Routes = [
  {
    path: '',
    pathMatch: 'full',
    loadComponent: () => import('./landing/landing.component').then(m => m.LandingComponent),
  },
  {
    path: '',
    loadChildren: () => import('./public/public.routes').then(m => m.PUBLIC_ROUTES),
  },
  {
    path: 'coordinator',
    loadChildren: () => import('./coordinator/coordinator.routes').then(m => m.COORDINATOR_ROUTES),
  },
  {
    path: '**',
    redirectTo: '',
  },
];
