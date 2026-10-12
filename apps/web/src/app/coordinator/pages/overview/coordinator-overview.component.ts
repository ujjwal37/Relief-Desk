import { ChangeDetectionStrategy, Component, OnInit, inject, signal } from '@angular/core';
import { RouterLink } from '@angular/router';
import { ApiClientService, RdTranslatePipe, StoredRequest, StoredResource } from '@rd/shared';
import { CoordinatorAlertsComponent } from '../alerts/coordinator-alerts.component';

const OPEN = new Set(['approved', 'dispatched', 'in_progress', 'completed', 'resolved', 'closed']);
const SENT = new Set(['approved', 'dispatched', 'in_progress']);

/** First tab: a short count, then the existing alerts list and map. */
@Component({
  selector: 'app-coordinator-overview',
  standalone: true,
  imports: [RouterLink, RdTranslatePipe, CoordinatorAlertsComponent],
  template: `
    <section class="summary" aria-labelledby="overview-h">
      <h1 id="overview-h">{{ 'coord.overview' | rdTranslate }}</h1>
      <p>{{ 'coord.overviewLead' | rdTranslate }}</p>
      <div class="nums">
        <a routerLink="/coordinator/command">{{ open() }} {{ 'coord.cases' | rdTranslate }}</a>
        <a routerLink="/coordinator/command" [queryParams]="{ status: 'dispatched' }" queryParamsHandling="merge">{{ dispatched() }} {{ 'coord.filterDispatched' | rdTranslate }}</a>
        <a routerLink="/coordinator/teams">{{ freeTeams() }} {{ 'coord.teams' | rdTranslate }}</a>
      </div>
    </section>
    <app-coordinator-alerts />
  `,
  styles: [`
    :host { display: flex; flex-direction: column; height: 100%; min-height: 0; }
    .summary { flex: none; padding: 12px 16px 0; }
    h1 { margin: 0; font-size: 22px; font-weight: 800; }
    p { margin: 4px 0 8px; color: var(--text-2); font-size: 15px; }
    .nums { display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 8px; }
    .nums a {
      min-height: 44px; display: inline-flex; align-items: center; padding: 0 14px;
      border-radius: 999px; background: var(--surface); border: 1px solid var(--border);
      color: var(--text); text-decoration: none; font-weight: 700;
    }
    app-coordinator-alerts { flex: 1; min-height: 0; }
  `],
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class CoordinatorOverviewComponent implements OnInit {
  private readonly api = inject(ApiClientService);
  readonly open = signal(0);
  readonly dispatched = signal(0);
  readonly freeTeams = signal(0);

  ngOnInit(): void {
    this.api.getRequests().subscribe({
      next: (rows: StoredRequest[]) => {
        this.open.set(rows.filter((row) => !OPEN.has(row.status)).length);
        this.dispatched.set(rows.filter((row) => SENT.has(row.status)).length);
      },
    });
    this.api.getResources().subscribe({
      next: (rows: StoredResource[]) => {
        this.freeTeams.set(rows.filter((row) => row.status === 'available' && row.capacity_remaining > 0).length);
      },
    });
  }
}
