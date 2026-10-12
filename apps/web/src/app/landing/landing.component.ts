import { ChangeDetectionStrategy, Component, inject } from '@angular/core';
import { Router, RouterLink } from '@angular/router';
import {
  AuthService, RdTranslatePipe, SettingsButtonComponent, CallPillComponent, QuietFooterComponent,
} from '@rd/shared';

@Component({
  selector: 'app-landing',
  standalone: true,
  imports: [RouterLink, RdTranslatePipe, SettingsButtonComponent, CallPillComponent, QuietFooterComponent],
  templateUrl: './landing.component.html',
  styleUrl: './landing.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class LandingComponent {
  private auth = inject(AuthService);
  private router = inject(Router);

  constructor() {
    if (window.matchMedia('(max-width: 599px)').matches) {
      void this.router.navigateByUrl('/report');
    }
  }

  async openDemo(event?: Event): Promise<void> {
    event?.preventDefault();
    if (await this.auth.loginDemo()) {
      await this.router.navigateByUrl('/coordinator/command');
    }
  }
}
