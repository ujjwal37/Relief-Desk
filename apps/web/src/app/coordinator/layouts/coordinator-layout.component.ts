import { ChangeDetectionStrategy, Component, inject } from '@angular/core';
import { Router, RouterLink, RouterOutlet } from '@angular/router';
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
export class CoordinatorLayoutComponent {
  readonly authService = inject(AuthService);
  private router = inject(Router);

  logout(): void {
    this.authService.logout();
    this.router.navigate(['/coordinator/login']);
  }
}
