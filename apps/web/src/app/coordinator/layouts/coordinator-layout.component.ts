import { ChangeDetectionStrategy, Component, OnDestroy, computed, inject, signal } from '@angular/core';
import { ActivatedRoute, Router, RouterLink, RouterOutlet } from '@angular/router';
import { AuthService, RdTranslatePipe, LanguageSwitcherComponent } from '@rd/shared';
import { ScenarioSwitcherComponent } from '../../core/components/scenario-switcher.component';

@Component({
  selector: 'app-coordinator-layout',
  standalone: true,
  imports: [RouterOutlet, RouterLink, RdTranslatePipe, LanguageSwitcherComponent, ScenarioSwitcherComponent],
  templateUrl: './coordinator-layout.component.html',
  styleUrl: './coordinator-layout.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class CoordinatorLayoutComponent implements OnDestroy {
  readonly authService = inject(AuthService);
  private router = inject(Router);
  private route = inject(ActivatedRoute);

  readonly demoOn = signal(false);
  readonly wideEnough = signal(true);
  readonly showPhone = computed(() => this.demoOn() && this.wideEnough());

  private media?: MediaQueryList;
  private onMedia = (event: MediaQueryListEvent): void => {
    this.wideEnough.set(event.matches);
  };
  private stopQuery?: () => void;

  constructor() {
    this.media = window.matchMedia('(min-width: 600px)');
    this.wideEnough.set(this.media.matches);
    this.media.addEventListener('change', this.onMedia);
    const sub = this.route.queryParamMap.subscribe((params) => {
      this.demoOn.set(params.get('demo') === '1');
    });
    this.stopQuery = () => sub.unsubscribe();
  }

  ngOnDestroy(): void {
    this.media?.removeEventListener('change', this.onMedia);
    this.stopQuery?.();
  }

  toggleDemo(): void {
    this.router.navigate([], {
      relativeTo: this.route,
      queryParams: { demo: this.demoOn() ? null : '1' },
      queryParamsHandling: 'merge',
    });
  }

  logout(): void {
    this.authService.logout();
    this.router.navigate(['/coordinator/login']);
  }
}
