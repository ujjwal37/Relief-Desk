import { Injectable, inject, signal } from '@angular/core';
import { AnomalyAlert, ApiClientService, RecentReport, StoredRequest, StoredResource } from '@rd/shared';
import { CoordUiService } from './services/coord-ui.service';

/** Latest desk lists. The event stream refreshes these; each page reads what it shows. */
@Injectable({ providedIn: 'root' })
export class DeskStore {
  private readonly api = inject(ApiClientService);
  private readonly ui = inject(CoordUiService);

  readonly requests = signal<StoredRequest[]>([]);
  readonly resources = signal<StoredResource[]>([]);
  readonly alerts = signal<AnomalyAlert[]>([]);
  readonly recent = signal<RecentReport[]>([]);
  readonly casesReady = signal(false);
  readonly teamsReady = signal(false);
  readonly alertsReady = signal(false);
  /** Copy id → the case it joined. The first id on a merge event is the one that stays. */
  readonly joined = signal<Record<string, string>>({});
  private casesTicket = 0;

  noteMerge(ids: string[]): void {
    const [target, ...copies] = ids.filter(Boolean);
    if (!target || !copies.length) return;
    const next = { ...this.joined() };
    for (const copy of copies) next[copy] = target;
    this.joined.set(next);
  }

  refreshCases(): void {
    const ticket = ++this.casesTicket;
    this.api.getRequests().subscribe({
      next: (rows) => {
        if (ticket !== this.casesTicket) return;
        this.requests.set(rows.filter((row) => !row.merged_into));
        this.casesReady.set(true);
      },
    });
  }

  refreshTeams(): void {
    this.api.getResources().subscribe({
      next: (rows) => {
        this.resources.set(rows);
        this.teamsReady.set(true);
      },
    });
  }

  refreshAlerts(): void {
    this.api.getAlerts().subscribe({
      next: (rows) => {
        this.alerts.set(rows);
        this.ui.alerts.set(rows);
        this.alertsReady.set(true);
      },
    });
  }

  refreshRecent(): void {
    this.api.getRecentReports().subscribe({
      next: (rows) => this.recent.set(rows),
    });
  }

  apply(kind: 'cases' | 'teams' | 'alerts' | 'recent' | 'all'): void {
    if (kind === 'cases' || kind === 'all') this.refreshCases();
    if (kind === 'teams' || kind === 'all') this.refreshTeams();
    if (kind === 'alerts' || kind === 'all' || kind === 'cases') this.refreshAlerts();
    if (kind === 'recent' || kind === 'cases' || kind === 'all') this.refreshRecent();
  }
}
