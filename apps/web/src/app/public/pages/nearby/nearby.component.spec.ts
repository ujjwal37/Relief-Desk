import { ComponentFixture, TestBed } from '@angular/core/testing';
import { of } from 'rxjs';
import { NearbyComponent } from './nearby.component';
import { ApiClientService, PublicCellsResponse, PublicAlert } from '@rd/shared';

describe('NearbyComponent', () => {
  let component: NearbyComponent;
  let fixture: ComponentFixture<NearbyComponent>;
  let apiSpy: jasmine.SpyObj<ApiClientService>;

  const mockCellsResponse: PublicCellsResponse = {
    cells: [
      {
        cell_id: 'cell_w7',
        ward: 'Ward 7 · Riverside',
        center_lat: 26.852,
        center_lng: 80.931,
        incident_counts: { rescue: 6, food: 4 },
        total_reports: 10,
        severity_band: 'critical',
        time_bucket: 'Last 2 hours',
        active_hazard: 'Water rising',
        alerts: ['Canal Road closed'],
        last_updated: '2026-10-11T12:00:00Z',
      },
      {
        cell_id: 'cell_w4',
        ward: 'Ward 4 · North Ghat',
        center_lat: 26.861,
        center_lng: 80.942,
        incident_counts: { rescue: 3 },
        total_reports: 3,
        severity_band: 'high',
        time_bucket: 'Last 2 hours',
        active_hazard: 'Waterlogging',
        alerts: [],
        last_updated: '2026-10-11T12:00:00Z',
      },
    ],
    total_active_cells: 2,
    disclaimer: 'Area-level only. No exact addresses.',
    synthetic: true,
  };

  const mockAlerts: PublicAlert[] = [
    {
      id: 'alt_01',
      title: 'Dog attack alert · Ward 9, Mill Colony',
      ward: 'Ward 9',
      time_ago: '25 min ago',
      severity: 'warning',
      description: '3 reports in 2 h. Avoid walking alone near colony lanes.',
      icon: 'dog',
    },
    {
      id: 'alt_02',
      title: 'Flooded lanes · Ward 7 and Ward 4',
      ward: 'Ward 7 & 4',
      time_ago: '1 h ago',
      severity: 'critical',
      description: 'Canal Road closed.',
      icon: 'flood',
    },
  ];

  beforeEach(async () => {
    apiSpy = jasmine.createSpyObj('ApiClientService', ['getPublicCells', 'getPublicAlerts']);
    apiSpy.getPublicCells.and.returnValue(of(mockCellsResponse));
    apiSpy.getPublicAlerts.and.returnValue(of(mockAlerts));

    await TestBed.configureTestingModule({
      imports: [NearbyComponent],
      providers: [{ provide: ApiClientService, useValue: apiSpy }],
    }).compileComponents();

    fixture = TestBed.createComponent(NearbyComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  it('should create and load area cells and alerts', () => {
    expect(component).toBeTruthy();
    expect(component.cells().length).toBe(2);
    expect(component.alerts().length).toBe(2);
    expect(component.selectedCell()?.ward).toBe('Ward 7 · Riverside');
  });

  it('should allow selecting a cell on map interaction', () => {
    component.selectCell(mockCellsResponse.cells[1]);
    expect(component.selectedCell()?.cell_id).toBe('cell_w4');
    expect(component.selectedCell()?.severity_band).toBe('high');
  });
});
