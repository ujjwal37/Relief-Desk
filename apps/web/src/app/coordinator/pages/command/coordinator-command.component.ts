import { CommonModule } from '@angular/common';
import {
  ChangeDetectionStrategy,
  Component,
  OnInit,
  computed,
  inject,
  signal,
} from '@angular/core';
import { FormsModule } from '@angular/forms';
import { ScenarioService } from '../../../core/services/scenario.service';
import {
  ApiClientService,
  MatchProposal,
  StoredRequest,
  StoredResource,
  UrgencyWeights,
} from '@rd/shared';

@Component({
  selector: 'app-coordinator-command',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './coordinator-command.component.html',
  styleUrl: './coordinator-command.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class CoordinatorCommandComponent implements OnInit {
  private readonly apiClient = inject(ApiClientService);
  private readonly scenarioService = inject(ScenarioService);

  readonly Math = Math;

  // Reactive state signals
  readonly requests = signal<StoredRequest[]>([]);
  readonly selectedRequestId = signal<string>('INC-001');
  readonly matches = signal<MatchProposal[]>([]);
  readonly resources = signal<StoredResource[]>([]);
  readonly filterType = signal<string>('all');
  readonly searchQuery = signal<string>('');
  readonly activeScenario = this.scenarioService.activeId;
  readonly scenarios = this.scenarioService.scenarios;
  readonly isWeightsDrawerOpen = signal<boolean>(false);
  readonly isOvercommitModalOpen = signal<boolean>(false);
  readonly isRejectModalOpen = signal<boolean>(false);
  readonly actionToast = signal<{ text: string; type: 'success' | 'warning' } | null>(null);
  readonly selectedTranslationLang = signal<'en' | 'hi' | 'ta'>('en');

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
    return this.matches()[0];
  });

  readonly filteredRequests = computed<StoredRequest[]>(() => {
    let list = this.requests();
    const type = this.filterType();
    const query = this.searchQuery().toLowerCase().trim();

    if (type !== 'all') {
      list = list.filter((r) => r.type === type);
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

  readonly criticalCount = computed<number>(() => {
    return this.requests().filter((r) => r.urgency_score >= 85).length;
  });

  readonly availableBoatsCount = computed<number>(() => {
    const boats = this.resources().filter((res) => res.kind === 'boat');
    return boats.filter((b) => b.capacity_remaining > 0).length || 4;
  });

  ngOnInit(): void {
    this.scenarioService.ensureLoaded();
    this.loadRequests();
    this.loadResources();
    this.loadWeights();
  }

  loadRequests(): void {
    this.apiClient.getRequests('urgency', this.activeScenario()).subscribe({
      next: (reqs) => {
        this.requests.set(reqs);
        if (reqs.length > 0 && !this.selectedRequestId()) {
          this.selectRequest(reqs[0].id);
        } else if (this.selectedRequestId()) {
          this.loadMatches(this.selectedRequestId());
        }
      },
      error: (err) => console.error('Failed to load requests:', err),
    });
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
        const updatedList = this.requests().map((r) =>
          r.id === prop.request_id ? { ...r, status: 'approved' as const } : r
        );
        this.requests.set(updatedList);

        // Update capacity locally
        const updatedResources = this.resources().map((res) =>
          res.id === prop.resource_id
            ? { ...res, capacity_remaining: Math.max(0, res.capacity_remaining - (this.selectedRequest()?.people_count || 1)) }
            : res
        );
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
