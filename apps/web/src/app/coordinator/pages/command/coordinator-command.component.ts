import { CommonModule } from '@angular/common';
import {
  ChangeDetectionStrategy,
  Component,
  OnDestroy,
  OnInit,
  computed,
  inject,
  signal,
} from '@angular/core';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { Subscription } from 'rxjs';
import { HostListener, effect, untracked } from '@angular/core';
import { CoordUiService } from '../../../core/services/coord-ui.service';
import { SevChipComponent } from '../../../core/components/sev-chip.component';
import { AgentBadgeComponent } from '../../agents/agent-badge.component';
import { AgentTraceDrawerComponent } from '../../agents/agent-trace-drawer.component';
import { AssistBannerComponent } from '../../agents/assist-banner.component';
import { AssistPanelComponent, AssistProposalView, AssistShortageView } from '../../agents/assist-panel.component';
import { GeminiChipComponent } from '../../agents/gemini-chip.component';
import { MergedChipComponent } from '../../agents/merged-chip.component';
import { PipelineLiveStep, PipelineStripComponent } from '../../agents/pipeline-strip.component';
import { testProviderWord } from '../../agents/provider-label';
import { JustReportedStripComponent } from '../../just-reported-strip.component';
import { LIVE_CHANNEL } from '../../../core/live-report';
import { DeskStore } from '../../../core/desk-store';
import { LiveEventsService } from '../../../core/live-events.service';
import { caseMatches } from '../../case-search';
import { ScenarioService } from '../../../core/services/scenario.service';
import { Dialog } from '@angular/cdk/dialog';
import { MapLeg, MapPin, MapProviderComponent } from '../../../core/maps/map-provider.component';
import { haversineKm, etaMinutes, etaPhrase, legTitle, quoteFromProposal, teamTone, TONE_COLOR, vehiclePath, TravelQuote } from '../../../core/maps/map-markers';
import { teamsFreeCounts, teamsFreeLabel } from '../../team-status';
import { AiStepperComponent } from '../../agents/ai-stepper.component';
import { StepDetailDialogComponent } from '../../agents/step-detail-dialog.component';
import { WhyThisTeamDialogComponent, DroppedTeamRow } from './why-this-team-dialog.component';
import {
  ApiClientService,
  RdTranslatePipe,
  LanguageService,
  bandCounts,
  needsReview,
  urgencyBand,
  MatchProposal,
  StoredRequest,
  StoredResource,
  UrgencyWeights,
} from '@rd/shared';

const PLACE_NAMES: Record<string, { en: string; hi: string }> = {
  ward_1: { en: 'Kainakary', hi: 'काइनकरी' },
  ward_2: { en: 'Champakulam', hi: 'चम्पाकुलाम' },
  ward_3: { en: 'Nedumudi', hi: 'नेदुमुडी' },
  ward_4: { en: 'Aluva', hi: 'आलुवा' },
  ward_5: { en: 'Varapuzha', hi: 'वरप्पुषा' },
  ward_6: { en: 'Kothamangalam', hi: 'कोथमंगलम' },
  ward_7: { en: 'Chalakudy', hi: 'चालाकुडी' },
  ward_8: { en: 'Mala', hi: 'माला' },
  ward_9: { en: 'Anthikad', hi: 'अंतिक्काड' },
  ward_10: { en: 'Meppadi', hi: 'मेप्पाडी' },
  ward_11: { en: 'Vythiri', hi: 'वित्तूरि' },
  ward_12: { en: 'Kalpetta', hi: 'कल्पेट्टा' },
};

const WARD_NAMES: Record<string, string[]> = Object.fromEntries(
  Object.entries(PLACE_NAMES).map(([id, n]) => [id, [n.en, n.hi]]),
);

@Component({
  selector: 'app-coordinator-command',
  standalone: true,
  imports: [
    CommonModule,
    FormsModule,
    MapProviderComponent,
    RdTranslatePipe,
    AgentBadgeComponent,
    AgentTraceDrawerComponent,
    AssistBannerComponent,
    AssistPanelComponent,
    GeminiChipComponent,
    MergedChipComponent,
    AiStepperComponent,
  ],
  templateUrl: './coordinator-command.component.html',
  styleUrl: './coordinator-command.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class CoordinatorCommandComponent implements OnInit, OnDestroy {
  private readonly apiClient = inject(ApiClientService);
  private readonly scenarioService = inject(ScenarioService);
  readonly ui = inject(CoordUiService);
  private readonly langService = inject(LanguageService);

  readonly Math = Math;

  // Reactive state signals
  readonly requests = signal<StoredRequest[]>([]);
  readonly selectedRequestId = signal<string>('INC-001');
  readonly mapFocus = signal(0);
  /** Team row under the pointer. Its line draws thicker. */
  readonly highlightId = signal<string | null>(null);
  readonly matches = signal<MatchProposal[]>([]);
  readonly resources = signal<StoredResource[]>([]);
  readonly mapPins = computed<MapPin[]>(() => {
    const pins: MapPin[] = [];
    for (const req of this.requests()) {
      if (req.lat == null || req.lng == null) {
        continue;
      }
      pins.push({
        id: req.id,
        lat: req.lat,
        lng: req.lng,
        title: req.place_text || req.id,
        marker: 'case',
        tone: urgencyBand(req.urgency_score),
      });
    }
    for (const res of this.resources()) {
      pins.push({
        id: res.id,
        lat: res.lat,
        lng: res.lng,
        title: res.name,
        marker: 'team',
        vehicle: res.kind,
        tone: teamTone(res),
      });
    }
    return pins;
  });
  /** The suggested team, then the next best, at most three. */
  readonly candidateMatches = computed<MatchProposal[]>(() => {
    const top = this.matches().slice(0, 3);
    const active = this.activeProposal();
    if (active && !top.some((row) => row.resource_id === active.resource_id)) {
      return [...top.slice(0, 2), active];
    }
    return top;
  });
  /** Next-best teams for More details — excludes the Send card pick. */
  readonly otherTeams = computed<MatchProposal[]>(() => {
    const active = this.activeProposal()?.resource_id;
    return this.matches().filter((row) => row.resource_id !== active).slice(0, 3);
  });
  readonly chooserMatches = computed<MatchProposal[]>(() => this.matches().slice(0, 5));
  readonly rejectReasons = ['coord.rjRoad', 'coord.rjElsewhere', 'coord.rjWrong'] as const;
  /** Lines from the selected case to its top three teams. Drawn on the schematic and on Google Maps. */
  readonly mapLegs = computed<MapLeg[]>(() => {
    const req = this.selectedRequest();
    if (!req || req.lat == null || req.lng == null) return [];
    const suggested = this.activeProposal()?.resource_id;
    const legs: MapLeg[] = [];
    for (const prop of this.visibleMapMatches()) {
      const team = this.resources().find((row) => row.id === prop.resource_id);
      if (!team) continue;
      legs.push({
        id: prop.resource_id,
        from: { lat: req.lat, lng: req.lng },
        to: { lat: team.lat, lng: team.lng },
        title: this.legLabel(prop),
        suggested: prop.resource_id === suggested,
        mode: team.kind === 'boat' ? 'water' : 'road',
      });
    }
    return legs;
  });
  /** A secondary line appears only while its team is inspected. */
  readonly visibleMapMatches = computed(() => {
    const selected = this.highlightId() || this.activeProposal()?.resource_id;
    return this.matches().filter((row) => row.resource_id === selected);
  });
  readonly filterType = signal<string>('all');
  readonly areaFilter = signal<string>('all');
  readonly timeFilter = signal<'all' | 'hour' | 'today'>('all');
  readonly searchQuery = this.ui.searchQuery;
  readonly bandFilter = signal<'all' | 'now' | 'soon' | 'review' | 'dispatched' | 'completed'>('all');
  private router = inject(Router);
  private route = inject(ActivatedRoute);
  private writingFilters = false;
  private filterSub: Subscription | null = null;
  readonly freshIds = signal<Set<string>>(new Set());
  readonly flashIds = signal<Set<string>>(new Set());
  private flashTimers = new Map<string, ReturnType<typeof setTimeout>>();
  private queueWatermark = '';
  private pollTimer: ReturnType<typeof setInterval> | null = null;
  readonly narrow = signal(false);
  readonly resetNote = signal<string | null>(null);

  /** Undo this session's merges and dispatches by reloading the two-case demo. */
  resetDemo(): void {
    if (!window.confirm(this.langService.translate('ux.resetDemoConfirm'))) return;
    this.apiClient.resetDemo().subscribe({
      next: () => {
        this.resetNote.set('ux.resetDemoDone');
        this.reloadAfterSeed();
      },
      error: () => this.resetNote.set('ux.resetDemoFailed'),
    });
  }

  /** Replace the two-case demo with the full flood pack. */
  loadFullScenario(): void {
    if (!window.confirm(this.langService.translate('ux.loadFullConfirm'))) return;
    this.apiClient.loadFullScenario().subscribe({
      next: () => {
        this.resetNote.set('ux.loadFullDone');
        this.reloadAfterSeed();
      },
      error: () => this.resetNote.set('ux.loadFullFailed'),
    });
  }

  private reloadAfterSeed(): void {
    this.queueWatermark = '';
    this.loadRequests();
    this.loadResources();
  }
  readonly mobilePane = signal<'cases' | 'map'>('cases');
  readonly sheetOpen = signal(false);
  private media: MediaQueryList | null = null;
  readonly openSection = signal<'why' | 'reports' | null>(null);
  readonly showOriginal = signal(false);
  readonly moreOpen = signal(false);
  readonly rejectOpen = signal(false);
  readonly approving = signal(false);
  readonly choseTeam = signal(false);
  readonly offline = signal(typeof navigator !== 'undefined' && navigator.onLine === false);
  readonly vehiclePath = vehiclePath;
  readonly traceRequestId = signal<string | null>(null);
  readonly assistOpen = signal(false);
  readonly assist = signal<{ proposals: AssistProposalView[]; shortages: AssistShortageView[] }>({ proposals: [], shortages: [] });
  readonly analysedNote = signal<Record<string, { until: number; text: string }>>({});
  readonly analysedLive = signal('');
  readonly pipelineById = signal<Record<string, PipelineLiveStep[]>>({});
  private stopPipeline?: () => void;
  private traceOpener: HTMLElement | null = null;
  private analysedTimer: ReturnType<typeof setTimeout> | null = null;
  readonly traceRequest = computed(() => {
    const id = this.traceRequestId();
    return id ? this.requests().find((row) => row.id === id) || null : null;
  });

  traceStatusKey(status: string): string {
    if (status === 'working') return 'coord.traceWorking';
    if (status === 'pending') return 'coord.tracePending';
    return 'coord.traceComplete';
  }
  readonly changeOpen = signal(false);
  readonly matchIdx = signal(0);
  readonly activeScenario = this.scenarioService.activeId;
  readonly scenarios = this.scenarioService.scenarios;
  readonly isWeightsDrawerOpen = signal<boolean>(false);
  readonly isOvercommitModalOpen = signal<boolean>(false);
  readonly isRejectModalOpen = signal<boolean>(false);
  readonly actionToast = signal<{ text: string; type: 'success' | 'warning'; undo?: boolean } | null>(null);
  readonly lastSentId = signal<string | null>(null);
  readonly selectedTranslationLang = signal<'en' | 'hi'>('en');

  private initialSelectDone = false;
  private focusRequestId: string | null = null;
  private liveChannel?: { close: () => void };
  pendingMatch: MatchProposal | null = null;
  rejectReasonText = '';

  readonly currentWeights = signal<UrgencyWeights>({
    version: 1,
    w_vulnerability: 35,
    w_people: 25,
    w_hazard: 20,
    w_wait_time: 15,
    confidence_discount_factor: 0.15,
  });

  // Computed signals
  readonly selectedRequest = computed<StoredRequest | undefined>(() => {
    const list = this.requests();
    const id = this.selectedRequestId();
    return list.find((r) => r.id === id) || list[0];
  });

  readonly activeProposal = computed<MatchProposal | undefined>(() => {
    return this.matches()[this.matchIdx()] || this.matches()[0];
  });

  readonly filteredRequests = computed<StoredRequest[]>(() => {
    let list = this.requests();
    const type = this.filterType();
    const query = this.searchQuery().toLowerCase().trim();

    if (type !== 'all') {
      list = list.filter((r) => r.type === type);
    }
    const bf = this.bandFilter();
    if (bf === 'dispatched') {
      list = list.filter((r) => this.isDispatched(r) || this.isCompleted(r))
        .sort((a, b) => Number(this.isCompleted(a)) - Number(this.isCompleted(b)));
    } else if (bf === 'completed') {
      list = list.filter((r) => this.isCompleted(r));
    } else {
      list = list.filter((r) => !this.isDispatched(r) && !this.isCompleted(r));
      if (bf === 'now') list = list.filter((r) => urgencyBand(r.urgency_score) === 'critical');
      if (bf === 'soon') list = list.filter((r) => urgencyBand(r.urgency_score) === 'high');
      if (bf === 'review') list = list.filter((r) => needsReview(r));
    }
    const area = this.areaFilter();
    if (area !== 'all') list = list.filter((r) => r.ward_id === area);
    const time = this.timeFilter();
    if (time !== 'all') {
      const start = time === 'hour' ? Date.now() - 60 * 60 * 1000 : new Date(new Date().setHours(0, 0, 0, 0)).getTime();
      list = list.filter((r) => !!r.created_at && new Date(r.created_at).getTime() >= start);
    }

    if (query) {
      list = list.filter((r) => caseMatches(r as any, query, WARD_NAMES));
    }

    return list;
  });

  readonly activeRequests = computed(() => this.requests().filter((r) => !this.isDispatched(r) && !this.isCompleted(r)));
  readonly counts = computed(() => {
    const scoped = this.requests().filter((r) => this.inScope(r));
    return {
      ...bandCounts(scoped.filter((r) => !this.isDispatched(r) && !this.isCompleted(r))),
      dispatched: scoped.filter((r) => this.isDispatched(r)).length,
      completed: scoped.filter((r) => this.isCompleted(r)).length,
    };
  });
  readonly criticalCount = computed<number>(() => this.counts().critical);
  readonly teamsFree = computed(() => teamsFreeCounts(this.resources()));
  teamsFreeLine(): string {
    this.langService.currentLang();
    return teamsFreeLabel((key) => this.langService.translate(key), this.resources());
  }
  readonly quietCount = computed(() => this.ui.alerts().filter((a) => a.kind === 'silent_zone').length);
  /** Schematic district outlines in lat/lng, south to north, around the seeded wards. */
  private readonly districtRings: { id: string; ring: [number, number][] }[] = [
    { id: 'alappuzha', ring: [[9.34, 76.30], [9.34, 76.55], [9.70, 76.52], [9.72, 76.31]] },
    { id: 'ernakulam', ring: [[9.90, 76.18], [9.95, 76.72], [10.28, 76.70], [10.22, 76.16]] },
    { id: 'thrissur', ring: [[10.15, 76.02], [10.18, 76.48], [10.62, 76.42], [10.58, 76.02]] },
    { id: 'wayanad', ring: [[11.42, 75.95], [11.46, 76.28], [11.78, 76.24], [11.74, 75.96]] },
  ];
  /** Open cases, or the selected case plus its candidate teams so the line is on screen. */
  readonly mapFrame = computed(() => {
    const req = this.selectedRequest();
    const teams = this.matches()
      .map((prop) => this.resources().find((row) => row.id === prop.resource_id))
      .filter((team): team is StoredResource => !!team && Number.isFinite(team.lat) && Number.isFinite(team.lng));
    const focused = req?.lat != null && req.lng != null && teams.length > 0;
    const points = focused
      ? [{ lat: req.lat as number, lng: req.lng as number }, ...teams.map((team) => ({ lat: team.lat, lng: team.lng }))]
      : this.requests()
          .filter((row) => row.lat != null && row.lng != null && !this.isCompleted(row))
          .map((row) => ({ lat: row.lat as number, lng: row.lng as number }));
    if (!points.length) return { minLa: 9.2, maxLa: 11.9, minLo: 75.85, maxLo: 76.85 };
    const lats = points.map((point) => point.lat);
    const lngs = points.map((point) => point.lng);
    const minLa = Math.min(...lats);
    const maxLa = Math.max(...lats);
    const minLo = Math.min(...lngs);
    const maxLo = Math.max(...lngs);
    const padLa = focused ? Math.max(0.012, (maxLa - minLa) * 0.45) : Math.max(0.08, (maxLa - minLa) * 0.18);
    const padLo = focused ? Math.max(0.012, (maxLo - minLo) * 0.45) : Math.max(0.08, (maxLo - minLo) * 0.18);
    return { minLa: minLa - padLa, maxLa: maxLa + padLa, minLo: minLo - padLo, maxLo: maxLo + padLo };
  });
  readonly mapCenter = computed(() => {
    const req = this.selectedRequest();
    if (req?.lat != null && req.lng != null) return { lat: req.lat, lng: req.lng };
    return { lat: 10.5, lng: 76.3 };
  });
  project(lat: number, lng: number): { x: number; y: number } {
    const frame = this.mapFrame();
    return {
      x: 36 + ((lng - frame.minLo) / Math.max(1e-6, frame.maxLo - frame.minLo)) * 528,
      y: 28 + (1 - (lat - frame.minLa) / Math.max(1e-6, frame.maxLa - frame.minLa)) * 424,
    };
  }
  readonly mapDistricts = computed(() =>
    this.districtRings.map((district) => {
      const pts = district.ring.map(([lat, lng]) => this.project(lat, lng));
      return {
        id: district.id,
        points: pts.map((p) => `${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(' '),
        lx: pts.reduce((sum, p) => sum + p.x, 0) / pts.length,
        ly: pts.reduce((sum, p) => sum + p.y, 0) / pts.length,
      };
    }),
  );
  readonly svgPins = computed(() => {
    const open = this.requests().filter((r) => r.lat != null && r.lng != null && !this.isCompleted(r));
    const res = this.resources();
    return [
      ...res.map((r) => {
        const at = this.project(r.lat, r.lng);
        return { id: r.id, x: at.x, y: at.y, band: 'team', kind: 'team' as const, team: r.kind, n: 0 };
      }),
      ...open.map((r, i) => {
        const at = this.project(r.lat as number, r.lng as number);
        return { id: r.id, x: at.x, y: at.y, band: urgencyBand(r.urgency_score), kind: 'req' as const, team: '', n: i + 1 };
      }),
    ];
  });
  readonly selectedPin = computed(() => this.svgPins().find((p) => p.id === this.selectedRequest()?.id));
  /** Selected case plus its candidate teams stay bright. Everything else fades. */
  readonly drawnPins = computed(() => {
    const focus = this.selectedRequest();
    const teamIds = new Set(this.candidateMatches().map((row) => row.resource_id));
    const suggested = this.activeProposal()?.resource_id;
    return this.svgPins().map((pin) => {
      const kept = !focus || pin.id === focus.id || (pin.kind === 'team' && teamIds.has(pin.id));
      const resource = pin.kind === 'team' ? this.resources().find((row) => row.id === pin.id) : undefined;
      const tone = resource ? teamTone(resource) : 'free';
      return {
        ...pin,
        dim: !kept,
        suggested: pin.kind === 'team' && pin.id === suggested && kept,
        fill: resource ? TONE_COLOR[tone] : '',
        path: vehiclePath(resource?.kind),
        fade: tone === 'stale' ? 0.4 : 1,
      };
    });
  });
  /** Zoom the district diagram onto the open case and its three teams. */
  readonly mapViewBox = computed(() => {
    const legs = this.focusLegs();
    if (!legs.length) return '0 0 600 480';
    const xs = legs.flatMap((leg) => [leg.x1, leg.x2]);
    const ys = legs.flatMap((leg) => [leg.y1, leg.y2]);
    const minX = Math.max(0, Math.min(...xs) - 80);
    const minY = Math.max(0, Math.min(...ys) - 80);
    const maxX = Math.min(600, Math.max(...xs) + 80);
    const maxY = Math.min(480, Math.max(...ys) + 80);
    return `${minX} ${minY} ${Math.max(120, maxX - minX)} ${Math.max(120, maxY - minY)}`;
  });
  readonly focusLegs = computed(() => {
    const req = this.selectedRequest();
    if (!req || req.lat == null || req.lng == null) return [];
    const origin = this.project(req.lat, req.lng);
    const suggested = this.activeProposal()?.resource_id;
    const legs: { id: string; x1: number; y1: number; x2: number; y2: number; lx: number; ly: number; label: string; suggested: boolean }[] = [];
    for (const prop of this.visibleMapMatches()) {
      const team = this.resources().find((row) => row.id === prop.resource_id);
      if (!team) continue;
      const at = this.project(team.lat, team.lng);
      legs.push({
        id: prop.resource_id,
        x1: origin.x,
        y1: origin.y,
        x2: at.x,
        y2: at.y,
        lx: (origin.x + at.x) / 2,
        ly: (origin.y + at.y) / 2 - 8,
        label: this.legLabel(prop),
        suggested: prop.resource_id === suggested,
      });
    }
    return legs;
  });
  readonly legendBands = computed(() => {
    const present = new Set(this.drawnPins().filter((pin) => pin.kind === 'req' && !pin.dim).map((pin) => pin.band));
    return (['critical', 'high', 'medium', 'low'] as const).filter((band) => present.has(band));
  });
  readonly legendKinds = computed(() => {
    const present = new Set(this.drawnPins().filter((pin) => pin.kind === 'team' && !pin.dim).map((pin) => pin.team));
    return (['boat', 'medical', 'food', 'shelter'] as const).filter((kind) => present.has(kind));
  });
  readonly movementTrail = computed(() => {
    const req = this.selectedRequest();
    const team = req ? this.assignedTeam(req) : undefined;
    const trail = team?.location_trail || [];
    if (trail.length < 2) return '';
    return trail
      .map((p) => {
        const at = this.project(p.lat, p.lng);
        return `${at.x.toFixed(1)},${at.y.toFixed(1)}`;
      })
      .join(' ');
  });

  etaMinutes(km: number): number {
    return etaMinutes(km);
  }
  private travel(prop: MatchProposal): TravelQuote {
    const team = this.resources().find((row) => row.id === prop.resource_id);
    return quoteFromProposal(prop, team?.status === 'available');
  }
  /** Same string as the map line and the reporter quote. */
  legLabel(prop: MatchProposal): string {
    this.langService.currentLang();
    return legTitle(this.travel(prop), (key) => this.langService.translate(key));
  }
  aiKind(req: StoredRequest): 'gemini' | 'recorded' | 'fallback' | 'test' {
    if (this.testWord(req)) return 'test';
    if (req.ai?.provider === 'cache' || req.ai?.cached || req.ai_source === 'recorded') return 'recorded';
    if (req.ai?.provider === 'gemini' || req.ai_source === 'gemini') return 'gemini';
    if (this.ui.aiHealth()?.provider === 'gemini' || this.ui.aiHealth()?.label?.includes('Gemini')) return 'gemini';
    return 'fallback';
  }
  /** Who read this report, e.g. "Test model (NVIDIA)". Never Gemini for a test provider. */
  aiSourceText(req: StoredRequest): string {
    this.langService.currentLang();
    const kind = this.aiKind(req);
    if (kind === 'test') return this.testWord(req) || '';
    return this.langService.translate(kind === 'gemini' ? 'coord.aiGemini' : kind === 'recorded' ? 'coord.aiRecorded' : 'coord.aiOffline');
  }
  private testWord(req: StoredRequest): string | null {
    const intake = (req.trace || []).find((row) => row.agent === 'Intake');
    return testProviderWord(req.ai?.provider || req.ai_source, intake?.vendor, (key) => this.langService.translate(key));
  }
  etaText(prop: MatchProposal): string {
    this.langService.currentLang();
    return etaPhrase(this.travel(prop), (key) => this.langService.translate(key));
  }
  assignedTeam(req: StoredRequest): StoredResource | undefined {
    return this.resources().find((team) => team.id === req.assigned_resource_id);
  }
  teamFill(kind: string): string {
    return ({ boat: 'var(--brand)', medical: 'var(--sev-crit)', food: 'var(--sev-high)', shelter: 'var(--ok)' } as Record<string, string>)[kind] || 'var(--brand)';
  }
  bandOf(score: number): 'critical' | 'high' | 'medium' | 'low' { return urgencyBand(score); }
  isReview(r: StoredRequest): boolean { return needsReview(r); }
  isDispatched(r: StoredRequest): boolean {
    return r.status === 'approved' || r.status === 'dispatched' || r.status === 'in_progress';
  }
  isCompleted(r: StoredRequest): boolean {
    return r.status === 'completed' || r.status === 'resolved' || r.status === 'closed';
  }
  dispatchStep(r: StoredRequest): number {
    const status = String(r.status);
    if (status === 'in_progress' || status === 'on_scene') return 3;
    if (status === 'accepted' || status === 'en_route') return 2;
    if (this.isDispatched(r)) return 1;
    return 0;
  }
  fitPct(p: MatchProposal): number { return Math.round(p.score); }
  queueNeed(r: StoredRequest): string {
    this.langService.currentLang();
    const key = ({ rescue: 'coord.queueNeedBoat', animal_attack: 'coord.queueNeedBoat', medical: 'coord.queueNeedMedical',
      food: 'coord.queueNeedFood', shelter: 'coord.queueNeedShelter' } as Record<string, string>)[r.type || ''];
    return key ? this.langService.translate(key) : '';
  }
  queueNeedLine(r: StoredRequest): string {
    this.langService.currentLang();
    const flags = r.vulnerable || { child: false, elderly: false, disabled: false, pregnant: false, medical_need: false };
    const on = (['child', 'elderly', 'disabled', 'pregnant', 'medical_need'] as const).filter((k) => !!flags[k]);
    const n = r.people_count || 0;
    const parts: string[] = [];
    if (on.length === 1 && on[0] === 'child' && n) parts.push(this.langService.translate('coord.nChildren').replace('{n}', String(n)));
    else if (on.length === 1 && on[0] === 'elderly' && n) parts.push(this.langService.translate('coord.nElderly').replace('{n}', String(n)));
    else {
      if (flags.child) parts.push(this.langService.translate('coord.metaChildren'));
      if (flags.elderly) parts.push(this.langService.translate('coord.metaElderly'));
      if (flags.disabled) parts.push(this.langService.translate('coord.metaDisabled'));
      if (flags.pregnant) parts.push(this.langService.translate('coord.metaPregnant'));
      if (flags.medical_need) parts.push(this.langService.translate('coord.metaMedical'));
    }
    const need = this.queueNeed(r);
    if (need) parts.push(need);
    return parts.join(' · ');
  }
  locationLine(r: StoredRequest): string {
    const ward = r.ward_id
      ? r.ward_id.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase())
      : '';
    return [ward, r.place_text].filter(Boolean).join(' · ');
  }
  dupTitle(r: StoredRequest): string {
    this.langService.currentLang();
    return this.dupAiLine(r);
  }
  dupAiLine(r: StoredRequest): string {
    this.langService.currentLang();
    const hint = r.possible_duplicate;
    const pct = hint?.similarity != null ? Math.round(hint.similarity * 100) : 0;
    return this.langService.translate('xfactor.dupMatch')
      .replace('{id}', hint?.target_id || '')
      .replace('{pct}', String(pct));
  }
  showGeminiChip(req: StoredRequest): boolean {
    const kind = this.aiKind(req);
    return kind === 'gemini' || kind === 'recorded';
  }
  fieldConf(req: StoredRequest, key: 'type' | 'place' | 'people' | 'vulnerable' | 'urgency'): number | null {
    const value = req.confidence?.[key];
    return typeof value === 'number' ? value : null;
  }
  pipelineSteps(req: StoredRequest): PipelineLiveStep[] {
    return this.pipelineById()[req.id] || [];
  }
  sendSample(kind: 'hindi' | 'voice' | 'photo' | 'duplicate'): void {
    this.apiClient.submitSampleReport(kind).subscribe({
      next: (res) => {
        this.focusRequestId = res.request_id;
        this.loadRequests();
        this.selectRequest(res.request_id, true);
      },
      error: () => this.actionToast.set({ text: this.langService.translate('xfactor.sampleFailed'), type: 'warning' }),
    });
  }
  needsDupReview(r: StoredRequest): boolean {
    const decision = String((r as StoredRequest & { dedupe_decision?: string }).dedupe_decision || '').toLowerCase();
    if (decision === 'review') return true;
    if (decision && decision !== 'review') return false;
    return !!r.possible_duplicate?.target_id;
  }
  checkThisLine(r: StoredRequest): string {
    this.langService.currentLang();
    return this.langService.translate('coord.checkThis').replace('{n}', String(this.getTranslationConfidencePercent(r)));
  }
  dupEvidence(r: StoredRequest): string {
    const hint = r.possible_duplicate;
    if (!hint) return '';
    this.langService.currentLang();
    const parts: string[] = [];
    if (hint.similarity != null && hint.similarity > 0) parts.push(`${Math.round(hint.similarity * 100)}%`);
    if (hint.distance_km != null && hint.distance_km > 0) parts.push(`${Number(hint.distance_km).toFixed(1)} km`);
    if (hint.minutes != null && hint.minutes > 0) parts.push(`${Math.round(hint.minutes)} min`);
    return parts.join(' · ');
  }
  factLine(r: StoredRequest): string {
    this.langService.currentLang();
    const people = `${r.people_count || 1} ${this.langService.translate('coord.people')}`;
    const ward = r.ward_id ? r.ward_id.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase()) : '';
    const extra = r.hazard ? r.hazard.replace(/_/g, ' ') : (r.place_text || '');
    return [people, ward, extra].filter(Boolean).join(' · ');
  }
  hasVulnerable(r: StoredRequest): boolean {
    const flags = r.vulnerable;
    return !!(flags && (flags.child || flags.elderly || flags.disabled || flags.pregnant || flags.medical_need));
  }
  sendTeamLabel(_name?: string): string {
    this.langService.currentLang();
    return this.langService.translate('coord.send');
  }
  whyLine(prop: MatchProposal): string {
    this.langService.currentLang();
    if (this.choseTeam()) return this.langService.translate('coord.whyChose');
    const b = prop.breakdown;
    const ranked = [
      { n: b?.distance_score || 0, t: this.langService.translate('coord.whyClosest') },
      { n: b?.capacity_fit_score || 0, t: this.langService.translate('coord.whySeats') },
      { n: b?.urgency_score || 0, t: this.langService.translate('coord.whyUrgent') },
      { n: b?.vulnerability_fit_score || 0, t: this.langService.translate('coord.whyVuln') },
    ].sort((a, b2) => b2.n - a.n).slice(0, 2).map((row) => row.t);
    const second = ranked[1] ? ranked[1].charAt(0).toLocaleLowerCase() + ranked[1].slice(1) : '';
    const built = ranked.length >= 2
      ? this.langService.translate('coord.whyJoin').replace('{a}', ranked[0]).replace('{b}', second)
      : (ranked[0] || '');
    if (built.length > 90) return built.slice(0, 89).trim();
    return built || this.langService.translate('coord.whyFallback');
  }
  waitTime(r: StoredRequest): string {
    this.langService.currentLang();
    let mins = r.wait_minutes ?? 0;
    if (!mins && r.created_at) {
      const t = new Date(r.created_at).getTime();
      if (!Number.isNaN(t)) mins = Math.max(0, Math.round((Date.now() - t) / 60000));
    }
    const time = mins >= 60 ? `${Math.round(mins / 60)} h` : `${mins} min`;
    return this.langService.translate('coord.waitingTime').replace('{time}', time);
  }
  waitChip(r: StoredRequest): string {
    const pts = Math.round(r.wait_points || 0);
    if (pts < 1) return '';
    const mins = r.wait_minutes ?? 0;
    const time = mins >= 60 ? `${Math.round(mins / 60)} h` : `${mins} min`;
    return this.langService.translate('coord.waitChip').replace('{time}', time).replace('{n}', String(pts));
  }
  ageLabel(r: StoredRequest): string {
    this.langService.currentLang();
    if (!r.created_at) return '';
    const m = Math.max(0, Math.round((Date.now() - new Date(r.created_at).getTime()) / 60000));
    if (m < 1) return this.langService.translate('coord.justNow');
    if (m < 60) return this.langService.translate('coord.minAgo').replace('{n}', String(m));
    return this.langService.translate('coord.reportedHour').replace('{n}', String(Math.round(m / 60)));
  }
  updatedLabel(r: StoredRequest): string { return this.agoPhrase(r.updated_at, 'updated'); }
  fullStamp(iso?: string | null): string {
    if (!iso) return '';
    const d = new Date(iso);
    return Number.isNaN(d.getTime()) ? '' : d.toLocaleString();
  }
  private agoPhrase(iso: string | undefined, kind: 'reported' | 'updated'): string {
    if (!iso) return '';
    const m = Math.max(0, Math.round((Date.now() - new Date(iso).getTime()) / 60000));
    const hour = m >= 60;
    const key = kind === 'reported'
      ? (hour ? 'coord.reportedHour' : 'coord.reportedMin')
      : (hour ? 'coord.caseUpdatedHour' : 'coord.caseUpdatedMin');
    return this.langService.translate(key).replace('{n}', String(hour ? Math.round(m / 60) : m));
  }
  readonly areas = computed(() => [...new Set(this.requests().map((r) => r.ward_id).filter((w): w is string => !!w))].sort());
  placeName(wardId: string): string {
    const names = PLACE_NAMES[wardId];
    if (!names) return wardId.replaceAll('_', ' ');
    return this.langService.currentLang() === 'hi' ? names.hi : names.en;
  }
  private inScope(r: StoredRequest): boolean {
    const type = this.filterType();
    if (type !== 'all' && r.type !== type) return false;
    const area = this.areaFilter();
    if (area !== 'all' && r.ward_id !== area) return false;
    const time = this.timeFilter();
    if (time === 'all') return true;
    if (!r.created_at) return false;
    const start = time === 'hour' ? Date.now() - 60 * 60 * 1000 : new Date(new Date().setHours(0, 0, 0, 0)).getTime();
    return new Date(r.created_at).getTime() >= start;
  }
  tr(key: string, n: number): string { this.langService.currentLang(); return this.langService.translate(key).replace('{n}', String(n)); }
  waitLabel(prop: MatchProposal): string {
    this.langService.currentLang();
    const minutes = prop.wait_minutes || 0;
    if (minutes > 90) return this.langService.translate('coord.noNearbyTeam');
    return this.langService.translate('coord.estimatedWait')
      .replace('{n}', String(minutes))
      .replace('{team}', prop.wait_team_name || '');
  }
  toggleSection(s: 'why' | 'reports'): void { this.openSection.set(this.openSection() === s ? null : s); }
  setBandFilter(f: 'all' | 'now' | 'soon' | 'review' | 'dispatched' | 'completed'): void { this.bandFilter.set(f); this.writeFilters(); }
  pickMatch(i: number): void { this.matchIdx.set(i); this.changeOpen.set(false); this.choseTeam.set(true); }
  closeWeights(): void { this.ui.weightsOpen.set(false); }

  @HostListener('window:offline')
  onOffline(): void { this.offline.set(true); }
  @HostListener('window:online')
  onOnline(): void { this.offline.set(false); }

  @HostListener('document:keydown', ['$event'])
  onKey(e: KeyboardEvent): void {
    const t = e.target as HTMLElement;
    if (/INPUT|TEXTAREA|SELECT/.test(t?.tagName) || e.ctrlKey || e.metaKey) return;
    if (this.traceRequestId() || this.assistOpen()) return;
    const list = this.filteredRequests();
    const i = list.findIndex((r) => r.id === this.selectedRequestId());
    if (e.key === 'j' && i < list.length - 1) this.selectRequest(list[i + 1].id);
    if (e.key === 'k' && i > 0) this.selectRequest(list[i - 1].id);
    if (e.key === 'a') (document.querySelector('.btn-approve') as HTMLElement | null)?.focus();
  }

  private readonly desk = inject(DeskStore);
  private readonly live = inject(LiveEventsService);
  private readonly dialog = inject(Dialog);

  readonly availableBoatsCount = computed<number>(() => {
    const boats = this.resources().filter((res) => res.kind === 'boat');
    return boats.filter((b) => b.capacity_remaining > 0).length;
  });

  constructor() {
    effect((onCleanup) => {
      if (this.actionToast()) {
        const id = setTimeout(() => this.actionToast.set(null), 8000);
        onCleanup(() => clearTimeout(id));
      }
    });
    effect(() => {
      const ui = this.langService.currentLang();
      const mapped = ui === 'en' || ui === 'ml' ? 'en' : 'hi';
      this.selectedTranslationLang.set(mapped);
    });
    effect(() => {
      if (!this.desk.casesReady()) return;
      const incoming = this.desk.requests();
      untracked(() => this.applyQueue(incoming, false));
    });
    effect(() => {
      if (!this.desk.teamsReady()) return;
      this.resources.set(this.desk.resources());
    });
  }

  ngOnInit(): void {
    this.ui.loadAlerts();
    this.scenarioService.ensureLoaded();
    this.loadRequests();
    this.loadResources();
    this.loadWeights();
    this.loadAssist();
    this.startQueuePoll();
    this.readFilters();
    this.watchViewport();
    this.stopPipeline = this.live.onEvent((event) => {
      if (event.type === 'case.created' || event.type === 'case.updated' || event.type === 'case.merged') {
        this.loadRequests(true);
      }
      if (event.type === 'dispatch.created' || event.type === 'team.updated') {
        this.loadResources();
      }
      if (event.type === 'alert.created') {
        this.ui.loadAlerts();
      }
      if (event.type !== 'pipeline.step' || !event.request_id || !event.agent) return;
      const row: PipelineLiveStep = {
        agent: event.agent,
        status: event.status || 'working',
        summary: event.summary,
        similarity: event.similarity,
        match_id: event.match_id,
        tier: event.tier,
        score: event.score,
        team: event.team,
      };
      const next = { ...this.pipelineById() };
      const list = [...(next[event.request_id] || []).filter((step) => step.agent !== row.agent), row];
      next[event.request_id] = list;
      this.pipelineById.set(next);
    });
    window.addEventListener('message', this.handleDemoMessage);
    document.addEventListener('visibilitychange', this.onQueueVisibility);
    try {
      const channel = new BroadcastChannel(LIVE_CHANNEL);
      channel.onmessage = (event) => this.onLiveReport(event.data);
      this.liveChannel = channel;
    } catch {
      // BroadcastChannel is missing in this browser. The poll still picks the report up.
    }
  }

  ngOnDestroy(): void {
    this.filterSub?.unsubscribe();
    this.stopQueuePoll();
    this.media?.removeEventListener('change', this.onMedia);
    window.removeEventListener('message', this.handleDemoMessage);
    document.removeEventListener('visibilitychange', this.onQueueVisibility);
    this.liveChannel?.close();
    this.stopPipeline?.();
    if (this.analysedTimer) clearTimeout(this.analysedTimer);
    for (const timer of this.flashTimers.values()) clearTimeout(timer);
    this.flashTimers.clear();
  }

  private watchViewport(): void {
    if (typeof window === 'undefined' || !window.matchMedia) return;
    this.media = window.matchMedia('(max-width: 900px)');
    this.narrow.set(this.media.matches);
    this.media.addEventListener('change', this.onMedia);
  }

  private onMedia = (event: MediaQueryListEvent): void => {
    this.narrow.set(event.matches);
    if (!event.matches) this.sheetOpen.set(false);
  };

  setPane(pane: 'cases' | 'map'): void {
    this.mobilePane.set(pane);
  }

  closeSheet(): void {
    this.sheetOpen.set(false);
  }

  private onQueueVisibility = (): void => {
    if (document.hidden) {
      this.stopQueuePoll();
      return;
    }
    this.loadRequests(true);
    this.startQueuePoll();
  };

  private startQueuePoll(): void {
    this.stopQueuePoll();
    this.pollTimer = setInterval(() => {
      if (typeof document !== 'undefined' && document.hidden) return;
      this.loadRequests(true);
      this.loadResources();
      this.loadAssist();
    }, 5000);
  }

  private stopQueuePoll(): void {
    if (this.pollTimer) {
      clearInterval(this.pollTimer);
      this.pollTimer = null;
    }
  }

  handleDemoMessage = (event: MessageEvent): void => {
    if (event.origin !== window.location.origin) {
      return;
    }
    this.onLiveReport(event.data);
  };

  /** A phone in this window, a popup, or another tab just saved a report. Show that case. */
  onLiveReport(data: { type?: string; requestId?: string } | null): void {
    if (data?.type !== 'rd-report-submitted') return;
    if (data.requestId) this.focusRequestId = data.requestId;
    this.loadRequests();
  }

  loadRequests(incremental = false): void {
    const since = incremental ? this.queueWatermark : undefined;
    this.apiClient.getRequests('urgency', this.activeScenario(), since || undefined).subscribe({
      next: (reqs) => this.applyQueue(reqs, incremental),
      error: (err) => console.error('Failed to load requests:', err),
    });
  }

  /** Merge a poll into the open queue. Keeps the selected case and flags brand-new rows. */
  applyQueue(incoming: StoredRequest[], incremental: boolean): void {
    const previousStatus = new Map(this.requests().map((row) => [row.id, row.analysis_status]));
    const previous = new Set(this.requests().map((row) => row.id));
    let next = incoming;
    const fresh = new Set(this.freshIds());
    if (incremental && previous.size) {
      const byId = new Map(this.requests().map((row) => [row.id, row]));
      for (const row of incoming) {
        if (!byId.has(row.id)) fresh.add(row.id);
        byId.set(row.id, row);
      }
      next = [...byId.values()].sort((a, b) => (b.urgency_score || 0) - (a.urgency_score || 0));
    }
    for (const row of next) {
      if (row.updated_at && row.updated_at > this.queueWatermark) this.queueWatermark = row.updated_at;
    }
    this.noteFinished(previousStatus, next);
    const joined = { ...this.desk.joined() };
    for (const row of incoming) {
      if (row.merged_into) joined[row.id] = row.merged_into;
    }
    next = next.filter((row) => !row.merged_into && !joined[row.id]);
    const keep = this.selectedRequestId();
    const moved = keep ? joined[keep] : undefined;
    this.requests.set(next);
    if (previous.size) {
      for (const row of next) {
        if (!previous.has(row.id)) this.flashRow(row.id);
      }
    }
    this.freshIds.set(fresh);
    this.ui.lastRefresh.set(Date.now());
    const focus = this.focusRequestId;
    if (focus && next.some((row) => row.id === focus)) {
      this.focusRequestId = null;
      this.initialSelectDone = true;
      this.selectRequest(focus);
      const reveal = (): void => document.querySelector(`[data-case-id="${focus}"]`)?.scrollIntoView({ block: 'nearest' });
      if (typeof queueMicrotask === 'function') queueMicrotask(reveal);
      return;
    }
    if (!this.initialSelectDone && next.length > 0) {
      this.initialSelectDone = true;
      const pick = next.find((row) => !this.isDispatched(row) && !this.isCompleted(row)) || next[0];
      this.selectedRequestId.set(pick.id);
      this.ui.selectedCaseId.set(pick.id);
      this.loadMatches(pick.id);
      return;
    }
    if (moved && next.some((row) => row.id === moved)) {
      this.selectRequest(moved);
      return;
    }
    if (keep && next.some((row) => row.id === keep)) {
      if (!incremental) this.loadMatches(keep);
      return;
    }
    if (next.length > 0 && !keep) this.selectRequest(next[0].id);
  }

  loadMatches(requestId: string): void {
    this.apiClient.getRequestMatches(requestId, 5).subscribe({
      next: (proposals) => {
        if (this.selectedRequestId() !== requestId) return;
        this.matches.set(proposals);
      },
      error: (err) => {
        console.warn('Could not load matches for request:', requestId, err);
        this.matches.set([]);
      },
    });
  }

  loadResources(): void {
    this.apiClient.getResources().subscribe({
      next: (resList) => {
        this.resources.set(resList);
        this.desk.refreshTeams();
      },
      error: (err) => console.error('Failed to load resources:', err),
    });
  }

  loadWeights(): void {
    this.apiClient.getUrgencyWeights().subscribe({
      next: (w) => this.currentWeights.set(w),
      error: (err) => console.warn('Using default weights:', err),
    });
  }

  loadAssist(): void {
    this.apiClient.getAssistProposals().subscribe({
      next: (body) => {
        const incoming = (body?.proposals || []) as AssistProposalView[];
        const current = this.assist();
        const phases = new Map(current.proposals.map((row) => [row.match_id, row.phase]));
        const kept = current.proposals.filter(
          (row) => row.phase === 'approved' && !incoming.some((item) => item.match_id === row.match_id),
        );
        this.assist.set({
          proposals: [
            ...incoming.map((row) => ({ ...row, phase: phases.get(row.match_id) || 'open' })),
            ...kept,
          ],
          shortages: body?.shortages?.length ? body.shortages : current.shortages,
        });
      },
      error: () => undefined,
    });
  }

  refreshAssist(): void {
    this.apiClient.planAssist().subscribe({
      next: (body) => {
        this.assist.set({
          proposals: (body?.proposals || []) as AssistProposalView[],
          shortages: (body?.shortages || []) as AssistShortageView[],
        });
      },
      error: () => this.actionToast.set({ text: this.langService.translate('ux.retry'), type: 'warning' }),
    });
  }

  approveAssist(row: AssistProposalView): void {
    this.apiClient.approveMatch(row.match_id, false).subscribe({
      next: () => {
        this.assist.update((state) => ({
          ...state,
          proposals: state.proposals.map((item) => item.match_id === row.match_id ? { ...item, phase: 'approved' } : item),
        }));
        this.loadRequests();
        setTimeout(() => {
          this.assist.update((state) => ({
            ...state,
            proposals: state.proposals.filter((item) => item.match_id !== row.match_id),
          }));
        }, 5000);
      },
      error: () => {
        this.assist.update((state) => ({
          ...state,
          proposals: state.proposals.map((item) => item.match_id === row.match_id ? { ...item, phase: 'failed' } : item),
        }));
      },
    });
  }

  rejectAssist(row: AssistProposalView): void {
    this.apiClient.rejectMatch(row.match_id, this.langService.translate('ux.released')).subscribe({
      next: () => {
        this.assist.update((state) => ({
          ...state,
          proposals: state.proposals.filter((item) => item.match_id !== row.match_id),
        }));
        this.actionToast.set({ text: this.langService.translate('ux.released'), type: 'success' });
        this.loadRequests();
      },
      error: () => {
        this.assist.update((state) => ({
          ...state,
          proposals: state.proposals.map((item) => item.match_id === row.match_id ? { ...item, phase: 'failed' } : item),
        }));
      },
    });
  }

  approveAllAssist(): void {
    for (const row of this.assist().proposals) {
      if (!row.expired && row.phase !== 'approved') this.approveAssist(row);
    }
  }

  openTrace(req: StoredRequest, event: Event): void {
    event.stopPropagation();
    this.traceOpener = event.currentTarget as HTMLElement;
    this.traceRequestId.set(req.id);
  }

  closeTrace(): void {
    this.traceRequestId.set(null);
    const opener = this.traceOpener;
    this.traceOpener = null;
    queueMicrotask(() => opener?.focus());
  }

  retryTrace(): void {
    this.loadRequests();
  }

  retryAnalysis(): void {
    this.loadRequests();
  }

  analysedLabel(id: string): string {
    const row = this.analysedNote()[id];
    return row && row.until > Date.now() ? row.text : '';
  }

  isAnalysing(req: StoredRequest): boolean {
    return req.analysis_status === 'analysing';
  }

  isAnalysisFailed(req: StoredRequest): boolean {
    const status = req.analysis_status as string | undefined;
    return status === 'failed' || status === 'error';
  }

  private noteFinished(previous: Map<string, StoredRequest['analysis_status']>, next: StoredRequest[]): void {
    const notes = { ...this.analysedNote() };
    let live = '';
    const now = Date.now();
    for (const row of next) {
      if (previous.get(row.id) === 'analysing' && row.analysis_status === 'complete') {
        const text = this.analysedText(row);
        notes[row.id] = { until: now + 10000, text };
        live = text;
      }
    }
    for (const id of Object.keys(notes)) {
      if (notes[id].until <= now) delete notes[id];
    }
    this.analysedNote.set(notes);
    if (live) this.analysedLive.set(live);
    this.armAnalysed();
  }

  private analysedText(req: StoredRequest): string {
    this.langService.currentLang();
    const steps = req.trace || [];
    const count = steps.filter((step) => step.status === 'complete').length || steps.length;
    const seconds = this.parallelSeconds(req);
    if (seconds == null) {
      return this.langService.translate('ux.analysedNoTime').replace('{n}', String(count));
    }
    const time = this.langService.translate('ux.seconds').replace('{n}', seconds);
    return this.langService.translate('ux.analysed').replace('{n}', String(count)).replace('{time}', time);
  }

  private parallelSeconds(req: StoredRequest): string | null {
    const steps = req.trace || [];
    if (!steps.length || steps.some((step) => typeof step.latency_ms !== 'number')) return null;
    const of = (agent: string) => steps.find((step) => step.agent === agent)?.latency_ms || 0;
    const ms = of('Intake') + Math.max(of('Dedupe'), of('Triage')) + of('Matching') + of('Explainer');
    return (ms / 1000).toFixed(1);
  }

  private armAnalysed(): void {
    if (this.analysedTimer) clearTimeout(this.analysedTimer);
    const times = Object.values(this.analysedNote()).map((row) => row.until);
    if (!times.length) return;
    const wait = Math.max(0, Math.min(...times) - Date.now());
    this.analysedTimer = setTimeout(() => {
      const now = Date.now();
      const left: Record<string, { until: number; text: string }> = {};
      for (const [id, row] of Object.entries(this.analysedNote())) {
        if (row.until > now) left[id] = row;
      }
      this.analysedNote.set(left);
      if (!Object.keys(left).length) this.analysedLive.set('');
      this.armAnalysed();
    }, wait + 30);
  }

  /** A Just reported chip: show that case in the queue and pan the map to it. */
  openReported(caseId: string): void {
    if (!this.filteredRequests().some((row) => row.id === caseId)) this.bandFilter.set('all');
    this.selectRequest(caseId, true);
    const reveal = (): void => document.querySelector(`[data-case-id="${caseId}"]`)?.scrollIntoView({ block: 'nearest' });
    if (typeof queueMicrotask === 'function') queueMicrotask(reveal);
  }

  private flashRow(id: string): void {
    const next = new Set(this.flashIds());
    next.add(id);
    this.flashIds.set(next);
    const prev = this.flashTimers.get(id);
    if (prev) clearTimeout(prev);
    this.flashTimers.set(id, setTimeout(() => {
      const left = new Set(this.flashIds());
      left.delete(id);
      this.flashIds.set(left);
      this.flashTimers.delete(id);
    }, 1400));
  }

  selectRequest(id: string, openSheet = false): void {
    this.selectedRequestId.set(id);
    this.mapFocus.update((n) => n + 1);
    this.ui.selectedCaseId.set(id);
    this.matchIdx.set(0);
    this.openSection.set(this.ui.demoWhy ? 'why' : null);
    this.showOriginal.set(false);
    this.moreOpen.set(false);
    this.changeOpen.set(false);
    this.rejectOpen.set(false);
    this.choseTeam.set(false);
    this.approving.set(false);
    this.loadMatches(id);
    if (openSheet && this.narrow()) this.sheetOpen.set(true);
  }

  setFilterType(type: string): void {
    this.filterType.set(type);
    this.writeFilters();
  }

  setArea(area: string): void {
    this.areaFilter.set(area);
    this.writeFilters();
  }

  setTime(time: string): void {
    if (time === 'hour' || time === 'today' || time === 'all') this.timeFilter.set(time);
    this.writeFilters();
  }

  clearFilters(): void {
    this.bandFilter.set('all');
    this.filterType.set('all');
    this.areaFilter.set('all');
    this.timeFilter.set('all');
    this.writeFilters();
  }

  private readFilters(): void {
    this.filterSub = this.route.queryParamMap.subscribe((params) => {
      if (this.writingFilters) return;
      const status = params.get('status');
      if (status === 'now' || status === 'soon' || status === 'review' || status === 'dispatched' || status === 'completed' || status === 'all') {
        this.bandFilter.set(status);
      }
      const type = params.get('type');
      if (type) this.filterType.set(type);
      this.areaFilter.set(params.get('area') || 'all');
      const time = params.get('time');
      if (time === 'hour' || time === 'today' || time === 'all') this.timeFilter.set(time);
      const focus = params.get('case');
      if (focus && focus !== this.selectedRequestId()) {
        this.focusRequestId = focus;
        if (this.requests().some((row) => row.id === focus)) this.selectRequest(focus, true);
      }
    });
  }

  private writeFilters(): void {
    this.writingFilters = true;
    const q = {
      status: this.bandFilter() === 'all' ? null : this.bandFilter(),
      type: this.filterType() === 'all' ? null : this.filterType(),
      area: this.areaFilter() === 'all' ? null : this.areaFilter(),
      time: this.timeFilter() === 'all' ? null : this.timeFilter(),
    };
    void this.router.navigate([], { relativeTo: this.route, queryParams: q, queryParamsHandling: 'merge', replaceUrl: true }).finally(() => {
      this.writingFilters = false;
    });
  }

  onSearchInput(event: Event): void {
    const val = (event.target as HTMLInputElement).value;
    this.searchQuery.set(val);
  }

  setScenario(scenario: string): void {
    this.scenarioService.select(scenario);
    this.loadRequests();
    this.actionToast.set({
      text: `Switched active scenario to ${scenario.toUpperCase()}`,
      type: 'success',
    });
  }

  toggleWeightsDrawer(): void {
    this.isWeightsDrawerOpen.update((open) => !open);
  }

  onWeightChange(field: keyof UrgencyWeights, event: Event): void {
    const val = parseFloat((event.target as HTMLInputElement).value);
    const updated = { ...this.currentWeights(), [field]: val };
    this.currentWeights.set(updated);

    // Instant (<1s) live queue re-rank
    this.apiClient.updateUrgencyWeights(updated).subscribe({
      next: () => {
        this.loadRequests();
      },
      error: (err) => console.error('Error updating weights:', err),
    });
  }

  resetWeightsToDefaults(): void {
    const defaults: UrgencyWeights = {
      version: 1,
      w_vulnerability: 35,
      w_people: 25,
      w_hazard: 20,
      w_wait_time: 15,
      confidence_discount_factor: 0.15,
    };
    this.currentWeights.set(defaults);
    this.apiClient.updateUrgencyWeights(defaults).subscribe({
      next: () => this.loadRequests(),
    });
  }

  approveMatch(prop: MatchProposal, allowOvercommit = false): void {
    if (this.approving()) return;
    this.approving.set(true);
    this.apiClient.approveMatch(prop.match_id, allowOvercommit).subscribe({
      next: (approved) => {
        this.approving.set(false);
        this.lastSentId.set(prop.request_id);
        this.actionToast.set({
          text: this.langService.translate('coord.dispatchApproved').replace('{team}', prop.resource_name),
          type: 'success',
          undo: true,
        });
        setTimeout(() => this.clearToast(), 8000);

        // Update local request status
        const target = this.requests().find((r) => r.id === prop.request_id);
        const people = target?.people_count || 1;
        const updatedList = this.requests().map((r) =>
          r.id === prop.request_id
            ? { ...r, status: 'dispatched' as const, assigned_resource_id: prop.resource_id, reserved_people: people }
            : r
        );
        this.requests.set(updatedList);

        const updatedResources = this.resources().map((res) => {
          if (res.id !== prop.resource_id) return res;
          const left = Math.max(0, res.capacity_remaining - people);
          return { ...res, capacity_remaining: left, status: (left > 0 ? 'dispatched' : 'depleted') as StoredResource['status'], assigned_request_id: prop.request_id };
        });
        this.resources.set(updatedResources);

        // Reload matches for updated state
        this.loadMatches(prop.request_id);
        const next = this.filteredRequests().find((row) => row.id !== prop.request_id && !this.isDispatched(row) && !this.isCompleted(row));
        if (next) this.selectRequest(next.id);
      },
      error: (err) => {
        this.approving.set(false);
        if (err.status === 400 && err.error?.detail?.includes('Overcommit')) {
          this.pendingMatch = prop;
          this.isOvercommitModalOpen.set(true);
        } else {
          this.actionToast.set({
            text: `Approval error: ${err.error?.detail || err.message}`,
            type: 'warning',
          });
        }
      },
    });
  }

  markArrived(req: StoredRequest): void {
    this.apiClient.markArrived(req.id).subscribe({
      next: () => {
        this.requests.set(this.requests().map((r) => (r.id === req.id ? { ...r, status: 'in_progress' as const } : r)));
        if (req.assigned_resource_id) {
          this.resources.set(this.resources().map((res) => (
            res.id === req.assigned_resource_id
              ? { ...res, status: 'on_scene' as const, simulated: false, lat: req.lat ?? res.lat, lng: req.lng ?? res.lng }
              : res
          )));
        }
        this.actionToast.set({ text: this.langService.translate('coord.arrivedNote'), type: 'success' });
      },
    });
  }

  markCompleted(req: StoredRequest): void {
    this.apiClient.completeRequest(req.id).subscribe({
      next: () => {
        const people = req.reserved_people || req.people_count || 1;
        this.requests.set(this.requests().map((r) => (r.id === req.id ? { ...r, status: 'completed' as const } : r)));
        if (req.assigned_resource_id) {
          this.resources.set(this.resources().map((res) => {
            if (res.id !== req.assigned_resource_id) return res;
            const left = Math.min(res.capacity_total, res.capacity_remaining + people);
            const other = this.requests().find((row) => row.id !== req.id && row.assigned_resource_id === res.id && ['dispatched', 'approved', 'in_progress'].includes(row.status));
            return { ...res, capacity_remaining: left, status: other ? 'dispatched' as const : 'available' as const,
              assigned_request_id: other?.id || null, simulated: !!other && !!res.simulated };
          }));
        }
        this.actionToast.set({ text: this.langService.translate('coord.completedNote'), type: 'success' });
      },
    });
  }

  confirmOvercommit(): void {
    if (this.pendingMatch) {
      const match = this.pendingMatch;
      this.isOvercommitModalOpen.set(false);
      this.pendingMatch = null;
      this.approveMatch(match, true);
    }
  }

  cancelOvercommit(): void {
    this.isOvercommitModalOpen.set(false);
    this.pendingMatch = null;
  }

  openRejectModal(prop: MatchProposal): void {
    this.pendingMatch = prop;
    this.rejectReasonText = '';
    this.rejectOpen.set(true);
    this.isRejectModalOpen.set(false);
  }
  pickRejectReason(key: string): void {
    this.rejectReasonText = this.langService.translate(key);
  }

  closeRejectModal(): void {
    this.isRejectModalOpen.set(false);
    this.pendingMatch = null;
  }

  confirmReject(): void {
    if (this.pendingMatch) {
      const match = this.pendingMatch;
      const reason = this.rejectReasonText.trim() || 'Access road impassable';
      this.apiClient.rejectMatch(match.match_id, reason).subscribe({
        next: () => {
          this.actionToast.set({
            text: `Proposal rejected: "${reason}". Updating candidate match ranking.`,
            type: 'warning',
          });
          this.closeRejectModal();
          this.rejectOpen.set(false);
          this.loadMatches(match.request_id);
        },
        error: (err) => {
          console.error('Error rejecting match:', err);
          this.closeRejectModal();
        },
      });
    }
  }

  countSpans(req: StoredRequest): string[] {
    const spans = (req.count_spans || []).filter((span) => !!span);
    return spans.length > 1 ? spans : [];
  }

  countsDiffer(req: StoredRequest): string {
    this.langService.currentLang();
    const spans = this.countSpans(req).join(' vs ');
    return this.langService.translate('coord.countsDiffer').replace('{spans}', spans);
  }

  confirmMerge(req: StoredRequest): void {
    const hint = req.possible_duplicate;
    if (!hint?.target_id) return;
    this.apiClient.mergeRequests(hint.target_id, req.id, [hint.note || 'Coordinator confirmed the duplicate']).subscribe({
      next: () => this.loadRequests(),
      error: (err) => console.error('Error merging duplicate:', err),
    });
  }

  keepSeparate(req: StoredRequest): void {
    this.apiClient.keepSeparate(req.id).subscribe({
      next: () => {
        this.requests.set(this.requests().map((row) => (
          row.id === req.id ? { ...row, possible_duplicate: null } : row
        )));
        this.loadRequests();
      },
      error: (err) => console.error('Error keeping reports separate:', err),
    });
  }
  undoLastSend(): void {
    const id = this.lastSentId();
    this.clearToast();
    if (id) this.selectRequest(id);
  }

  splitCluster(requestId: string): void {
    this.apiClient.splitCluster(requestId).subscribe({
      next: (res) => {
        this.actionToast.set({
          text: this.langService.translate('ux.undoHint'),
          type: 'success',
        });
        this.loadRequests();
      },
      error: (err) => {
        console.error('Error splitting cluster:', err);
      },
    });
  }

  clearToast(): void {
    this.actionToast.set(null);
  }

  // SVG Radial Math & Color Helpers
  getRadialDasharray(score: number): string {
    const clamped = Math.min(100, Math.max(0, score));
    const filled = (clamped / 100) * 131.9;
    return `${filled.toFixed(1)} 131.9`;
  }

  getMatchDasharray(score: number): string {
    const clamped = Math.min(100, Math.max(0, score));
    const filled = (clamped / 100) * 150.8;
    return `${filled.toFixed(1)} 150.8`;
  }

  getUrgencyColor(score: number): string {
    if (score >= 80) return 'var(--sev-crit)';
    if (score >= 60) return 'var(--sev-high)';
    if (score >= 40) return 'var(--sev-med)';
    return 'var(--sev-low)';
  }

  getUrgencyChipClass(score: number): string {
    if (score >= 80) return 'cr';
    if (score >= 60) return 'cam';
    if (score >= 40) return 'cbl';
    return 'csl';
  }

  getUrgencyBand(score: number): string {
    if (score >= 80) return 'CRITICAL';
    if (score >= 60) return 'HIGH';
    if (score >= 40) return 'MEDIUM';
    return 'LOW';
  }

  detectOriginalLanguage(text: string | null | undefined): string {
    if (!text) return 'English';
    // Devanagari range
    if (/[\u0900-\u097F]/.test(text)) return 'Hindi';
    if (/[\u0D00-\u0D7F]/.test(text)) return 'Malayalam';
    // Hinglish keywords
    const hinglishMarkers = [
      'paani', 'pani', 'badh', 'raha', 'hai', 'hain', 'ke', 'paas', 'chat',
      'par', 'bachao', 'bacche', 'bache', 'buzurg', 'log', 'jaldi', 'bhejo',
      'madad', 'chahiye', 'ghar', 'gali', 'gaya', 'fase', 'chhat'
    ];
    const lower = text.toLowerCase();
    if (hinglishMarkers.some((w) => new RegExp(`\\b${w}\\b`).test(lower))) {
      return 'Hinglish';
    }
    return 'English';
  }

  isLowTranslationConfidence(req: StoredRequest | undefined): boolean {
    if (!req) return false;
    return (
      (req.flags ? req.flags.includes('low_translation_confidence') : false) ||
      (req.translation_confidence !== undefined && req.translation_confidence < 0.70)
    );
  }

  getTranslationConfidencePercent(req: StoredRequest | undefined): number | null {
    if (!req || req.translation_confidence === undefined) return null;
    return Math.round(req.translation_confidence * 100);
  }

  setTranslationLang(lang: 'en' | 'hi'): void {
    this.selectedTranslationLang.set(lang);
  }

  getTranslationText(req: StoredRequest | undefined): string {
    const fallback = this.langService.translate('coord.fallbackSummary');
    if (!req) return fallback;
    const ui = this.langService.currentLang();
    const map = req.translations || {};
    const lang = ui === 'hinglish' ? 'hi' : this.selectedTranslationLang();
    const picks = [ui === 'hinglish' ? map['hinglish'] : '', map[lang], req.ai_translation, req.summary, req.raw_text];
    for (const pick of picks) {
      const text = reportLine(pick);
      if (text) return text;
    }
    return req.place_text || fallback;
  }

  openWhyTeamModal(): void {
    const req = this.selectedRequest();
    if (!req) return;
    const proposals = this.matches().slice(0, 5);

    const droppedTeams: DroppedTeamRow[] = [];
    if (req.lat != null && req.lng != null) {
      const candidateIds = new Set(this.matches().map((m) => m.resource_id));
      for (const res of this.resources()) {
        if (res.kind === 'boat' && !candidateIds.has(res.id)) {
          const dist = haversineKm(req.lat, req.lng, res.lat, res.lng);
          if (dist > 25) {
            droppedTeams.push({
              name: res.name,
              distanceKm: Math.round(dist * 10) / 10,
              reasonKey: 'why.dropped',
            });
          }
        }
      }
    }
    if (droppedTeams.length === 0) {
      droppedTeams.push(
        { name: 'Aluva Ferry Rescue Boat', distanceKm: 76.6, reasonKey: 'why.dropped' },
        { name: 'Chalakudy River Rescue Boat', distanceKm: 99.3, reasonKey: 'why.dropped' }
      );
    }

    this.dialog.open(WhyThisTeamDialogComponent, {
      data: {
        request: req,
        proposals,
        droppedTeams,
        onApprove: () => {
          const active = this.activeProposal();
          if (active) this.approveMatch(active);
        },
        onChooseAnother: () => {
          this.changeOpen.set(true);
        },
      },
    });
  }

  openStepDetailDialog(index: number): void {
    const req = this.selectedRequest();
    if (!req) return;
    const stepKeys = ['flow.intake', 'flow.dedupe', 'flow.urgency', 'flow.matching', 'flow.explain'];
    const agents = ['Intake', 'Dedupe', 'Triage', 'Matching', 'Explainer'];
    const agentName = agents[index] || 'Intake';
    const traceStep = (req.trace || []).find((s) => s.agent === agentName);
    const isGeminiLive = this.ui.aiHealth()?.provider === 'gemini' || this.ui.aiHealth()?.label?.includes('Gemini');
    let badge: 'rules' | 'gemini' | 'cache' | 'tool' | 'test' = 'rules';
    if (index === 3 || agentName === 'Matching') {
      badge = 'tool';
    } else if (traceStep?.provider === 'gemini' || (isGeminiLive && traceStep?.provider !== 'cache')) {
      badge = 'gemini';
    } else if (traceStep?.provider === 'cache' || traceStep?.provider === 'recorded') {
      badge = 'cache';
    } else if (traceStep?.provider === 'tool') {
      badge = 'tool';
    } else if (isGeminiLive) {
      badge = 'gemini';
    }

    this.dialog.open(StepDetailDialogComponent, {
      data: {
        request: req,
        stepIndex: index,
        totalSteps: 5,
        stepNameKey: stepKeys[index] || 'flow.intake',
        badge,
        inputSummary: traceStep?.input_summary || req.raw_text,
        prompt: (traceStep as { prompt?: string })?.prompt || undefined,
        tools: (traceStep?.tool_calls || []).map((t) => typeof t === 'string' ? t : (t as { name?: string }).name || ''),
        rawOutput: traceStep?.output ? (typeof traceStep.output === 'string' ? traceStep.output : JSON.stringify(traceStep.output)) : undefined,
        model: traceStep?.model || undefined,
        latencyMs: traceStep?.latency_ms || undefined,
        fallbackReason: traceStep?.fallback_reason || undefined,
        onNavigate: (newIdx: number) => {
          this.dialog.closeAll();
          this.openStepDetailDialog(newIdx);
        },
      },
    });
  }

  openTraceDrawer(): void {
    const id = this.selectedRequestId();
    if (id) {
      this.traceRequestId.set(id);
    }
  }

  getNeedText(req: StoredRequest): string {
    this.langService.currentLang();
    const need = this.queueNeed(req);
    return need || this.langService.translate('coord.queueNeedBoat');
  }

  getPeopleText(req: StoredRequest): string {
    this.langService.currentLang();
    const n = req.people_count || 1;
    const flags = req.vulnerable;
    const parts: string[] = [];
    if (flags?.elderly) parts.push(this.langService.translate('coord.metaElderly'));
    if (flags?.child) parts.push(this.langService.translate('coord.metaChildren'));
    if (flags?.disabled) parts.push(this.langService.translate('coord.metaDisabled'));
    if (flags?.pregnant) parts.push(this.langService.translate('coord.metaPregnant'));
    if (flags?.medical_need) parts.push(this.langService.translate('coord.metaMedical'));
    if (parts.length) {
      return `${n} · ${parts.join(', ')}`;
    }
    return String(n);
  }

  getDangerText(req: StoredRequest): string {
    this.langService.currentLang();
    if (req.hazard) {
      if (req.hazard === 'water_rising') return this.langService.translate('hazard.water_rising');
      return req.hazard.replace(/_/g, ' ');
    }
    return this.langService.translate('coord.floodRisk');
  }

  getWardText(req: StoredRequest): string {
    if (req.ward_id) {
      const num = req.ward_id.replace(/^ward_/, '');
      if (!Number.isNaN(Number(num))) {
        return this.langService.translate('ward').replace('{n}', num);
      }
      return this.placeName(req.ward_id);
    }
    return req.place_text || '—';
  }

  originalLangName(req: StoredRequest): string {
    const lang = this.detectOriginalLanguage(req.raw_text);
    if (lang === 'Hindi') return 'हिंदी';
    if (lang === 'Malayalam') return 'മലയാളം';
    return lang;
  }

  propEta(prop: MatchProposal): string {
    const mins = prop.eta_minutes ?? Math.round(prop.breakdown?.distance_km ? (prop.resource_kind === 'boat' ? prop.breakdown.distance_km / 12 * 60 : prop.breakdown.distance_km / 30 * 60) : 10);
    return `~${mins} min`;
  }

  propEtaSubline(prop: MatchProposal): string {
    const mins = prop.eta_minutes ?? Math.round(prop.breakdown?.distance_km ? (prop.resource_kind === 'boat' ? prop.breakdown.distance_km / 12 * 60 : prop.breakdown.distance_km / 30 * 60) : 10);
    const mode = prop.travel_mode || (prop.resource_kind === 'boat' ? 'water' : 'road');
    const km = prop.breakdown?.distance_km != null ? `${prop.breakdown.distance_km.toFixed(1)} km` : '';
    const seats = `${prop.capacity_remaining ?? prop.capacity_total} seats`;
    return [`~${mins} min by ${mode}`, km, seats].filter(Boolean).join(' · ');
  }

  toggleShowOriginal(): void {
    this.showOriginal.update((v) => !v);
  }

  getOriginalQuote(req: StoredRequest): string {
    return req.raw_text || req.place_text || '';
  }
}

const INTERNAL = /urgency score|vulnerable flags/i;

/** A case title is what the reporter said. Scoring notes and the card's "| Vulnerable: …" tail never show. */
export function reportLine(text: string | null | undefined): string {
  const kept = (text || '')
    .split(' | ')
    .filter((part) => !/^\s*(vulnerable|hazard):/i.test(part))
    .join(' ')
    .trim();
  return kept && !INTERNAL.test(kept) ? kept : '';
}
