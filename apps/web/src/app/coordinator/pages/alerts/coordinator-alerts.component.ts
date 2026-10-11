import { ChangeDetectionStrategy, Component, OnInit, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { AnomalyAlert, ApiClientService, RdTranslatePipe } from '@rd/shared';

@Component({
  selector: 'app-coordinator-alerts',
  standalone: true,
  imports: [CommonModule, RdTranslatePipe],
  templateUrl: './coordinator-alerts.component.html',
  styleUrl: './coordinator-alerts.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class CoordinatorAlertsComponent implements OnInit {
  private api = inject(ApiClientService);

  readonly alerts = signal<AnomalyAlert[]>([]);
  readonly selectedId = signal<string | null>(null);
  readonly error = signal<string | null>(null);

  ngOnInit(): void {
    this.reload();
  }

  reload(): void {
    this.error.set(null);
    this.api.getAlerts().subscribe({
      next: (rows) => {
        this.alerts.set(rows);
        if (rows.length) {
          this.selectedId.set(rows[0].id);
        }
      },
      error: () => this.error.set('Could not load alerts.'),
    });
  }

  select(alert: AnomalyAlert): void {
    this.selectedId.set(alert.id);
  }

  acknowledge(alert: AnomalyAlert): void {
    this.api.acknowledgeAlert(alert.id).subscribe({
      next: (updated) => {
        this.alerts.update((rows) => rows.map((row) => (row.id === updated.id ? updated : row)));
      },
    });
  }
}
