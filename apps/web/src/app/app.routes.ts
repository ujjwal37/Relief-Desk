import { Routes } from '@angular/router';

export const routes: Routes = [
  {
    path: 'team/:id',
    loadComponent: () => import('./public/pages/team/team-confirm.component').then(m => m.TeamConfirmComponent),
  },
  {
    path: '',
    pathMatch: 'full',
    loadComponent: () => import('./landing/landing.component').then(m => m.LandingComponent),
  },
  {
    path: 'welcome',
    loadComponent: () => import('./landing/landing.component').then(m => m.LandingComponent),
  },
  {
    path: 'report-preview',
    loadComponent: () => import('./landing/report-preview.component').then(m => m.ReportPreviewComponent),
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
