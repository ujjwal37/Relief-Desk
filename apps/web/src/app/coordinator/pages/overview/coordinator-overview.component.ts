import { ChangeDetectionStrategy, Component, OnInit, computed, inject, signal } from '@angular/core';
import { RouterLink } from '@angular/router';
import { ApiClientService, RdTranslatePipe, StoredRequest, StoredResource, urgencyBand } from '@rd/shared';
import { MapPin, MapProviderComponent } from '../../../core/maps/map-provider.component';
import { CoordinatorAlertsComponent } from '../alerts/coordinator-alerts.component';

const DONE = new Set(['completed', 'resolved', 'closed']);
const SENT = new Set(['approved', 'dispatched', 'in_progress']);
const OPEN = new Set(['approved', 'dispatched', 'in_progress', 'completed', 'resolved', 'closed']);

type UrgencyFilter = 'all' | 'critical' | 'high' | 'medium' | 'low';
type KindFilter = 'all' | 'boat' | 'medical' | 'food' | 'shelter';
type Band = 'critical' | 'high' | 'medium' | 'low';

interface PlacedCase { id: string; lat: number; lng: number; band: Band; }
interface PlacedTeam { id: string; name: string; lat: number; lng: number; kind: string; }

/** Counts on top, then the alerts list beside one map. The schematic is only the fallback. */
@Component({
  selector: 'app-coordinator-overview',
  standalone: true,
  imports: [RouterLink, RdTranslatePipe, CoordinatorAlertsComponent, MapProviderComponent],
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
    <div class="stage">
      <app-coordinator-alerts [listOnly]="true" />
      <section class="map-stage" [attr.aria-label]="'ui.map' | rdTranslate">
        <rd-map-provider [pins]="mapPins()" [center]="mapCenter()" [fitAll]="true">
          <svg viewBox="0 0 600 480" class="schematic" role="img" [attr.aria-label]="'ui.map' | rdTranslate">
            <rect width="600" height="480" fill="var(--map-bg)"/>
            @for (p of pins(); track p.id) {
              @if (p.kind === 'team') {
                <rect [attr.x]="p.x - 9" [attr.y]="p.y - 9" width="18" height="18" rx="4" [attr.fill]="p.fill" stroke="var(--surface)" stroke-width="2"/>
              } @else {
                <circle [attr.cx]="p.x" [attr.cy]="p.y" r="9" [attr.fill]="p.fill" stroke="var(--surface)" stroke-width="2"/>
              }
            }
          </svg>
        </rd-map-provider>
        <div class="chips" role="group" [attr.aria-label]="'coord.mapFilters' | rdTranslate">
          @for (band of urgencyChips; track band) {
            <button type="button" [class.on]="urgency() === band" [attr.aria-pressed]="urgency() === band" (click)="urgency.set(urgency() === band ? 'all' : band)">
              {{ ('coord.band.' + band) | rdTranslate }}
            </button>
          }
          @for (kind of kindChips; track kind) {
            <button type="button" [class.on]="teamKind() === kind" [attr.aria-pressed]="teamKind() === kind" (click)="teamKind.set(teamKind() === kind ? 'all' : kind)">
              {{ ('coord.kind.' + kind) | rdTranslate }}
            </button>
          }
          <button type="button" [class.on]="freeOnly()" [attr.aria-pressed]="freeOnly()" (click)="freeOnly.set(!freeOnly())">{{ 'coord.mapFree' | rdTranslate }}</button>
        </div>
        <div class="legend" [attr.aria-label]="'ui.mapKey' | rdTranslate">
          @for (band of legendBands(); track band) {
            <span><i class="d" [class.crit]="band === 'critical'" [class.high]="band === 'high'" [class.med]="band === 'medium'" [class.low]="band === 'low'"></i>{{ ('coord.band.' + band) | rdTranslate }}</span>
          }
          @for (kind of legendKinds(); track kind) {
            <span><i class="sq" [style.background]="fillKind(kind)"></i>{{ ('coord.kind.' + kind) | rdTranslate }}</span>
          }
        </div>
      </section>
    </div>
  `,
  styles: [`
    :host { display: flex; flex-direction: column; height: 100%; min-height: 0; overflow: hidden; }
    .summary { flex: none; padding: 12px 16px 8px; }
    h1 { margin: 0; font-size: 22px; font-weight: 800; }
    p { margin: 4px 0 8px; color: var(--text-2); font-size: 15px; }
    .nums { display: flex; flex-wrap: wrap; gap: 8px; }
    .nums a {
      min-height: 44px; display: inline-flex; align-items: center; padding: 0 14px;
      border-radius: 999px; background: var(--surface); border: 1px solid var(--border);
      color: var(--text); text-decoration: none; font-weight: 700;
    }
    .stage {
      flex: 1; min-height: 0; display: grid;
      grid-template-columns: minmax(300px, 420px) minmax(0, 1fr);
      gap: 12px; padding: 0 12px 12px;
    }
    app-coordinator-alerts { min-height: 0; height: 100%; overflow: auto; display: block; }
    .map-stage {
      position: relative; min-height: 0; border-radius: 16px; overflow: hidden;
      border: 1px solid var(--border); background: var(--map-bg);
    }
    rd-map-provider { position: absolute; inset: 0; display: block; }
    .schematic { position: absolute; inset: 0; width: 100%; height: 100%; display: block; }
    .chips {
      position: absolute; z-index: 2; top: 10px; left: 10px; max-width: 68%;
      display: flex; flex-wrap: wrap; gap: 6px; pointer-events: auto;
    }
    .chips button {
      min-height: 32px; padding: 0 10px; border-radius: 999px;
      border: 1px solid var(--border); background: var(--surface); color: var(--text);
      font: 700 12px var(--rd-font-family); cursor: pointer;
    }
    .chips button.on { background: var(--brand); border-color: var(--brand); color: var(--on-brand); }
    .legend {
      position: absolute; z-index: 2; top: 10px; right: 10px; display: flex; flex-wrap: wrap;
      max-width: 220px; gap: 6px 10px; background: var(--surface); border: 1px solid var(--border);
      border-radius: 10px; padding: 6px 10px; font-size: 12px; font-weight: 700;
    }
    .legend span { display: inline-flex; align-items: center; gap: 4px; }
    .d { width: 10px; height: 10px; border-radius: 50%; display: inline-block; }
    .crit { background: var(--sev-crit); } .high { background: var(--sev-high); }
    .med { background: var(--sev-med); } .low { background: var(--sev-low); }
    .sq { width: 10px; height: 10px; border-radius: 3px; display: inline-block; }
    @media (max-width: 900px) {
      :host { overflow: auto; }
      .stage { grid-template-columns: 1fr; overflow: visible; }
      .map-stage { min-height: 420px; }
      app-coordinator-alerts { height: auto; max-height: none; overflow: visible; }
    }
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
  readonly urgencyChips: Exclude<UrgencyFilter, 'all'>[] = ['critical', 'high', 'medium', 'low'];
  readonly kindChips: Exclude<KindFilter, 'all'>[] = ['boat', 'medical', 'food', 'shelter'];

  private readonly placed = computed(() => {
    const urgency = this.urgency();
    const kind = this.teamKind();
    const freeOnly = this.freeOnly();
    const cases: PlacedCase[] = this.requests().filter((row) => {
      if (row.lat == null || row.lng == null || DONE.has(row.status)) return false;
      return urgency === 'all' || urgencyBand(row.urgency_score) === urgency;
    }).map((row) => ({
      id: row.id,
      lat: row.lat as number,
      lng: row.lng as number,
      band: urgencyBand(row.urgency_score),
    }));
    const teams: PlacedTeam[] = this.resources().filter((row) => {
      if (kind !== 'all' && row.kind !== kind) return false;
      if (freeOnly && !(row.status === 'available' && row.capacity_remaining > 0)) return false;
      return row.lat != null && row.lng != null;
    }).map((row) => ({ id: row.id, name: row.name, lat: row.lat, lng: row.lng, kind: row.kind }));
    return { cases, teams };
  });

  readonly mapPins = computed<MapPin[]>(() => {
    const { cases, teams } = this.placed();
    return [
      ...teams.map((row) => ({ id: row.id, lat: row.lat, lng: row.lng, title: row.name })),
      ...cases.map((row) => ({ id: row.id, lat: row.lat, lng: row.lng, title: row.id })),
    ];
  });

  readonly mapCenter = computed(() => {
    const pins = this.mapPins();
    if (!pins.length) return { lat: 9.47, lng: 76.39 };
    return {
      lat: pins.reduce((sum, pin) => sum + pin.lat, 0) / pins.length,
      lng: pins.reduce((sum, pin) => sum + pin.lng, 0) / pins.length,
    };
  });

  readonly pins = computed(() => {
    const { cases, teams } = this.placed();
    const frame = this.frame([
      ...cases.map((row) => ({ lat: row.lat, lng: row.lng })),
      ...teams.map((row) => ({ lat: row.lat, lng: row.lng })),
    ]);
    return this.spread([
      ...teams.map((row) => ({ id: row.id, kind: 'team' as const, team: row.kind, band: '' as const, fill: this.fillKind(row.kind), ...this.project(row.lat, row.lng, frame) })),
      ...cases.map((row) => ({ id: row.id, kind: 'req' as const, team: '' as const, band: row.band, fill: this.fillBand(row.band), ...this.project(row.lat, row.lng, frame) })),
    ]);
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
      minLa: minLa - Math.max(0.02, (maxLa - minLa) * 0.15),
      maxLa: maxLa + Math.max(0.02, (maxLa - minLa) * 0.15),
      minLo: minLo - Math.max(0.02, (maxLo - minLo) * 0.15),
      maxLo: maxLo + Math.max(0.02, (maxLo - minLo) * 0.15),
    };
  }
  /** Keep pins that share a ward from drawing on top of each other. */
  private spread<T extends { x: number; y: number }>(pins: T[]): T[] {
    const placed: { x: number; y: number }[] = [];
    return pins.map((pin) => {
      let x = pin.x;
      let y = pin.y;
      for (let n = 0; n < 16 && placed.some((other) => Math.hypot(other.x - x, other.y - y) < 18); n++) {
        const turn = n * 2.399;
        const radius = 18 + n * 4;
        x = Math.min(584, Math.max(16, pin.x + Math.cos(turn) * radius));
        y = Math.min(464, Math.max(16, pin.y + Math.sin(turn) * radius));
      }
      placed.push({ x, y });
      return { ...pin, x, y };
    });
  }

  private project(lat: number, lng: number, frame: { minLa: number; maxLa: number; minLo: number; maxLo: number }): { x: number; y: number } {
    return {
      x: 36 + ((lng - frame.minLo) / Math.max(1e-6, frame.maxLo - frame.minLo)) * 528,
      y: 48 + (1 - (lat - frame.minLa) / Math.max(1e-6, frame.maxLa - frame.minLa)) * 384,
    };
  }
}
