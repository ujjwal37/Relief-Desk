import { ChangeDetectionStrategy, Component, OnInit, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ApiClientService, LanguageService, RdTranslatePipe } from '@rd/shared';

export interface MetricRow {
  key: string;
  label: string;
  means: string;
  relief: string;
  baseline: string;
  baselineName: string;
  pct: boolean;
}

/** Strongest honest results first. Weaker scores stay on the page, lower down. */
const METRIC_ORDER = [
  'hoax_catch_rate_pct',
  'hoax_false_flag_rate_pct',
  'false_merge_rate_pct',
  'duplicate_precision_pct',
  'duplicate_f1_pct',
  'duplicate_recall_pct',
  'people_count_exact_pct',
  'people_count_pm1_pct',
  'vulnerable_flag_macro_f1_pct',
  'critical_case_top5_share_pct',
  'critical_case_top10_share_pct',
  'critical_case_mean_rank',
  'duplicate_vs_update_3way_accuracy_pct',
  'type_accuracy_pct',
  'place_ward_accuracy_pct',
  'latency_p50_ms',
  'latency_p95_ms',
  'cost_per_1000_msgs_usd',
];

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
  private lang = inject(LanguageService);

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
    this.subtitle.set(split ? `${split} · seed ${seed}` : '');
    const keys = [
      ...METRIC_ORDER.filter((key) => metrics[key]),
      ...Object.keys(metrics).filter((key) => !METRIC_ORDER.includes(key)),
    ];
    this.rows.set(keys.map((key) => {
      const value = metrics[key];
      const baseline = this.baselineOf(value);
      return {
        key,
        label: `bench.m.${key}`,
        means: `bench.mean.${key}`,
        relief: this.format(value['relief_desk']),
        baseline: this.format(baseline.value),
        baselineName: baseline.name,
        pct: /_pct$/.test(key),
      };
    }));
    const examples = (payload['failure_examples'] || []) as Array<Record<string, unknown>>;
    this.failures.set(examples.map((item) => `${item['message_id']}: ${item['category']}`));
  }

  private baselineOf(value: Record<string, unknown>): { value: unknown; name: string } {
    this.lang.currentLang();
    if (value['baseline_fcfs'] != null) return { value: value['baseline_fcfs'], name: 'bench.baseFcfs' };
    if (value['baseline_keyword'] != null) return { value: value['baseline_keyword'], name: 'bench.baseKeyword' };
    if (value['baseline_hash'] != null) return { value: value['baseline_hash'], name: 'bench.baseHash' };
    return { value: value['baseline'], name: 'bench.base' };
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
