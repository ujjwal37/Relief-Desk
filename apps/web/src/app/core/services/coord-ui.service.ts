import { Injectable, inject, signal } from '@angular/core';
import { AnomalyAlert, ApiClientService } from '@rd/shared';

/** Small shared state for the coordinator shell: header search, weights drawer, tour, alerts. */
@Injectable({ providedIn: 'root' })
export class CoordUiService {
  private api = inject(ApiClientService);

  readonly searchQuery = signal('');
  readonly weightsOpen = signal(false);
  readonly alerts = signal<AnomalyAlert[]>([]);
  readonly tourOpen = signal(false);
  readonly tourStep = signal(0);
  readonly demoWhy = typeof location !== 'undefined' && location.search.includes('demo=1');
  readonly lastRefresh = signal<number>(Date.now());

  private static readonly TOUR_KEY = 'rd_tour_done';

  loadAlerts(): void {
    const call = (this.api as Partial<ApiClientService>).getAlerts?.();
    call?.subscribe({ next: (rows) => this.alerts.set(rows), error: () => this.alerts.set([]) });
  }

  tourDone(): boolean {
    try { return localStorage.getItem(CoordUiService.TOUR_KEY) === '1'; } catch { return true; }
  }

  startTour(): void {
    this.tourStep.set(0);
    this.tourOpen.set(true);
  }

  finishTour(): void {
    this.tourOpen.set(false);
    try { localStorage.setItem(CoordUiService.TOUR_KEY, '1'); } catch { /* ignore */ }
  }
}
