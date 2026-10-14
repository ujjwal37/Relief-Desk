import { ChangeDetectionStrategy, Component, HostListener, OnDestroy, computed, effect, inject, signal } from '@angular/core';
import { ActivatedRoute, NavigationEnd, Router, RouterLink, RouterLinkActive, RouterOutlet } from '@angular/router';
import { filter } from 'rxjs';
import { ApiClientService, AuthService, LanguageService, MORE_LANGUAGES, PRIMARY_LANGUAGES, RdTranslatePipe, ThemeMode, ThemeService } from '@rd/shared';
import { ScenarioService } from '../../core/services/scenario.service';
import { CoordUiService } from '../../core/services/coord-ui.service';
import { LiveEventsService } from '../../core/live-events.service';
import { TourComponent } from '../../core/components/tour.component';

@Component({
  selector: 'app-coordinator-layout',
  standalone: true,
  imports: [RouterOutlet, RouterLink, RouterLinkActive, RdTranslatePipe, TourComponent],
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

  readonly demoOn = signal(false);
  readonly wideEnough = signal(true);
  readonly showPhone = computed(() => this.demoOn() && this.wideEnough());
  readonly menuOpen = signal(false);
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
  selectScenario(id: string): void { this.scenarioService.select(id); this.menuOpen.set(false); location.reload(); }

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
