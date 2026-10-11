import { ChangeDetectionStrategy, Component, OnInit, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ApiClientService, RdTranslatePipe } from '@rd/shared';

export interface MetricRow {
  key: string;
  label: string;
  relief: string;
  baseline: string;
  pct: boolean;
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
    this.reload();
  }

  reload(): void {
    this.error.set(null);
    this.api.getBenchmark().subscribe({
      next: (payload) => this.apply(payload),
      error: () => this.error.set('Could not load bench/results/latest.json'),
    });
  }

  /** Bar width: values up to 1 are fractions, otherwise already percentages. */
  pct(value: string): number {
    const n = parseFloat(value);
    if (Number.isNaN(n)) return 0;
    return Math.max(0, Math.min(100, n <= 1 ? n * 100 : n));
  }

  apply(payload: Record<string, unknown>): void {
    const metrics = (payload['metrics'] || {}) as Record<string, Record<string, unknown>>;
    const split = String(payload['split_desc'] || '');
    const seed = String(payload['seed'] ?? '');
    this.subtitle.set(`${split} · seed ${seed}`);
    this.rows.set(Object.entries(metrics).map(([key, value]) => ({
      key,
      label: this.pretty(key),
      relief: this.format(value['relief_desk']),
      baseline: this.format(this.baselineOf(value)),
      pct: /_pct$/.test(key),
    })));
    const examples = (payload['failure_examples'] || []) as Array<Record<string, unknown>>;
    this.failures.set(examples.map((item) => `${item['message_id']}: ${item['category']}`));
  }

  private pretty(key: string): string {
    const base = key.replace(/_(pct|ms|usd)$/, '').replace(/_/g, ' ').replace(/\bpm1\b/, '(±1)').replace(/\bf1\b/, 'F1').replace(/\bp(\d+)\b/, 'P$1').replace(/\btop(\d+)\b/, 'top $1');
    const unit = /_pct$/.test(key) ? ' (%)' : /_ms$/.test(key) ? ' (ms)' : /_usd$/.test(key) ? ' (USD)' : '';
    return base.charAt(0).toUpperCase() + base.slice(1) + unit;
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
    if (value == null) return '';
    const text = String(value);
    return text.startsWith('N/A') ? 'N/A' : text;
  }
}
