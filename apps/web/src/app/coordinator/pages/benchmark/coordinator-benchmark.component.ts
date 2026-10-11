import { ChangeDetectionStrategy, Component, OnInit, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ApiClientService, RdTranslatePipe } from '@rd/shared';

export interface MetricRow {
  key: string;
  label: string;
  relief: string;
  baseline: string;
}

@Component({
  selector: 'app-coordinator-benchmark',
  standalone: true,
  imports: [CommonModule, RdTranslatePipe],
  templateUrl: './coordinator-benchmark.component.html',
  styleUrl: './coordinator-benchmark.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class CoordinatorBenchmarkComponent implements OnInit {
  private api = inject(ApiClientService);

  readonly rows = signal<MetricRow[]>([]);
  readonly subtitle = signal('');
  readonly failures = signal<string[]>([]);
  readonly error = signal<string | null>(null);

  ngOnInit(): void {
    this.api.getBenchmark().subscribe({
      next: (payload) => this.apply(payload),
      error: () => this.error.set('Could not load bench/results/latest.json'),
    });
  }

  apply(payload: Record<string, unknown>): void {
    const metrics = (payload['metrics'] || {}) as Record<string, Record<string, unknown>>;
    const split = String(payload['split_desc'] || '');
    const seed = String(payload['seed'] ?? '');
    this.subtitle.set(`${split} · seed ${seed}`);
    this.rows.set(Object.entries(metrics).map(([key, value]) => ({
      key,
      label: key.replace(/_/g, ' '),
      relief: this.format(value['relief_desk']),
      baseline: this.format(this.baselineOf(value)),
    })));
    const examples = (payload['failure_examples'] || []) as Array<Record<string, unknown>>;
    this.failures.set(examples.map((item) => `${item['message_id']}: ${item['category']}`));
  }

  private baselineOf(value: Record<string, unknown>): unknown {
    return value['baseline_hash']
      ?? value['baseline_fcfs']
      ?? value['baseline_keyword']
      ?? value['baseline'];
  }

  private format(value: unknown): string {
    if (typeof value === 'number') {
      return value.toFixed(1);
    }
    return value == null ? '' : String(value);
  }
}
