import { ChangeDetectionStrategy, Component, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import {
  AuthService,
  DEMO_COORDINATOR_EMAIL,
  DEMO_COORDINATOR_PASSWORD,
  RdTranslatePipe,
  LanguageSwitcherComponent,
} from '@rd/shared';

@Component({
  selector: 'app-coordinator-login',
  standalone: true,
  imports: [FormsModule, RouterLink, RdTranslatePipe, LanguageSwitcherComponent],
  templateUrl: './coordinator-login.component.html',
  styleUrl: './coordinator-login.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class CoordinatorLoginComponent {
  private authService = inject(AuthService);
  private router = inject(Router);
  private route = inject(ActivatedRoute);

  email = signal(DEMO_COORDINATOR_EMAIL);
  password = signal(DEMO_COORDINATOR_PASSWORD);
  errorMessage = signal<string | null>(null);
  isSubmitting = signal(false);

  async onLogin(): Promise<void> {
    this.isSubmitting.set(true);
    this.errorMessage.set(null);

    const result = await this.authService.login(this.email(), this.password());
    this.isSubmitting.set(false);

    if (result.success) {
      const returnUrl = this.route.snapshot.queryParams['returnUrl'] || '/coordinator/command';
      this.router.navigateByUrl(returnUrl);
    } else {
      this.errorMessage.set(result.error || 'Invalid credentials');
    }
  }

  useDemoAccount(): void {
    this.email.set(DEMO_COORDINATOR_EMAIL);
    this.password.set(DEMO_COORDINATOR_PASSWORD);
    this.errorMessage.set(null);
    this.onLogin();
  }
}
