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
      {
        id: 'gap-medical',
        kind: 'resource_gap',
        title: 'Sample resource gap',
        reason: 'Sample. Medical demand 6, only 2 free',
        severity: 'high',
        age_label: '17 min ago',
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

  it('marks a spike with a small circle and keeps close place labels apart', () => {
    const cells = fixture.componentInstance.cells.filter((c) => ['ward_1', 'ward_2', 'ward_3'].includes(c.ward.id));
    for (let i = 0; i < cells.length; i++) {
      for (let j = i + 1; j < cells.length; j++) {
        const gap = Math.hypot(cells[i].lx - cells[j].lx, cells[i].ly - cells[j].ly);
        expect(gap).toBeGreaterThan(30);
      }
    }
    fixture.componentInstance.selectedId.set(null);
    fixture.detectChanges();
    expect(fixture.nativeElement.querySelectorAll('.wname .dist').length).toBe(0);
    fixture.componentInstance.selectedId.set('spike-ward-7');
    fixture.detectChanges();
    const mark = fixture.nativeElement.querySelector('circle.spike-mark') as SVGCircleElement;
    expect(mark).toBeTruthy();
    expect(Number(mark.getAttribute('r'))).toBe(28);
    expect(fixture.nativeElement.querySelector('polygon.ward.spike')).toBeNull();
  });

  it('badges the seeded resource gap as a sample and does not style it as live', () => {
    const card = fixture.nativeElement.querySelector('.alert-row.sample') as HTMLElement;
    expect(card).toBeTruthy();
    expect(card.querySelector('.sample-badge')?.textContent).toContain('Sample');
    expect(card.textContent).toContain('Sample: Resource gap');
    expect(card.classList.contains('k-resource_gap')).toBeTrue();
    const live = fixture.nativeElement.querySelector('.alert-row.k-spike') as HTMLElement;
    expect(live.classList.contains('sample')).toBeFalse();
  });

  it('labels a seeded resource gap as a sample', () => {
    const title = fixture.componentInstance.titleOf({
      id: 'gap-medical',
      kind: 'resource_gap',
      title: 'Sample resource gap',
      reason: 'Sample. Medical demand 6, only 2 free',
      severity: 'high',
      age_label: '17 min ago',
      acknowledged: false,
    });
    expect(title).toBe('Sample: Resource gap');
  });

  it('View on map focuses that ward, including the row that is already selected', () => {
    expect(fixture.componentInstance.selectedId()).toBe('spike-ward-7');
    const button = fixture.nativeElement.querySelector('button.secondary') as HTMLButtonElement;
    expect(button.textContent).toContain('View on map');
    button.click();
    fixture.detectChanges();
    expect(fixture.componentInstance.focusNonce()).toBe(1);
    expect(fixture.componentInstance.center().lat).toBeCloseTo(9.381, 3);
    expect(fixture.componentInstance.center().lng).toBeCloseTo(76.488, 3);
    const buttons = fixture.nativeElement.querySelectorAll('button.secondary');
    (buttons[1] as HTMLButtonElement).click();
    fixture.detectChanges();
    expect(fixture.componentInstance.selectedId()).toBe('silent-ward-5');
    expect(fixture.componentInstance.center().lat).toBeCloseTo(9.479, 3);
    expect(fixture.componentInstance.center().lng).toBeCloseTo(76.438, 3);
    expect(fixture.componentInstance.transform()).toContain('scale(1.35)');
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
