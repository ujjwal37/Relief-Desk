import { Routes } from '@angular/router';
import { PublicLayoutComponent } from './layouts/public-layout.component';

export const PUBLIC_ROUTES: Routes = [
  {
    path: '',
    component: PublicLayoutComponent,
    children: [
      {
        path: '',
        pathMatch: 'full',
        loadComponent: () => import('./pages/home/home.component').then(m => m.HomeComponent),
      },
      {
        path: 'report',
        loadComponent: () => import('./pages/report/report.component').then(m => m.ReportComponent),
      },
      {
        path: 'status',
        loadComponent: () => import('./pages/status/status.component').then(m => m.StatusComponent),
      },
      {
        path: 'nearby',
        loadComponent: () => import('./pages/nearby/nearby.component').then(m => m.NearbyComponent),
      },
    ],
  },
];
