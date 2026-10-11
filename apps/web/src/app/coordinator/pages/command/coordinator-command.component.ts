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
import { HostListener, effect } from '@angular/core';
import { CoordUiService } from '../../../core/services/coord-ui.service';
import { SevChipComponent } from '../../../core/components/sev-chip.component';
import { ScenarioService } from '../../../core/services/scenario.service';
import { MapPin, MapProviderComponent } from '../../../core/maps/map-provider.component';
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

@Component({
  selector: 'app-coordinator-command',
  standalone: true,
  imports: [CommonModule, FormsModule, MapProviderComponent, SevChipComponent, RdTranslatePipe],
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
      });
    }
    for (const res of this.resources()) {
      pins.push({ id: res.id, lat: res.lat, lng: res.lng, title: res.name });
    }
    return pins;
  });
  readonly filterType = signal<string>('all');
  readonly searchQuery = this.ui.searchQuery;
  readonly bandFilter = signal<'all' | 'now' | 'soon' | 'review' | 'dispatched' | 'completed'>('all');
  readonly freshIds = signal<Set<string>>(new Set());
  private queueWatermark = '';
  private pollTimer: ReturnType<typeof setInterval> | null = null;
  readonly briefingOpen = signal(true);
  readonly openSection = signal<'why' | 'reports' | null>(null);
  readonly showOriginal = signal(false);
  readonly changeOpen = signal(false);
  readonly matchIdx = signal(0);
  readonly activeScenario = this.scenarioService.activeId;
  readonly scenarios = this.scenarioService.scenarios;
  readonly isWeightsDrawerOpen = signal<boolean>(false);
  readonly isOvercommitModalOpen = signal<boolean>(false);
  readonly isRejectModalOpen = signal<boolean>(false);
  readonly actionToast = signal<{ text: string; type: 'success' | 'warning' } | null>(null);
  readonly selectedTranslationLang = signal<'en' | 'hi' | 'ta'>('en');

  private initialSelectDone = false;
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
      list = list.filter((r) => this.isDispatched(r));
    } else if (bf === 'completed') {
      list = list.filter((r) => this.isCompleted(r));
    } else {
      list = list.filter((r) => !this.isDispatched(r) && !this.isCompleted(r));
      if (bf === 'now') list = list.filter((r) => urgencyBand(r.urgency_score) === 'critical');
      if (bf === 'soon') list = list.filter((r) => urgencyBand(r.urgency_score) === 'high');
      if (bf === 'review') list = list.filter((r) => needsReview(r));
    }

    if (query) {
      list = list.filter(
        (r) =>
          r.id.toLowerCase().includes(query) ||
          (r.place_text && r.place_text.toLowerCase().includes(query)) ||
          (r.ward_id && r.ward_id.toLowerCase().includes(query))
      );
    }

    return list;
  });

  readonly activeRequests = computed(() => this.requests().filter((r) => !this.isDispatched(r) && !this.isCompleted(r)));
  readonly counts = computed(() => ({
    ...bandCounts(this.activeRequests()),
    dispatched: this.requests().filter((r) => this.isDispatched(r)).length,
    completed: this.requests().filter((r) => this.isCompleted(r)).length,
  }));
  readonly criticalCount = computed<number>(() => this.counts().critical);
  readonly teamsFree = computed(() => {
    const teams = this.resources().filter((r) => r.kind === 'boat' || r.kind === 'medical');
    const pool = teams.length ? teams : this.resources();
    return { free: pool.filter((r) => r.status === 'available' && r.capacity_remaining > 0).length, total: pool.length };
  });
  readonly quietCount = computed(() => this.ui.alerts().filter((a) => a.kind === 'silent_zone').length);
  readonly briefing = computed(() => {
    this.langService.currentLang();
    const c = this.counts();
    const t = (k: string, n: number) => this.langService.translate(k).replace('{n}', String(n));
    if (c.critical > 0) return t('coord.briefNow', c.critical);
    if (c.high > 0) return t('coord.briefSoon', c.high);
    return this.langService.translate('coord.briefNone');
  });
  readonly svgPins = computed(() => {
    const reqs = this.requests().filter((r) => r.lat != null && r.lng != null);
    const res = this.resources();
    const pts = [...reqs.map((r) => ({ lat: r.lat as number, lng: r.lng as number })), ...res.map((r) => ({ lat: r.lat, lng: r.lng }))];
    if (!pts.length) return [] as { id: string; x: number; y: number; band: string; kind: 'req' | 'team'; team: string; n: number }[];
    const minLa = Math.min(...pts.map((p) => p.lat)), maxLa = Math.max(...pts.map((p) => p.lat));
    const minLo = Math.min(...pts.map((p) => p.lng)), maxLo = Math.max(...pts.map((p) => p.lng));
    const fx = (lng: number) => 50 + ((lng - minLo) / Math.max(1e-6, maxLo - minLo)) * 500;
    const fy = (lat: number) => 40 + (1 - (lat - minLa) / Math.max(1e-6, maxLa - minLa)) * 400;
    const top = this.filteredRequests().filter((r) => r.lat != null && r.lng != null).slice(0, 14);
    return [
      ...res.map((r) => ({ id: r.id, x: fx(r.lng), y: fy(r.lat), band: 'team', kind: 'team' as const, team: r.kind, n: 0 })),
      ...top.map((r, i) => ({ id: r.id, x: fx(r.lng as number), y: fy(r.lat as number), band: urgencyBand(r.urgency_score), kind: 'req' as const, team: '', n: i + 1 })),
    ];
  });
  readonly selectedPin = computed(() => this.svgPins().find((p) => p.id === this.selectedRequest()?.id));

  teamFill(kind: string): string {
    return ({ boat: '#0b6e99', medical: '#b42318', food: '#b54708', shelter: '#067647' } as Record<string, string>)[kind] || '#0b6e99';
  }
  bandOf(score: number): 'critical' | 'high' | 'medium' | 'low' { return urgencyBand(score); }
  isReview(r: StoredRequest): boolean { return needsReview(r); }
  isDispatched(r: StoredRequest): boolean {
    return r.status === 'approved' || r.status === 'dispatched' || r.status === 'in_progress';
  }
  isCompleted(r: StoredRequest): boolean {
    return r.status === 'completed' || r.status === 'resolved' || r.status === 'closed';
  }
  fitPct(p: MatchProposal): number { return Math.round(p.score); }
  ageLabel(r: StoredRequest): string {
    if (!r.created_at) return '';
    const m = Math.max(0, Math.round((Date.now() - new Date(r.created_at).getTime()) / 60000));
    return m < 60 ? `${m} min` : `${Math.round(m / 60)} h`;
  }
  tr(key: string, n: number): string { this.langService.currentLang(); return this.langService.translate(key).replace('{n}', String(n)); }
  toggleSection(s: 'why' | 'reports'): void { this.openSection.set(this.openSection() === s ? null : s); }
  setBandFilter(f: 'all' | 'now' | 'soon' | 'review' | 'dispatched' | 'completed'): void { this.bandFilter.set(f); }
  pickMatch(i: number): void { this.matchIdx.set(i); this.changeOpen.set(false); }
  closeWeights(): void { this.ui.weightsOpen.set(false); }

  @HostListener('document:keydown', ['$event'])
  onKey(e: KeyboardEvent): void {
    const t = e.target as HTMLElement;
    if (/INPUT|TEXTAREA|SELECT/.test(t?.tagName) || e.ctrlKey || e.metaKey) return;
    const list = this.filteredRequests();
    const i = list.findIndex((r) => r.id === this.selectedRequestId());
    if (e.key === 'j' && i < list.length - 1) this.selectRequest(list[i + 1].id);
    if (e.key === 'k' && i > 0) this.selectRequest(list[i - 1].id);
    if (e.key === 'a') (document.querySelector('.btn-approve') as HTMLElement | null)?.focus();
  }

  readonly availableBoatsCount = computed<number>(() => {
    const boats = this.resources().filter((res) => res.kind === 'boat');
    return boats.filter((b) => b.capacity_remaining > 0).length || 4;
  });

  constructor() {
    effect((onCleanup) => {
      if (this.actionToast()) {
        const id = setTimeout(() => this.actionToast.set(null), 5000);
        onCleanup(() => clearTimeout(id));
      }
    });
  }

  ngOnInit(): void {
    this.ui.loadAlerts();
    if (!this.ui.tourDone()) setTimeout(() => this.ui.startTour(), 900);
    this.scenarioService.ensureLoaded();
    this.loadRequests();
    this.loadResources();
    this.loadWeights();
    this.startQueuePoll();
    window.addEventListener('message', this.handleDemoMessage);
    document.addEventListener('visibilitychange', this.onQueueVisibility);
  }

  ngOnDestroy(): void {
    this.stopQueuePoll();
    window.removeEventListener('message', this.handleDemoMessage);
    document.removeEventListener('visibilitychange', this.onQueueVisibility);
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
    }, 4000);
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
    if (event.data?.type === 'rd-report-submitted') {
      this.loadRequests();
    }
  };

  loadRequests(incremental = false): void {
    const since = incremental ? this.queueWatermark : undefined;
    this.apiClient.getRequests('urgency', this.activeScenario(), since || undefined).subscribe({
      next: (reqs) => this.applyQueue(reqs, incremental),
      error: (err) => console.error('Failed to load requests:', err),
    });
  }

  /** Merge a poll into the open queue. Keeps the selected case and flags brand-new rows. */
  applyQueue(incoming: StoredRequest[], incremental: boolean): void {
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
    const keep = this.selectedRequestId();
    this.requests.set(next);
    this.freshIds.set(fresh);
    this.ui.lastRefresh.set(Date.now());
    if (!this.initialSelectDone && next.length > 0) {
      this.initialSelectDone = true;
      this.selectedRequestId.set(next[0].id);
      this.loadMatches(next[0].id);
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
      next: (resList) => this.resources.set(resList),
      error: (err) => console.error('Failed to load resources:', err),
    });
  }

  loadWeights(): void {
    this.apiClient.getUrgencyWeights().subscribe({
      next: (w) => this.currentWeights.set(w),
      error: (err) => console.warn('Using default weights:', err),
    });
  }

  selectRequest(id: string): void {
    this.selectedRequestId.set(id);
    this.matchIdx.set(0);
    this.openSection.set(this.ui.demoWhy ? 'why' : null);
    this.showOriginal.set(false);
    this.loadMatches(id);
  }

  setFilterType(type: string): void {
    this.filterType.set(type);
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
    this.apiClient.approveMatch(prop.match_id, allowOvercommit).subscribe({
      next: (approved) => {
        this.actionToast.set({
          text: `✓ Dispatch Approved: ${prop.resource_name} dispatched for ${this.selectedRequest()?.place_text || prop.request_id}`,
          type: 'success',
        });

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
      },
      error: (err) => {
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
            return { ...res, capacity_remaining: left, status: 'available' as const };
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
    this.isRejectModalOpen.set(true);
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
          this.loadMatches(match.request_id);
        },
        error: (err) => {
          console.error('Error rejecting match:', err);
          this.closeRejectModal();
        },
      });
    }
  }

  splitCluster(requestId: string): void {
    this.apiClient.splitCluster(requestId).subscribe({
      next: (res) => {
        this.actionToast.set({
          text: `Cluster split undone: Constituent requests restored as independent reports (Audited).`,
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
    if (score >= 85) return '#fb7185'; // Red
    if (score >= 70) return '#fbbf24'; // Amber
    if (score >= 50) return '#60a5fa'; // Blue
    return '#94a3b8'; // Slate
  }

  getUrgencyChipClass(score: number): string {
    if (score >= 85) return 'cr';
    if (score >= 70) return 'cam';
    if (score >= 50) return 'cbl';
    return 'csl';
  }

  getUrgencyBand(score: number): string {
    if (score >= 85) return 'CRITICAL';
    if (score >= 70) return 'HIGH';
    if (score >= 50) return 'MEDIUM';
    return 'LOW';
  }

  detectOriginalLanguage(text: string | null | undefined): string {
    if (!text) return 'English';
    // Devanagari range
    if (/[\u0900-\u097F]/.test(text)) return 'Hindi';
    // Tamil range
    if (/[\u0B80-\u0BFF]/.test(text)) return 'Tamil';
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

  getTranslationConfidencePercent(req: StoredRequest | undefined): number {
    if (!req || req.translation_confidence === undefined) return 92;
    return Math.round(req.translation_confidence * 100);
  }

  setTranslationLang(lang: 'en' | 'hi' | 'ta'): void {
    this.selectedTranslationLang.set(lang);
  }

  getTranslationText(req: StoredRequest | undefined): string {
    if (!req) return 'Urgent assistance requested at this location.';
    const lang = this.selectedTranslationLang();
    if (req.translations && req.translations[lang]) {
      return req.translations[lang];
    }
    return req.ai_translation || req.place_text || 'Urgent assistance requested at this location.';
  }
}
