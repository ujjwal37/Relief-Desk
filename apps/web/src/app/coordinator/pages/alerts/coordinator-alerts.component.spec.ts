import { ComponentFixture, TestBed } from '@angular/core/testing';
import { of } from 'rxjs';
import { ApiClientService } from '@rd/shared';
import { MapProviderService } from '../../../core/maps/map-provider.service';
import { CoordinatorAlertsComponent } from './coordinator-alerts.component';

describe('CoordinatorAlertsComponent', () => {
  let fixture: ComponentFixture<CoordinatorAlertsComponent>;

  beforeEach(async () => {
    const api = jasmine.createSpyObj('ApiClientService', ['getAlerts', 'acknowledgeAlert']);
    api.getAlerts.and.returnValue(of([
      {
        id: 'spike-ward-7',
        kind: 'spike',
        title: 'Report spike',
        reason: 'Ward 7: 14 reports in 20 min (baseline 3)',
        ward_id: 'ward_7',
        severity: 'critical',
        age_label: '4 min ago',
        acknowledged: false,
      },
      {
        id: 'silent-ward-5',
        kind: 'silent_zone',
        title: 'Silent zone',
        reason: 'Ward 5: 0 reports in 3 h, neighbours rising. Possible outage.',
        ward_id: 'ward_5',
        severity: 'high',
        age_label: '11 min ago',
        acknowledged: false,
      },
    ]));
    api.acknowledgeAlert.and.returnValue(of({
      id: 'spike-ward-7',
      kind: 'spike',
      title: 'Report spike',
      reason: 'Ward 7: 14 reports in 20 min (baseline 3)',
      ward_id: 'ward_7',
      severity: 'critical',
      age_label: '4 min ago',
      acknowledged: true,
    }));

    await TestBed.configureTestingModule({
      imports: [CoordinatorAlertsComponent],
      providers: [{ provide: ApiClientService, useValue: api }, { provide: MapProviderService, useValue: { decide: () => Promise.resolve('svg'), authFailed: false } }],
    }).compileComponents();

    fixture = TestBed.createComponent(CoordinatorAlertsComponent);
    fixture.detectChanges();
  });

  it('shows the seeded spike and silent zone with their reasons', () => {
    const text = fixture.nativeElement.textContent as string;
    expect(text).toContain('Report spike');
    expect(text).toContain('14 reports in 20 min');
    expect(text).toContain('Silent zone');
    expect(text).toContain('0 reports in 3 h');
    expect(text).toContain('Nothing is deleted');
  });
});
