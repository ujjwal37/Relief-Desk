import { ChangeDetectionStrategy, Component, HostListener, OnDestroy, computed, inject, signal } from '@angular/core';
import { ActivatedRoute, NavigationEnd, Router, RouterLink, RouterLinkActive, RouterOutlet } from '@angular/router';
import { filter } from 'rxjs';
import { AuthService, LanguageService, RdTranslatePipe, SUPPORTED_LANGUAGES, ThemeMode, ThemeService } from '@rd/shared';
import { ScenarioService } from '../../core/services/scenario.service';
import { CoordUiService } from '../../core/services/coord-ui.service';
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
  readonly compactNav = signal(false);
  readonly langs = SUPPORTED_LANGUAGES;
  readonly themes: { m: ThemeMode; k: string }[] = [
    { m: 'light', k: 'settings.themeLight' }, { m: 'dark', k: 'settings.themeDark' }, { m: 'system', k: 'settings.themeSystem' },
  ];
  readonly initial = computed(() => (this.authService.currentUser()?.email || 'D').charAt(0).toUpperCase());
  readonly path = signal('');
  readonly dispatchedOn = computed(() => /(?:\?|&)status=dispatched(?:&|$)/.test(this.path()));
  readonly casesOn = computed(() => {
    const path = this.path().split('?')[0];
    return (path === '/coordinator/command' || path.startsWith('/coordinator/command/')) && !this.dispatchedOn();
  });

  private media?: MediaQueryList;
  private onMedia = (event: MediaQueryListEvent): void => { this.wideEnough.set(event.matches); };
  private stopQuery?: () => void;

  constructor() {
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
    this.syncCompactNav();
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
  }

  toggleDemo(): void {
    this.menuOpen.set(false);
    this.router.navigate([], { relativeTo: this.route, queryParams: { demo: this.demoOn() ? null : '1' }, queryParamsHandling: 'merge' });
  }

  /** Search filters the Cases queue, so typing on another tab opens Cases with the query kept. */
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
