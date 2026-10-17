import { ComponentFixture, TestBed } from '@angular/core/testing';
import { By } from '@angular/platform-browser';
import { provideRouter, Router } from '@angular/router';
import { of } from 'rxjs';
import { ApiClientService, LanguageService, MatchProposal, StoredRequest, StoredResource } from '@rd/shared';
import { MapProviderComponent } from '../../../core/maps/map-provider.component';
import { CoordUiService } from '../../../core/services/coord-ui.service';
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
    const api = jasmine.createSpyObj('ApiClientService', ['getRequests', 'getResources', 'getAlerts', 'getRequestMatches', 'getRecentReports']);
    api.getRequests.and.returnValue(of(cases));
    api.getRecentReports.and.returnValue(of([]));
    api.getResources.and.returnValue(of(teams));
    api.getAlerts.and.returnValue(of([]));
    api.getRequestMatches.and.returnValue(of([]));
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
    const map = fixture.nativeElement.querySelector('rd-map-provider') as HTMLElement;
    const alerts = fixture.nativeElement.querySelector('app-coordinator-alerts') as HTMLElement;
    expect(getComputedStyle(map).top).toBe('56px');
    expect(parseFloat(getComputedStyle(alerts).width)).toBeGreaterThan(300);
    expect(getComputedStyle(fixture.nativeElement.querySelector('.alerts-page.list-only')).overflowY).toBe('auto');
    expect(map.compareDocumentPosition(alerts) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(fixture.nativeElement.querySelector('.map-stage svg:not(.rd-schematic)')).toBeNull();
    expect(provider().pins.map((pin) => pin.id).sort()).toEqual(['boat', 'med', 'now', 'soon']);
    expect(provider().fitAll).toBeTrue();
    const legend = () => (fixture.nativeElement.querySelector('.map-stage .legend') as HTMLElement).textContent || '';
    expect(legend()).toContain('Needs help now');
    expect(legend()).toContain('Help soon');
    expect(legend()).toContain('Boat');
    expect(legend()).toContain('Ambulance / medical');
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
    expect(legend()).not.toContain('Ambulance / medical');
    expect(provider().pins.find((pin) => pin.id === 'boat')?.vehicle).toBe('boat');
    expect(provider().pins.find((pin) => pin.id === 'now')?.tone).toBe('critical');
  });

  it('opens a just-reported case in the queue', () => {
    const router = TestBed.inject(Router);
    spyOn(router, 'navigate').and.resolveTo(true);
    component.openReported('now');
    expect(TestBed.inject(CoordUiService).selectedCaseId()).toBe('now');
    // The overview focuses the case on its own map now; it no longer jumps to Command.
    expect(component.focusId()).toBe('now');
  });

  it('fits the open case and its top teams when a case is selected', () => {
    const api = TestBed.inject(ApiClientService) as jasmine.SpyObj<ApiClientService>;
    api.getRequestMatches.and.returnValue(of([{
      match_id: 'm',
      request_id: 'now',
      resource_id: 'boat',
      resource_name: 'Boat',
      resource_kind: 'boat',
      resource_ward: 'ward_1',
      capacity_total: 6,
      capacity_remaining: 4,
      score: 80,
      breakdown: { distance_km: 1.2, distance_score: 1, capacity_fit_score: 1, urgency_score: 1, vulnerability_fit_score: 1, total_score: 80 },
      state: 'proposed',
      eta_minutes: 4,
      overcommit_warning: false,
    } as MatchProposal]));
    component.focusCase('now');
    fixture.detectChanges();
    const provider = fixture.debugElement.query(By.css('rd-map-provider')).componentInstance as MapProviderComponent;
    expect(provider.fitAll).toBeFalse();
    expect(provider.legs.map((leg) => leg.title)).toEqual(['1.2 km · about 4 min']);
    expect(provider.legs[0].suggested).toBeTrue();
    expect(component.mapLegs().length).toBe(1);
  });
});
