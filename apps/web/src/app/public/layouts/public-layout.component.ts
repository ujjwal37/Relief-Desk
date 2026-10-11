import { ChangeDetectionStrategy, Component, DestroyRef, inject, signal, viewChild } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { NavigationEnd, Router, RouterLink, RouterLinkActive, RouterOutlet } from '@angular/router';
import { filter } from 'rxjs';
import { CallPillComponent, QuietFooterComponent, RdTranslatePipe, SettingsButtonComponent } from '@rd/shared';
import { ScenarioSwitcherComponent } from '../../core/components/scenario-switcher.component';

@Component({
  selector: 'app-public-layout',
  standalone: true,
  imports: [RouterOutlet, RouterLink, RouterLinkActive, RdTranslatePipe, CallPillComponent, QuietFooterComponent, SettingsButtonComponent, ScenarioSwitcherComponent],
  templateUrl: './public-layout.component.html',
  styleUrl: './public-layout.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class PublicLayoutComponent {
  private router = inject(Router);
  private settings = viewChild(SettingsButtonComponent);
  /** Chat screen is full-screen: no header or tab bar. */
  readonly chat = signal(this.router.url.startsWith('/report'));
  readonly demo = signal(typeof location !== 'undefined' && location.search.includes('demo=1'));

  constructor() {
    this.router.events
      .pipe(filter((e) => e instanceof NavigationEnd), takeUntilDestroyed(inject(DestroyRef)))
      .subscribe(() => {
        this.chat.set(this.router.url.startsWith('/report'));
        this.demo.set(this.router.url.includes('demo=1') || location.search.includes('demo=1'));
      });
  }

  openHelp(): void {
    this.settings()?.open();
  }
}
