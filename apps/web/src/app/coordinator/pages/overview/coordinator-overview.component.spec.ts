import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { of } from 'rxjs';
import { ApiClientService, LanguageService, StoredRequest, StoredResource } from '@rd/shared';
import { CoordinatorOverviewComponent } from './coordinator-overview.component';

describe('CoordinatorOverviewComponent map filters', () => {
  let fixture: ComponentFixture<CoordinatorOverviewComponent>;
  let component: CoordinatorOverviewComponent;

  const cases: StoredRequest[] = [
    { id: 'now', status: 'new', lat: 9.5, lng: 76.3, urgency_score: 90 } as StoredRequest,
    { id: 'soon', status: 'new', lat: 10.2, lng: 76.4, urgency_score: 72 } as StoredRequest,
    { id: 'done', status: 'completed', lat: 11.5, lng: 76.1, urgency_score: 90 } as StoredRequest,
  ];
  const teams: StoredResource[] = [
    { id: 'boat', kind: 'boat', name: 'Boat', lat: 9.52, lng: 76.32, status: 'available', capacity_remaining: 4, capacity_total: 6, ward_id: 'ward_1' },
    { id: 'med', kind: 'medical', name: 'Medic', lat: 10.1, lng: 76.5, status: 'dispatched', capacity_remaining: 0, capacity_total: 2, ward_id: 'ward_2' },
  ];

  beforeEach(async () => {
    const api = jasmine.createSpyObj('ApiClientService', ['getRequests', 'getResources', 'getAlerts']);
    api.getRequests.and.returnValue(of(cases));
    api.getResources.and.returnValue(of(teams));
    api.getAlerts.and.returnValue(of([]));
    await TestBed.configureTestingModule({
      imports: [CoordinatorOverviewComponent],
      providers: [provideRouter([]), { provide: ApiClientService, useValue: api }],
    }).compileComponents();
    TestBed.inject(LanguageService).setLanguage('en');
    fixture = TestBed.createComponent(CoordinatorOverviewComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  it('filters by urgency, team type, and free teams, and lists only visible kinds', () => {
    expect(component.pins().map((pin) => pin.id).sort()).toEqual(['boat', 'med', 'now', 'soon']);
    const legend = () => (fixture.nativeElement.querySelector('.omap .legend') as HTMLElement).textContent || '';
    expect(legend()).toContain('Needs help now');
    expect(legend()).toContain('Help soon');
    expect(legend()).toContain('Boat');
    expect(legend()).toContain('Medical');
    expect(legend()).not.toContain('Shelter');

    component.urgency.set('critical');
    fixture.detectChanges();
    expect(component.pins().filter((pin) => pin.kind === 'req').map((pin) => pin.id)).toEqual(['now']);
    expect(legend()).toContain('Needs help now');
    expect(legend()).not.toContain('Help soon');

    component.teamKind.set('boat');
    component.freeOnly.set(true);
    fixture.detectChanges();
    expect(component.pins().filter((pin) => pin.kind === 'team').map((pin) => pin.id)).toEqual(['boat']);
    expect(legend()).toContain('Boat');
    expect(legend()).not.toContain('Medical');
  });
});
