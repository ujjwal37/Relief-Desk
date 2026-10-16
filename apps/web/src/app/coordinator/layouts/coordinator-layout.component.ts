import { ChangeDetectionStrategy, Component, HostListener, OnDestroy, computed, effect, inject, signal } from '@angular/core';
import { ActivatedRoute, NavigationEnd, Router, RouterLink, RouterLinkActive, RouterOutlet } from '@angular/router';
import { filter } from 'rxjs';
import { AiHealthResponse, ApiClientService, AuthService, LanguageService, MORE_LANGUAGES, PRIMARY_LANGUAGES, RdTranslatePipe, SitrepResponse, ThemeMode, ThemeService } from '@rd/shared';
import { ScenarioService } from '../../core/services/scenario.service';
import { CoordUiService } from '../../core/services/coord-ui.service';
import { LiveEventsService } from '../../core/live-events.service';
import { TourComponent } from '../../core/components/tour.component';
import { SitrepPanelComponent } from '../agents/sitrep-panel.component';
import { AskDeskComponent } from '../agents/ask-desk.component';

@Component({
  selector: 'app-coordinator-layout',
  standalone: true,
  imports: [RouterOutlet, RouterLink, RouterLinkActive, RdTranslatePipe, TourComponent, SitrepPanelComponent, AskDeskComponent],
  templateUrl: './coordinator-layout.component.html',
  styleUrl: './coordinator-layout.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class CoordinatorLayoutComponent implements OnDestroy {
  readonly authService = inject(AuthService);
  readonly live = inject(LiveEventsService);
  readonly ui = inject(CoordUiService);
  readonly theme = inject(ThemeService);
  readonly lang = inject(LanguageService);
  readonly scenarioService = inject(ScenarioService);
  private router = inject(Router);
  private route = inject(ActivatedRoute);

  readonly demoAllowed = signal(false);
  readonly aiHealth = signal<AiHealthResponse | null>(null);
  readonly sitrepOpen = signal(false);
  readonly sitrepBusy = signal(false);
  readonly sitrepError = signal(false);
  readonly sitrep = signal<SitrepResponse | null>(null);
  private sitrepAt = 0;
  readonly surgeBusy = signal(false);
  readonly surgeNotice = signal('');
  readonly mergeNotice = signal('');
  private mergeTimer?: ReturnType<typeof setTimeout>;
  private stopSurge?: () => void;
  private surgePoll?: ReturnType<typeof setInterval>;
  private aiHealthPoll?: ReturnType<typeof setInterval>;
  readonly demoOn = signal(false);
  readonly wideEnough = signal(true);
  readonly showPhone = computed(() => this.demoOn() && this.wideEnough());
  readonly menuOpen = signal(false);
  readonly askDeskOpen = signal(false);
  readonly guideOpen = signal(false);
  private api = inject(ApiClientService);
  readonly compactNav = signal(false);
  readonly primaryLangs = PRIMARY_LANGUAGES;
  readonly moreLangs = MORE_LANGUAGES;
  readonly langMore = signal(false);
  readonly themes: { m: ThemeMode; k: string }[] = [
    { m: 'light', k: 'settings.themeLight' }, { m: 'dark', k: 'settings.themeDark' }, { m: 'system', k: 'settings.themeSystem' },
  ];
  readonly initial = computed(() => (this.authService.currentUser()?.email || 'D').charAt(0).toUpperCase());
  readonly liveLabel = computed(() => {
    const state = this.live.state();
    if (state === 'live') return 'coord.live';
    if (state === 'offline') return 'coord.liveOff';
    return 'coord.liveRetry';
  });
  readonly path = signal('');
  readonly dispatchedOn = computed(() => /(?:\?|&)status=dispatched(?:&|$)/.test(this.path()));
  readonly homeOn = computed(() => {
    const path = this.path().split('?')[0];
    return (path === '/coordinator/command' || path.startsWith('/coordinator/command/')) && !this.dispatchedOn();
  });

  private media?: MediaQueryList;
  private onMedia = (event: MediaQueryListEvent): void => { this.wideEnough.set(event.matches); };
  private stopQuery?: () => void;

  constructor() {
    effect(() => {
      if (!this.menuOpen()) this.langMore.set(false);
    });
    this.theme.ensureDefault('light');
    this.media = window.matchMedia('(min-width: 600px)');
    this.wideEnough.set(this.media.matches);
    this.media.addEventListener('change', this.onMedia);
    const sub = this.route.queryParamMap.subscribe((params) => { this.demoOn.set(params.get('demo') === '1'); });
    this.path.set(this.router.url);
    const nav = this.router.events.pipe(filter((event): event is NavigationEnd => event instanceof NavigationEnd))
      .subscribe(() => this.path.set(this.router.url));
    this.stopQuery = () => { sub.unsubscribe(); nav.unsubscribe(); };
    this.scenarioService.ensureLoaded();
    this.ui.loadAlerts();
    this.live.connectDesk();
    this.api.getHealth().subscribe({ next: (health) => this.demoAllowed.set(!!health.demo_mode), error: () => this.demoAllowed.set(false) });
    this.refreshAiHealth();
    this.prewarmSitrep();
    // The pill reads "Rules fallback" until the first Gemini call succeeds; keep it current.
    this.aiHealthPoll = setInterval(() => this.refreshAiHealth(), 15000);
    this.maybeStartTour();
    this.stopSurge = this.live.onEvent((event) => {
      if (event.type === 'case.merged' && event.request_ids?.[0]) {
        this.mergeNotice.set(this.lang.translate('demo.mergeNotice').replace('{id}', event.request_ids[0]));
        clearTimeout(this.mergeTimer);
        this.mergeTimer = setTimeout(() => this.mergeNotice.set(''), 7000);
      }
      if (event.type !== 'demo.surge') return;
      this.surgeBusy.set(!!event.running);
      this.surgeNotice.set(this.lang.translate(event.failed ? 'demo.surgeFailed' : event.running ? 'demo.surgeProgress' : 'demo.surgeDone').replace('{n}', String(event.submitted || 0)));
    });
    this.syncCompactNav();
    this.guideOpen.set(!this.guideDismissed());
  }

  private guideDismissed(): boolean {
    try {
      return localStorage.getItem('rd_guide_dismissed') === '1' || localStorage.getItem('rd_tour_done') === '1';
    } catch {
      return true;
    }
  }

  dismissGuide(): void {
    this.guideOpen.set(false);
    try { localStorage.setItem('rd_guide_dismissed', '1'); } catch { /* private mode */ }
  }

  resetDemo(): void {
    if (!window.confirm(this.lang.translate('ux.resetDemoConfirm'))) return;
    this.menuOpen.set(false);
    this.api.resetDemo().subscribe({ next: () => location.reload() });
  }

  loadFullScenario(): void {
    if (!window.confirm(this.lang.translate('ux.loadFullConfirm'))) return;
    this.menuOpen.set(false);
    this.api.loadFullScenario().subscribe({ next: () => location.reload() });
  }

  syncCompactNav(): void {
    this.compactNav.set(window.innerWidth <= 900);
  }

  @HostListener('window:resize')
  onResize(): void {
    this.syncCompactNav();
  }

  ngOnDestroy(): void {
    this.media?.removeEventListener('change', this.onMedia);
    clearInterval(this.surgePoll);
    clearInterval(this.aiHealthPoll);
    clearTimeout(this.mergeTimer);
    this.stopSurge?.();
    this.stopQuery?.();
    this.live.stop();
  }

  toggleDemo(): void {
    this.menuOpen.set(false);
    this.router.navigate([], { relativeTo: this.route, queryParams: { demo: this.demoOn() ? null : '1' }, queryParamsHandling: 'merge' });
  }

  /** Search filters the Home queue, so typing on another tab opens Home with the query kept. */
  onSearch(event: Event): void {
    this.ui.searchQuery.set((event.target as HTMLInputElement).value);
    if (!this.router.url.startsWith('/coordinator/command')) {
      this.router.navigateByUrl('/coordinator/command');
    }
  }
  openWeights(): void { this.menuOpen.set(false); this.ui.weightsOpen.set(true); }
  takeTour(): void { this.menuOpen.set(false); this.router.navigateByUrl('/coordinator/command').then(() => setTimeout(() => this.ui.startTour(), 150)); }
  toggleAskDesk(): void { this.askDeskOpen.update((v) => !v); }
  onDeskCasePicked(caseId: string): void {
    this.askDeskOpen.set(false);
    this.router.navigate(['/coordinator/command'], { queryParams: { id: caseId }, queryParamsHandling: 'merge' });
  }

  private maybeStartTour(): void {
    try {
      if (sessionStorage.getItem('rd_start_tour') !== '1') return;
      sessionStorage.removeItem('rd_start_tour');
      if (this.ui.tourDone()) return;
    } catch {
      return;
    }
    void this.router.navigateByUrl('/coordinator/command').then(() => setTimeout(() => this.ui.startTour(), 280));
  }

  onTourAction(kind: 'sample' | 'ask'): void {
    if (kind === 'sample') {
      this.sendSample('hindi');
      this.ui.tourStep.update((step) => Math.min(5, step + 1));
      return;
    }
    this.ui.finishTour();
    void this.router.navigate(['/coordinator/agent'], { queryParams: { ask: 'pending' } });
  }

  aiPillText(): string {
    this.lang.currentLang();
    if (this.aiHealth()?.provider === 'gemini') return this.lang.translate('xfactor.geminiLive');
    return this.lang.translate('coord.aiOffline');
  }

  geminiCalls(): number | null {
    const calls = this.aiHealth()?.quota?.calls;
    return typeof calls === 'number' ? calls : null;
  }

  refreshAiHealth(): void {
    this.api.getAiHealth?.().subscribe({
      next: (health) => {
        this.aiHealth.set(health);
        this.ui.aiHealth.set(health);
      },
      error: () => {
        const fallback = { provider: 'fallback', model: '', label: '' };
        this.aiHealth.set(fallback);
        this.ui.aiHealth.set(fallback);
      },
    });
  }

  sendSample(kind: 'hindi' | 'voice' | 'photo' | 'duplicate'): void {
    if (this.surgeBusy()) return;
    this.surgeBusy.set(true);
    this.api.submitSampleReport(kind).subscribe({
      next: (res) => {
        this.surgeBusy.set(false);
        this.surgeNotice.set(this.lang.translate('xfactor.sampleDone').replace('{id}', res.request_id));
        void this.router.navigate(['/coordinator/command'], { queryParams: { case: res.request_id } });
      },
      error: () => {
        this.surgeBusy.set(false);
        this.surgeNotice.set(this.lang.translate('xfactor.sampleFailed'));
      },
    });
  }

  private prewarmSitrep(): void {
    this.api.generateSitrep().subscribe({
      next: (report) => {
        this.sitrep.set(report);
        this.sitrepAt = Date.now();
      },
      error: () => undefined,
    });
  }

  openSitrep(): void {
    this.menuOpen.set(false);
    this.sitrepOpen.set(true);
    this.sitrepError.set(false);
    const now = Date.now();
    if (this.sitrep() && now - this.sitrepAt < 120000) return;
    this.sitrepBusy.set(true);
    this.api.generateSitrep().subscribe({
      next: (report) => {
        this.sitrep.set(report);
        this.sitrepBusy.set(false);
        this.sitrepAt = Date.now();
      },
      error: () => {
        this.sitrepBusy.set(false);
        this.sitrepError.set(true);
      },
    });
  }
  selectScenario(id: string): void {
    const open = () => { this.scenarioService.select(id); this.menuOpen.set(false); location.reload(); };
    if (this.demoAllowed()) this.api.loadScenarioDemo(id).subscribe({ next: open, error: () => this.surgeNotice.set(this.lang.translate('demo.scenarioFailed')) });
    else open();
  }

  simulateSurge(): void {
    if (this.surgeBusy()) return;
    this.surgeBusy.set(true);
    this.scenarioService.select('flood');
    this.router.navigateByUrl('/coordinator/command');
    this.api.simulateSurge().subscribe({
      next: () => {
        this.surgeNotice.set(this.lang.translate('demo.surgeProgress').replace('{n}', '0'));
        clearInterval(this.surgePoll);
        this.surgePoll = setInterval(() => this.api.getSurgeState().subscribe({
          next: (state) => {
            this.surgeBusy.set(state.running);
            this.surgeNotice.set(this.lang.translate(state.failed ? 'demo.surgeFailed' : state.running ? 'demo.surgeProgress' : 'demo.surgeDone').replace('{n}', String(state.submitted)));
            if (!state.running) clearInterval(this.surgePoll);
          },
          error: () => { clearInterval(this.surgePoll); this.surgeBusy.set(false); this.surgeNotice.set(this.lang.translate('demo.surgeUnavailable')); },
        }), 2500);
      },
      error: () => { this.surgeBusy.set(false); this.surgeNotice.set(this.lang.translate('demo.surgeUnavailable')); },
    });
  }

  logout(): void {
    this.authService.logout();
    this.router.navigate(['/coordinator/login']);
  }

  @HostListener('document:keydown.escape') onEsc(): void { this.menuOpen.set(false); }
  @HostListener('document:keydown', ['$event']) onSlash(e: KeyboardEvent): void {
    const t = e.target as HTMLElement;
    if (e.key === '/' && !/INPUT|TEXTAREA|SELECT/.test(t?.tagName)) {
      e.preventDefault();
      (document.getElementById('coord-search') as HTMLInputElement | null)?.focus();
    }
  }
}
