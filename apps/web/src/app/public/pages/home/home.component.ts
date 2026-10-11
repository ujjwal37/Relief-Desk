import { ChangeDetectionStrategy, Component, OnInit, inject, signal } from '@angular/core';
import { RouterLink } from '@angular/router';
import { ApiClientService, RdTranslatePipe } from '@rd/shared';
import { MyRequestsService, SavedRequest } from '../../../core/services/my-requests.service';

interface Row { req: SavedRequest; state: 'loading' | 'ok' | 'err'; headline: string; eta: string; }

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
  readonly store = inject(MyRequestsService);
  readonly rows = signal<Row[]>([]);

  ngOnInit(): void {
    const saved = this.store.list().slice(0, 3);
    this.rows.set(saved.map((req) => ({ req, state: 'loading', headline: '', eta: '' })));
    saved.forEach((req) => {
      const call = (this.api as Partial<ApiClientService>).getReportStatus?.(req.id, req.token || undefined);
      call?.subscribe({
        next: (s) => this.patch(req.id, { state: 'ok', headline: s.hero_title, eta: s.eta_display }),
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
