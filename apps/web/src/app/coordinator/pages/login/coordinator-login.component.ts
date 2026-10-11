import { ChangeDetectionStrategy, Component, ElementRef, inject, signal, viewChild } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import {
  ApiClientService, AuthService, RdTranslatePipe, SettingsButtonComponent, CallPillComponent, QuietFooterComponent,
} from '@rd/shared';

@Component({
  selector: 'app-coordinator-login',
  standalone: true,
  imports: [FormsModule, RouterLink, RdTranslatePipe, SettingsButtonComponent, CallPillComponent, QuietFooterComponent],
  templateUrl: './coordinator-login.component.html',
  styleUrl: './coordinator-login.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class CoordinatorLoginComponent {
  private authService = inject(AuthService);
  private router = inject(Router);
  private route = inject(ActivatedRoute);
  private api = inject(ApiClientService);
  /** Demo entry is shown only when the backend reports DEMO_MODE (GET /healthz demo_mode). */
  demoMode = signal(false);

  constructor() {
    const call = (this.api as Partial<ApiClientService>).getHealth?.();
    call?.subscribe({ next: (h) => this.demoMode.set(!!h?.demo_mode), error: () => this.demoMode.set(false) });
  }

  email = signal('');
  password = signal('');
  showPassword = signal(false);
  submitted = signal(false);
  failed = signal(false);
  isSubmitting = signal(false);
  toast = signal(false);
  private pwd = viewChild<ElementRef<HTMLInputElement>>('pwd');

  get emailMissing(): boolean { return this.submitted() && !this.email().trim(); }
  get passwordMissing(): boolean { return this.submitted() && !this.password(); }

  async onLogin(): Promise<void> {
    this.submitted.set(true);
    this.failed.set(false);
    if (!this.email().trim() || !this.password()) return;
    this.isSubmitting.set(true);
    const result = await this.authService.login(this.email(), this.password());
    this.isSubmitting.set(false);
    if (result.success) {
      await this.goToDashboard();
    } else {
      this.failed.set(true);
    }
  }

  async enterDemo(): Promise<void> {
    this.isSubmitting.set(true);
    const ok = await this.authService.loginDemo();
    this.isSubmitting.set(false);
    if (ok) await this.goToDashboard();
  }

  forgot(event: Event): void {
    event.preventDefault();
    this.toast.set(true);
    setTimeout(() => this.toast.set(false), 5000);
  }

  private goToDashboard(): Promise<boolean> {
    const returnUrl = this.route.snapshot.queryParams['returnUrl'] || '/coordinator/command';
    return this.router.navigateByUrl(returnUrl);
  }
}
