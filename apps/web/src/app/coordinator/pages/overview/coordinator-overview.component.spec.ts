import { ComponentFixture, TestBed } from '@angular/core/testing';
import { By } from '@angular/platform-browser';
import { provideRouter } from '@angular/router';
import { of } from 'rxjs';
import { ApiClientService, LanguageService, StoredRequest, StoredResource } from '@rd/shared';
import { MapProviderComponent } from '../../../core/maps/map-provider.component';
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
    const provider = () => fixture.debugElement.query(By.css('rd-map-provider')).componentInstance as MapProviderComponent;
    expect(component.mapPins().map((pin) => pin.id).sort()).toEqual(['boat', 'med', 'now', 'soon']);
    expect(fixture.nativeElement.querySelectorAll('rd-map-provider').length).toBe(1);
    expect(fixture.nativeElement.querySelector('.omap')).toBeNull();
    expect(fixture.nativeElement.querySelector('.map-stage svg:not(.rd-schematic)')).toBeNull();
    expect(provider().pins.map((pin) => pin.id).sort()).toEqual(['boat', 'med', 'now', 'soon']);
    expect(provider().fitAll).toBeTrue();
    const legend = () => (fixture.nativeElement.querySelector('.map-stage .legend') as HTMLElement).textContent || '';
    expect(legend()).toContain('Needs help now');
    expect(legend()).toContain('Help soon');
    expect(legend()).toContain('Boat');
    expect(legend()).toContain('Medical');
    expect(legend()).not.toContain('Shelter');

    component.urgency.set('critical');
    fixture.detectChanges();
    expect(component.mapPins().map((pin) => pin.id).sort()).toEqual(['boat', 'med', 'now']);
    expect(provider().pins.map((pin) => pin.id).sort()).toEqual(['boat', 'med', 'now']);
    expect(legend()).toContain('Needs help now');
    expect(legend()).not.toContain('Help soon');

    component.teamKind.set('boat');
    component.freeOnly.set(true);
    fixture.detectChanges();
    expect(component.mapPins().map((pin) => pin.id).sort()).toEqual(['boat', 'now']);
    expect(provider().pins.map((pin) => pin.id).sort()).toEqual(['boat', 'now']);
    expect(legend()).toContain('Boat');
    expect(legend()).not.toContain('Medical');
  });
});
