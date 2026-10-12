import { ChangeDetectionStrategy, Component, OnInit, computed, inject, signal } from '@angular/core';
import { RouterLink } from '@angular/router';
import { ApiClientService, RdTranslatePipe, StoredRequest, StoredResource, urgencyBand } from '@rd/shared';
import { CoordinatorAlertsComponent } from '../alerts/coordinator-alerts.component';

const DONE = new Set(['completed', 'resolved', 'closed']);
const SENT = new Set(['approved', 'dispatched', 'in_progress']);
const OPEN = new Set(['approved', 'dispatched', 'in_progress', 'completed', 'resolved', 'closed']);

type UrgencyFilter = 'all' | 'critical' | 'high' | 'medium' | 'low';
type KindFilter = 'all' | 'boat' | 'medical' | 'food' | 'shelter';

/** First tab: a short count, a filterable case map, then the alerts list and map. */
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
      <div class="filters" role="group" [attr.aria-label]="'coord.mapFilters' | rdTranslate">
        <label>{{ 'coord.mapUrgency' | rdTranslate }}
          <select [value]="urgency()" (change)="setUrgency($event)">
            <option value="all">{{ 'coord.filterAll' | rdTranslate }}</option>
            <option value="critical">{{ 'coord.band.critical' | rdTranslate }}</option>
            <option value="high">{{ 'coord.band.high' | rdTranslate }}</option>
            <option value="medium">{{ 'coord.band.medium' | rdTranslate }}</option>
            <option value="low">{{ 'coord.band.low' | rdTranslate }}</option>
          </select>
        </label>
        <label>{{ 'coord.mapTeam' | rdTranslate }}
          <select [value]="teamKind()" (change)="setKind($event)">
            <option value="all">{{ 'coord.filterAll' | rdTranslate }}</option>
            <option value="boat">{{ 'coord.kind.boat' | rdTranslate }}</option>
            <option value="medical">{{ 'coord.kind.medical' | rdTranslate }}</option>
            <option value="food">{{ 'coord.kind.food' | rdTranslate }}</option>
            <option value="shelter">{{ 'coord.kind.shelter' | rdTranslate }}</option>
          </select>
        </label>
        <label class="check"><input type="checkbox" [checked]="freeOnly()" (change)="setFree($event)" /> {{ 'coord.mapFree' | rdTranslate }}</label>
      </div>
      <div class="omap">
        <svg viewBox="0 0 600 200" role="img" [attr.aria-label]="'ui.map' | rdTranslate">
          <rect width="600" height="200" fill="var(--map-bg)"/>
          @for (p of pins(); track p.id) {
            @if (p.kind === 'team') {
              <rect [attr.x]="p.x - 7" [attr.y]="p.y - 7" width="14" height="14" rx="4" [attr.fill]="p.fill" stroke="var(--surface)" stroke-width="1.5"/>
            } @else {
              <circle [attr.cx]="p.x" [attr.cy]="p.y" r="7" [attr.fill]="p.fill" stroke="var(--surface)" stroke-width="1.5"/>
            }
          }
        </svg>
        <div class="legend" [attr.aria-label]="'ui.mapKey' | rdTranslate">
          @for (band of legendBands(); track band) {
            <span><i class="d" [class.crit]="band === 'critical'" [class.high]="band === 'high'" [class.med]="band === 'medium'" [class.low]="band === 'low'"></i>{{ ('coord.band.' + band) | rdTranslate }}</span>
          }
          @for (kind of legendKinds(); track kind) {
            <span><i class="sq" [style.background]="fillKind(kind)"></i>{{ ('coord.kind.' + kind) | rdTranslate }}</span>
          }
        </div>
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
    .filters { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; margin-bottom: 8px; }
    .filters label { display: inline-flex; align-items: center; gap: 6px; font-size: 13px; font-weight: 700; color: var(--text-2); }
    .filters select, .filters .check { min-height: 44px; }
    .filters select { border-radius: 10px; border: 1px solid var(--border); background: var(--surface); color: var(--text); font: 600 14px var(--rd-font-family); padding: 0 8px; }
    .check { padding: 0 10px; border-radius: 10px; border: 1px solid var(--border); background: var(--surface); color: var(--text); }
    .omap { position: relative; height: 200px; border-radius: 16px; overflow: hidden; border: 1px solid var(--border); margin-bottom: 8px; }
    svg { width: 100%; height: 100%; display: block; }
    .legend { position: absolute; left: 8px; bottom: 8px; display: flex; flex-wrap: wrap; gap: 6px 10px; background: var(--surface); border: 1px solid var(--border); border-radius: 10px; padding: 6px 10px; font-size: 12px; font-weight: 700; }
    .legend span { display: inline-flex; align-items: center; gap: 4px; }
    .d { width: 10px; height: 10px; border-radius: 50%; display: inline-block; } .crit { background: var(--sev-crit); } .high { background: var(--sev-high); } .med { background: var(--sev-med); } .low { background: var(--sev-low); }
    .sq { width: 10px; height: 10px; border-radius: 3px; display: inline-block; }
    app-coordinator-alerts { flex: 1; min-height: 0; }
  `],
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class CoordinatorOverviewComponent implements OnInit {
  private readonly api = inject(ApiClientService);
  readonly open = signal(0);
  readonly dispatched = signal(0);
  readonly freeTeams = signal(0);
  readonly requests = signal<StoredRequest[]>([]);
  readonly resources = signal<StoredResource[]>([]);
  readonly urgency = signal<UrgencyFilter>('all');
  readonly teamKind = signal<KindFilter>('all');
  readonly freeOnly = signal(false);

  readonly pins = computed(() => {
    const urgency = this.urgency();
    const kind = this.teamKind();
    const freeOnly = this.freeOnly();
    const cases = this.requests().filter((row) => {
      if (row.lat == null || row.lng == null || DONE.has(row.status)) return false;
      return urgency === 'all' || urgencyBand(row.urgency_score) === urgency;
    });
    const teams = this.resources().filter((row) => {
      if (kind !== 'all' && row.kind !== kind) return false;
      if (freeOnly && !(row.status === 'available' && row.capacity_remaining > 0)) return false;
      return row.lat != null && row.lng != null;
    });
    const frame = this.frame([...cases.map((row) => ({ lat: row.lat as number, lng: row.lng as number })), ...teams.map((row) => ({ lat: row.lat, lng: row.lng }))]);
    return [
      ...teams.map((row) => ({ id: row.id, kind: 'team' as const, team: row.kind, band: '' as const, fill: this.fillKind(row.kind), ...this.project(row.lat, row.lng, frame) })),
      ...cases.map((row) => {
        const band = urgencyBand(row.urgency_score);
        return { id: row.id, kind: 'req' as const, team: '' as const, band, fill: this.fillBand(band), ...this.project(row.lat as number, row.lng as number, frame) };
      }),
    ];
  });
  readonly legendBands = computed(() => {
    const present = new Set(this.pins().filter((pin) => pin.kind === 'req').map((pin) => pin.band));
    return (['critical', 'high', 'medium', 'low'] as const).filter((band) => present.has(band));
  });
  readonly legendKinds = computed(() => {
    const present = new Set(this.pins().filter((pin) => pin.kind === 'team').map((pin) => pin.team));
    return (['boat', 'medical', 'food', 'shelter'] as const).filter((kind) => present.has(kind));
  });

  ngOnInit(): void {
    this.api.getRequests().subscribe({
      next: (rows: StoredRequest[]) => {
        this.requests.set(rows);
        this.open.set(rows.filter((row) => !OPEN.has(row.status)).length);
        this.dispatched.set(rows.filter((row) => SENT.has(row.status)).length);
      },
    });
    this.api.getResources().subscribe({
      next: (rows: StoredResource[]) => {
        this.resources.set(rows);
        this.freeTeams.set(rows.filter((row) => row.status === 'available' && row.capacity_remaining > 0).length);
      },
    });
  }

  setUrgency(event: Event): void {
    this.urgency.set((event.target as HTMLSelectElement).value as UrgencyFilter);
  }
  setKind(event: Event): void {
    this.teamKind.set((event.target as HTMLSelectElement).value as KindFilter);
  }
  setFree(event: Event): void {
    this.freeOnly.set((event.target as HTMLInputElement).checked);
  }
  fillKind(kind: string): string {
    return ({ boat: 'var(--brand)', medical: 'var(--sev-crit)', food: 'var(--sev-high)', shelter: 'var(--ok)' } as Record<string, string>)[kind] || 'var(--brand)';
  }

  private fillBand(band: string): string {
    return ({ critical: 'var(--sev-crit)', high: 'var(--sev-high)', medium: 'var(--sev-med)', low: 'var(--sev-low)' } as Record<string, string>)[band] || 'var(--sev-med)';
  }
  private frame(points: { lat: number; lng: number }[]): { minLa: number; maxLa: number; minLo: number; maxLo: number } {
    if (!points.length) return { minLa: 9.2, maxLa: 11.9, minLo: 75.85, maxLo: 76.85 };
    const lats = points.map((point) => point.lat);
    const lngs = points.map((point) => point.lng);
    const minLa = Math.min(...lats);
    const maxLa = Math.max(...lats);
    const minLo = Math.min(...lngs);
    const maxLo = Math.max(...lngs);
    return {
      minLa: minLa - Math.max(0.05, (maxLa - minLa) * 0.2),
      maxLa: maxLa + Math.max(0.05, (maxLa - minLa) * 0.2),
      minLo: minLo - Math.max(0.05, (maxLo - minLo) * 0.2),
      maxLo: maxLo + Math.max(0.05, (maxLo - minLo) * 0.2),
    };
  }
  private project(lat: number, lng: number, frame: { minLa: number; maxLa: number; minLo: number; maxLo: number }): { x: number; y: number } {
    return {
      x: 24 + ((lng - frame.minLo) / Math.max(1e-6, frame.maxLo - frame.minLo)) * 552,
      y: 16 + (1 - (lat - frame.minLa) / Math.max(1e-6, frame.maxLa - frame.minLa)) * 168,
    };
  }
}
