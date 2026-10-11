import { ChangeDetectionStrategy, Component, OnInit, inject, signal } from '@angular/core';
import { Router, RouterLink } from '@angular/router';
import { ApiClientService, AuthService, LanguageService, RdTranslatePipe } from '@rd/shared';
import { MyRequestsService, SavedRequest } from '../../../core/services/my-requests.service';
import { OfflineSyncService } from '../../../core/services/offline-sync.service';

interface Row { req: SavedRequest; state: 'loading' | 'ok' | 'err'; headline: string; eta: string; code: string; }

@Component({
  selector: 'app-home',
  standalone: true,
  imports: [RouterLink, RdTranslatePipe],
  templateUrl: './home.component.html',
  styleUrl: './home.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class HomeComponent implements OnInit {
  private api = inject(ApiClientService);
  private lang = inject(LanguageService);
  readonly store = inject(MyRequestsService);
  private auth = inject(AuthService);
  private router = inject(Router);
  readonly rows = signal<Row[]>([]);
  readonly demoMode = signal(false);
  readonly offline = inject(OfflineSyncService);

  async enterDemo(): Promise<void> {
    if (await this.auth.loginDemo()) await this.router.navigateByUrl('/coordinator/command');
  }

  ngOnInit(): void {
    (this.api as Partial<ApiClientService>).getHealth?.()?.subscribe({ next: (h) => this.demoMode.set(!!h?.demo_mode), error: () => this.demoMode.set(false) });
    const saved = this.store.list().slice(0, 3);
    this.rows.set(saved.map((req) => ({ req, state: 'loading', headline: '', eta: '', code: '' })));
    saved.forEach((req) => {
      const call = (this.api as Partial<ApiClientService>).getReportStatus?.(req.id, req.token || undefined);
      call?.subscribe({
        next: (s) => this.patch(req.id, {
          state: 'ok',
          headline: this.lang.translate(s.hero_title),
          eta: s.eta_display,
          code: s.public_code || '',
        }),
        error: () => this.patch(req.id, { state: 'err' }),
      });
    });
  }

  private patch(id: string, p: Partial<Row>): void {
    this.rows.update((rows) => rows.map((r) => (r.req.id === id ? { ...r, ...p } : r)));
  }

  remove(id: string): void {
    this.store.remove(id);
    this.rows.update((rows) => rows.filter((r) => r.req.id !== id));
  }
}

