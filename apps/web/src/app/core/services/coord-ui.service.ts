import { Injectable, inject, signal } from '@angular/core';
import { AiHealthResponse, AnomalyAlert, ApiClientService } from '@rd/shared';

/** Small shared state for the coordinator shell: header search, weights drawer, tour, alerts, citizen panel. */
@Injectable({ providedIn: 'root' })
export class CoordUiService {
  private api = inject(ApiClientService);

  readonly searchQuery = signal('');
  /** Last case opened on Cases, so Teams can quote distance to it. */
  readonly selectedCaseId = signal('');
  readonly weightsOpen = signal(false);
  readonly alerts = signal<AnomalyAlert[]>([]);
  readonly tourOpen = signal(false);
  readonly tourStep = signal(0);
  readonly cornerPromptOpen = signal(false);
  readonly phonePanelOpen = signal(false);
  readonly yourReport = signal<{ id: string; code: string } | null>(null);

  readonly demoWhy = typeof location !== 'undefined' && location.search.includes('demo=1');
  readonly lastRefresh = signal<number>(Date.now());
  readonly aiHealth = signal<AiHealthResponse | null>(null);

  static readonly TOUR_V2_KEY = 'rd_tour_v2_off';

  loadAlerts(): void {
    const call = (this.api as Partial<ApiClientService>).getAlerts?.();
    call?.subscribe({ next: (rows) => this.alerts.set(rows), error: () => this.alerts.set([]) });
  }

  tourOff(): boolean {
    try {
      return localStorage.getItem(CoordUiService.TOUR_V2_KEY) === '1';
    } catch {
      return true;
    }
  }

  tourDone(): boolean {
    return this.tourOff();
  }

  showCornerPrompt(): void {
    if (!this.tourOff() && !this.tourOpen()) {
      this.cornerPromptOpen.set(true);
    }
  }

  dismissCornerPrompt(): void {
    this.cornerPromptOpen.set(false);
    try {
      localStorage.setItem(CoordUiService.TOUR_V2_KEY, '1');
    } catch {
      /* ignore */
    }
  }

  startTour(): void {
    this.cornerPromptOpen.set(false);
    this.tourStep.set(0);
    this.tourOpen.set(true);
  }

  finishTour(): void {
    this.tourOpen.set(false);
    try {
      localStorage.setItem(CoordUiService.TOUR_V2_KEY, '1');
    } catch {
      /* ignore */
    }
  }

  replayTour(): void {
    this.cornerPromptOpen.set(false);
    this.tourStep.set(0);
    this.tourOpen.set(true);
  }

  togglePhonePanel(): void {
    this.phonePanelOpen.update((v) => !v);
  }

  openPhonePanel(): void {
    this.phonePanelOpen.set(true);
  }

  closePhonePanel(): void {
    this.phonePanelOpen.set(false);
  }
}
