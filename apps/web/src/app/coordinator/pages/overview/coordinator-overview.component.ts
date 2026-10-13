import { ChangeDetectionStrategy, Component, OnInit, computed, effect, inject, signal } from '@angular/core';
import { Router, RouterLink } from '@angular/router';
import { ApiClientService, LanguageService, MatchProposal, RdTranslatePipe, StoredRequest, StoredResource, urgencyBand } from '@rd/shared';
import { MapLeg, MapPin, MapProviderComponent } from '../../../core/maps/map-provider.component';
import { legTitle, quoteFromProposal, teamTone } from '../../../core/maps/map-markers';
import { CoordUiService } from '../../../core/services/coord-ui.service';
import { CoordinatorAlertsComponent } from '../alerts/coordinator-alerts.component';
import { JustReportedStripComponent } from '../../just-reported-strip.component';

const DONE = new Set(['completed', 'resolved', 'closed']);
const SENT = new Set(['approved', 'dispatched', 'in_progress']);
const OPEN = new Set(['approved', 'dispatched', 'in_progress', 'completed', 'resolved', 'closed']);

type UrgencyFilter = 'all' | 'critical' | 'high' | 'medium' | 'low';
type KindFilter = 'all' | 'boat' | 'medical' | 'food' | 'shelter';
type Band = 'critical' | 'high' | 'medium' | 'low';

interface PlacedCase { id: string; lat: number; lng: number; band: Band; title: string; }
interface PlacedTeam { id: string; name: string; lat: number; lng: number; kind: StoredResource['kind']; tone: 'free' | 'busy' | 'stale'; }

/** Counts on top, then the alerts list beside one map. The schematic is only the fallback. */
@Component({
  selector: 'app-coordinator-overview',
  standalone: true,
  imports: [RouterLink, RdTranslatePipe, CoordinatorAlertsComponent, MapProviderComponent, JustReportedStripComponent],
  template: `
    <app-just-reported (picked)="openReported($event)" />
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
      <section class="map-stage" [attr.aria-label]="'ui.map' | rdTranslate">
        <rd-map-provider [pins]="mapPins()" [legs]="mapLegs()" [center]="mapCenter()" [fitAll]="mapLegs().length === 0"></rd-map-provider>
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
      <app-coordinator-alerts [listOnly]="true" />
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
      grid-template-columns: minmax(0, 1fr) 380px;
      gap: 12px; padding: 0 12px 12px;
    }
    app-coordinator-alerts { width: 380px; min-height: 0; height: 100%; overflow: hidden; display: block; }
    .map-stage {
      position: relative; min-height: 0; border-radius: 16px; overflow: hidden;
      border: 1px solid var(--border); background: var(--map-bg);
    }
    rd-map-provider { position: absolute; top: 56px; right: 0; bottom: 0; left: 0; display: block; }
    .chips {
      position: absolute; z-index: 2; top: 0; left: 0; right: 0; height: 56px;
      display: flex; align-items: center; flex-wrap: wrap; gap: 6px; padding: 0 10px;
      pointer-events: auto;
    }
    .chips button {
      min-height: 32px; padding: 0 10px; border-radius: 999px;
      border: 1px solid var(--border); background: var(--surface); color: var(--text);
      font: 700 12px var(--rd-font-family); cursor: pointer;
    }
    .chips button.on { background: var(--brand); border-color: var(--brand); color: var(--on-brand); }
    .legend {
      position: absolute; z-index: 2; bottom: 10px; left: 10px; display: flex; flex-wrap: wrap;
      max-width: 280px; gap: 6px 10px; background: var(--surface); border: 1px solid var(--border);
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
      app-coordinator-alerts { width: auto; height: auto; max-height: none; overflow: visible; }
    }
  `],
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class CoordinatorOverviewComponent implements OnInit {
  private readonly api = inject(ApiClientService);
  private readonly lang = inject(LanguageService);
  private readonly ui = inject(CoordUiService);
  private readonly router = inject(Router);
  readonly matches = signal<MatchProposal[]>([]);

  constructor() {
    effect((onCleanup) => {
      const id = this.ui.selectedCaseId();
      if (!id) {
        this.matches.set([]);
        return;
      }
      const sub = this.api.getRequestMatches(id, 5).subscribe({
        next: (rows) => this.matches.set(rows),
        error: () => this.matches.set([]),
      });
      onCleanup(() => sub.unsubscribe());
    });
  }
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
      title: row.place_text || row.id,
    }));
    const teams: PlacedTeam[] = this.resources().filter((row) => {
      if (kind !== 'all' && row.kind !== kind) return false;
      if (freeOnly && !(row.status === 'available' && row.capacity_remaining > 0)) return false;
      return row.lat != null && row.lng != null;
    }).map((row) => ({ id: row.id, name: row.name, lat: row.lat, lng: row.lng, kind: row.kind, tone: teamTone(row) }));
    return { cases, teams };
  });

  readonly mapPins = computed<MapPin[]>(() => {
    const { cases, teams } = this.placed();
    return [
      ...teams.map((row) => ({
        id: row.id,
        lat: row.lat,
        lng: row.lng,
        title: row.name,
        marker: 'team' as const,
        vehicle: row.kind,
        tone: row.tone,
      })),
      ...cases.map((row) => ({
        id: row.id,
        lat: row.lat,
        lng: row.lng,
        title: row.title,
        marker: 'case' as const,
        tone: row.band,
      })),
    ];
  });

  /** Lines to the top three teams once a case is open on the desk. */
  readonly mapLegs = computed<MapLeg[]>(() => {
    this.lang.currentLang();
    const req = this.requests().find((row) => row.id === this.ui.selectedCaseId());
    if (!req || req.lat == null || req.lng == null) return [];
    const suggested = this.matches()[0]?.resource_id;
    const legs: MapLeg[] = [];
    for (const prop of this.matches().slice(0, 3)) {
      const team = this.resources().find((row) => row.id === prop.resource_id);
      if (!team) continue;
      legs.push({
        id: team.id,
        from: { lat: req.lat, lng: req.lng },
        to: { lat: team.lat, lng: team.lng },
        title: legTitle(quoteFromProposal(prop, team.status === 'available'), (key) => this.lang.translate(key)),
        suggested: team.id === suggested,
      });
    }
    return legs;
  });

  readonly mapCenter = computed(() => {
    const pins = this.mapPins();
    if (!pins.length) return { lat: 9.47, lng: 76.39 };
    return {
      lat: pins.reduce((sum, pin) => sum + pin.lat, 0) / pins.length,
      lng: pins.reduce((sum, pin) => sum + pin.lng, 0) / pins.length,
    };
  });

  readonly legendBands = computed(() => {
    const present = new Set(this.placed().cases.map((row) => row.band));
    return (['critical', 'high', 'medium', 'low'] as const).filter((band) => present.has(band));
  });
  readonly legendKinds = computed(() => {
    const present = new Set(this.placed().teams.map((row) => row.kind));
    return (['boat', 'medical', 'food', 'shelter'] as const).filter((kind) => present.has(kind));
  });

  /** Open the case in the queue and pan the Cases map onto it. */
  openReported(caseId: string): void {
    this.ui.selectedCaseId.set(caseId);
    void this.router.navigate(['/coordinator/command'], { queryParams: { case: caseId } });
  }

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
}
