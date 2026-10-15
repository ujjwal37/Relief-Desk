import { ChangeDetectionStrategy, Component, OnInit, computed, effect, inject, signal } from '@angular/core';
import { Router } from '@angular/router';
import { ApiClientService, LanguageService, MatchProposal, RdTranslatePipe, StoredRequest, StoredResource, urgencyBand } from '@rd/shared';
import { MapLeg, MapPin, MapProviderComponent } from '../../../core/maps/map-provider.component';
import { haversineKm, legTitle, quoteFromProposal, teamTone } from '../../../core/maps/map-markers';
import { CoordUiService } from '../../../core/services/coord-ui.service';
import { DeskStore } from '../../../core/desk-store';
import { CoordinatorAlertsComponent } from '../alerts/coordinator-alerts.component';
import { JustReportedStripComponent } from '../../just-reported-strip.component';
import { teamsFreeCounts, teamsFreeLabel } from '../../team-status';

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
  imports: [RdTranslatePipe, CoordinatorAlertsComponent, MapProviderComponent, JustReportedStripComponent],
  template: `
    <app-just-reported (picked)="openReported($event)" />
    <section class="summary" aria-labelledby="overview-h">
      <h1 id="overview-h">{{ 'coord.overview' | rdTranslate }}</h1>
      <p class="lead-line">{{ overviewLine() }}</p>
    </section>
    <div class="stage">
      <section class="map-stage" [attr.aria-label]="'ui.map' | rdTranslate">
        <rd-map-provider [pins]="mapPins()" [legs]="mapLegs()" [center]="mapCenter()" [cluster]="true" [fitAll]="mapLegs().length === 0 && !focusId()" [selectedId]="focusId()" (pinSelect)="pickPin($event)"></rd-map-provider>
        @if (focusId()) {
          <button type="button" class="clear-focus" (click)="clearFocus()">{{ 'coord.mapClear' | rdTranslate }}</button>
        }
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
          <span class="grp"><span class="disc">{{ criticalCount() }}</span>{{ 'coord.legendGroup' | rdTranslate }}</span>
          @for (band of legendBands(); track band) {
            <span><i class="d" [class.crit]="band === 'critical'" [class.high]="band === 'high'" [class.med]="band === 'medium'" [class.low]="band === 'low'"></i>{{ ('coord.band.' + band) | rdTranslate }}</span>
          }
          @for (kind of legendKinds(); track kind) {
            <span><i class="sq" [style.background]="fillKind(kind)"></i>{{ ('coord.kind.' + kind) | rdTranslate }}</span>
          }
        </div>
      </section>
      <app-coordinator-alerts [listOnly]="true" (focus)="focusAlert($event)" />
    </div>
  `,
  styles: [`
    :host { display: flex; flex-direction: column; height: 100%; min-height: 0; overflow: hidden; }
    .summary { flex: none; padding: 28px 28px 16px; }
    h1 { margin: 0; font: var(--t-page, 600 24px/30px var(--rd-font-family)); letter-spacing: var(--t-page-ls, -0.02em); }
    .lead-line { margin: 6px 0 8px; color: var(--text-2); font: 400 14px/22px var(--rd-font-family); }
    p { margin: 4px 0 8px; color: var(--text-2); font-size: 14px; }
    .stage {
      flex: 1; min-height: 0; display: grid;
      grid-template-columns: minmax(0, 1fr) 380px;
      gap: 20px; padding: 0 28px 28px;
    }
    app-coordinator-alerts { width: 380px; min-height: 0; height: 100%; overflow: hidden; display: block; }
    .map-stage {
      position: relative; min-height: 0; border-radius: 16px; overflow: hidden; box-shadow:var(--e1);
      border: 1px solid var(--border); background: var(--map-bg);
    }
    rd-map-provider { position: absolute; top: 56px; right: 0; bottom: 0; left: 0; display: block; }
    .chips {
      position: absolute; z-index: 2; top: 0; left: 0; right: 0; height: 56px;
      display: flex; align-items: center; flex-wrap: wrap; gap: 6px; padding: 0 10px;
      pointer-events: auto; background:var(--surface); border-bottom:1px solid var(--border);
    }
    .chips button {
      min-height: 32px; padding: 0 10px; border-radius: 7px;
      border: 1px solid var(--border); background: var(--surface); color: var(--text);
      font: 600 12px var(--rd-font-family); cursor: pointer;
    }
    .chips button.on { background: var(--brand-tint); border-color:transparent; color: var(--brand); }
    .clear-focus {
      position: absolute; z-index: 3; top: 66px; right: 10px; min-height: 32px; padding: 0 12px;
      border-radius: 999px; border: 1px solid var(--border); background: var(--surface); color: var(--text);
      font: 600 12px var(--rd-font-family); cursor: pointer; box-shadow: var(--e1);
    }
    .legend {
      position: absolute; z-index: 2; bottom: 10px; left: 10px; display: flex; flex-wrap: wrap;
      max-width: 280px; gap: 6px 10px; background: var(--surface); border: 1px solid var(--border);
      border-radius: 10px; padding: 6px 10px; font-size: 12px; font-weight: 600;
    }
    .legend span { display: inline-flex; align-items: center; gap: 4px; }
    .d { width: 10px; height: 10px; border-radius: 50%; display: inline-block; }
    .crit { background: var(--sev-crit); } .high { background: var(--sev-high); }
    .med { background: var(--sev-med); } .low { background: var(--sev-low); }
    .sq { width: 10px; height: 10px; border-radius: 3px; display: inline-block; }
    .disc { width: 20px; height: 20px; border-radius: 50%; background: var(--sev-crit); color: #fff; display: inline-grid; place-items: center; font: 600 12px/20px var(--rd-font-family); font-style: normal; font-variant-numeric: tabular-nums; overflow: visible; }
    @media (max-width: 900px) {
      :host { overflow: auto; }
      .summary { padding:20px 16px 12px; }
      .stage { padding:0 16px 20px; gap:16px; }
      .stage { grid-template-columns: 1fr; overflow: visible; }
      .map-stage { min-height: 420px; }
      .chips { height: auto; min-height: 44px; padding: 6px 8px; }
      .legend { max-width: calc(100% - 16px); padding: 4px 8px; font-size: 12px; bottom: 8px; left: 8px; }
      .disc { width: 18px; height: 18px; font: 600 12px/18px var(--rd-font-family); }
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
  private readonly desk = inject(DeskStore);
  readonly matches = signal<MatchProposal[]>([]);

  constructor() {
    effect((onCleanup) => {
      const id = this.focusId();
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
    effect(() => {
      if (!this.desk.casesReady()) return;
      const rows = this.desk.requests();
      this.requests.set(rows);
      this.open.set(rows.filter((row) => !OPEN.has(row.status)).length);
      this.dispatched.set(rows.filter((row) => SENT.has(row.status)).length);
    });
    effect(() => {
      if (!this.desk.teamsReady()) return;
      const rows = this.desk.resources();
      this.resources.set(rows);
      this.freeTeams.set(teamsFreeCounts(rows).free);
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
  /** Case framed on this map. Set from a card, an alert, or a pin. */
  readonly focusId = signal<string | null>(null);
  readonly urgencyChips: Exclude<UrgencyFilter, 'all'>[] = ['critical', 'high', 'medium', 'low'];
  readonly kindChips: Exclude<KindFilter, 'all'>[] = ['boat', 'medical', 'food', 'shelter'];

  private readonly placed = computed(() => {
    const urgency = this.urgency();
    const kind = this.teamKind();
    const freeOnly = this.freeOnly();
    const cases: PlacedCase[] = this.requests().filter((row) => {
      if (row.lat == null || row.lng == null) return false;
      if (row.id === this.focusId()) return true;
      if (DONE.has(row.status)) return false;
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

  /** One road route to the focused case: its assigned team, else the best match, else the nearest free team. */
  readonly mapLegs = computed<MapLeg[]>(() => {
    this.lang.currentLang();
    const id = this.focusId();
    const req = id ? this.requests().find((row) => row.id === id) : null;
    if (!req || req.lat == null || req.lng == null) return [];
    const teams = this.resources().filter((row) => row.lat != null && row.lng != null);
    const assigned = teams.find((row) => row.assigned_request_id === req.id);
    const best = this.matches()[0];
    const matched = best ? teams.find((row) => row.id === best.resource_id) : undefined;
    const free = teams.filter((row) => row.status === 'available' && (row.capacity_remaining ?? 1) > 0);
    const nearest = [...(free.length ? free : teams)].sort((a, b) =>
      haversineKm(req.lat as number, req.lng as number, a.lat, a.lng) - haversineKm(req.lat as number, req.lng as number, b.lat, b.lng))[0];
    const team = assigned || matched || nearest;
    if (!team) return [];
    const quote = !assigned && matched && best
      ? quoteFromProposal(best, team.status === 'available')
      : { km: haversineKm(req.lat, req.lng, team.lat, team.lng), teamAvailable: team.status === 'available' };
    return [{
      id: team.id,
      from: { lat: req.lat, lng: req.lng },
      to: { lat: team.lat, lng: team.lng },
      title: legTitle(quote, (key) => this.lang.translate(key)),
      suggested: true,
    }];
  });

  /** A card, an alert or a pin frames that case. The same one again, or Clear, resets. */
  focusCase(caseId: string | null): void {
    const next = caseId && this.focusId() !== caseId ? caseId : null;
    this.focusId.set(next);
    this.ui.selectedCaseId.set(next ?? '');
  }

  clearFocus(): void {
    this.focusCase(null);
  }

  pickPin(id: string): void {
    if (this.requests().some((row) => row.id === id)) this.focusCase(id);
  }

  /** An alert frames the most urgent open case in its ward, or the nearest one to it. */
  focusAlert(at: { id: string; ward_id: string | null; lat: number; lng: number } | null): void {
    if (!at) { this.focusCase(null); return; }
    const open = this.requests().filter((row) => row.lat != null && row.lng != null && !DONE.has(row.status) && !row.merged_into);
    const inWard = at.ward_id ? open.filter((row) => row.ward_id === at.ward_id) : [];
    const pool = inWard.length ? inWard : open;
    const pick = [...pool].sort((a, b) => inWard.length
      ? (b.urgency_score || 0) - (a.urgency_score || 0)
      : haversineKm(at.lat, at.lng, a.lat as number, a.lng as number) - haversineKm(at.lat, at.lng, b.lat as number, b.lng as number))[0];
    this.focusId.set(null);
    this.focusCase(pick?.id ?? null);
  }

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

  /** A Just reported card frames that case on this map. Clicking it again resets. */
  openReported(caseId: string): void {
    this.focusCase(caseId);
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
        this.freeTeams.set(teamsFreeCounts(rows).free);
      },
    });
  }

  fillKind(kind: string): string {
    return ({ boat: 'var(--brand)', medical: 'var(--sev-crit)', food: 'var(--sev-high)', shelter: 'var(--ok)' } as Record<string, string>)[kind] || 'var(--brand)';
  }

  criticalCount(): number {
    return this.requests().filter((row) => !OPEN.has(row.status) && urgencyBand(row.urgency_score) === 'critical').length;
  }

  overviewLine(): string {
    this.lang.currentLang();
    const n = this.criticalCount();
    const teams = teamsFreeLabel((key) => this.lang.translate(key), this.resources());
    return this.lang.translate('coord.needHelpNow').replace('{n}', String(n)) + ' · ' + teams;
  }
}
