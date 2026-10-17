import { ComponentFixture, TestBed } from '@angular/core/testing';
import { of } from 'rxjs';
import { ApiClientService } from '@rd/shared';
import { CoordinatorBenchmarkComponent } from './coordinator-benchmark.component';

const FIXTURE = {
  split_desc: 'Test split (70% = 168 messages)',
  seed: 42,
  metrics: {
    duplicate_precision_pct: { relief_desk: 71.4, baseline_hash: 10.0, target: 'Beat hash clearly' },
    duplicate_recall_pct: { relief_desk: 11.1, baseline_hash: 4.4, target: 'Beat hash clearly' },
    false_merge_rate_pct: { relief_desk: 0.0, baseline_hash: 0.0, target: 'As low as possible' },
    critical_case_mean_rank: { relief_desk: 10.5, baseline_fcfs: 13.5, target: 'Lower is better' },
    cost_per_1000_msgs_usd: { relief_desk: '$0.0467', baseline: 'N/A', target: 'Reported' },
  },
  failure_examples: [],
  gemini: {
    measured: false,
    reason: 'no_api_key',
    model: 'gemini-3.8-flash',
    date: '2026-10-12',
    n: 168,
    type_accuracy_pct: null,
    place_ward_accuracy_pct: null,
    baseline_type_accuracy_pct: 16.3,
    baseline_ward_accuracy_pct: 13.3,
  },
};

describe('CoordinatorBenchmarkComponent', () => {
  let fixture: ComponentFixture<CoordinatorBenchmarkComponent>;

  beforeEach(async () => {
    const api = jasmine.createSpyObj('ApiClientService', ['getBenchmark', 'getMeasuredCost']);
    api.getMeasuredCost.and.returnValue(of({ measured: false, reports: 0, tokens: 0, tokens_per_report: null, inr_per_report: null, inr_per_1000_reports: null }));
    api.getBenchmark.and.returnValue(of(FIXTURE));
    await TestBed.configureTestingModule({
      imports: [CoordinatorBenchmarkComponent],
      providers: [{ provide: ApiClientService, useValue: api }],
    }).compileComponents();
    fixture = TestBed.createComponent(CoordinatorBenchmarkComponent);
    fixture.detectChanges();
  });

  it('prints the JSON numbers and the synthetic-data line', () => {
    const text = fixture.nativeElement.textContent as string;
    expect(text).toContain('Synthetic reports, our own labels');
    expect(text).toContain('71.4');
    expect(text).toContain('0.0');
    const cmp = fixture.componentInstance;
    expect(cmp.rows().find((row) => row.key === 'duplicate_recall_pct')?.relief).toBe('11.1');
    expect(cmp.rows().find((row) => row.key === 'critical_case_mean_rank')?.relief).toBe('10.5');
    // Cost is only shown when Gemini was actually measured; this fixture has measured: false.
    expect(cmp.rows().find((row) => row.key === 'cost_per_1000_msgs_usd')).toBeUndefined();
    expect(cmp.subtitle()).toContain('seed 42');
    expect(cmp.gemini()).toEqual(jasmine.objectContaining({ model: 'gemini-3.8-flash', measured: false, n: '168', baseType: '16.3' }));
    expect(text).not.toContain('Example data');
  });
});
