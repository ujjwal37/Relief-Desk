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
};

describe('CoordinatorBenchmarkComponent', () => {
  let fixture: ComponentFixture<CoordinatorBenchmarkComponent>;

  beforeEach(async () => {
    const api = jasmine.createSpyObj('ApiClientService', ['getBenchmark']);
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
    expect(text).toContain('11.1');
    expect(text).toContain('10.5');
    expect(text).toContain('0.0');
    expect(text).toContain('$0.0467');
    expect(text).toContain('seed 42');
  });
});
