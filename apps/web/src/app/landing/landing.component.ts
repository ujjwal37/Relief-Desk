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

  async openDemo(event?: Event, live = false): Promise<void> {
    event?.preventDefault();
    if (await this.auth.loginDemo()) {
      await this.router.navigateByUrl(live ? '/coordinator/command?live=1' : '/coordinator/command');
    }
  }
}
