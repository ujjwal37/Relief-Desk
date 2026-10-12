import { ComponentFixture, TestBed } from '@angular/core/testing';
import { of } from 'rxjs';
import { ApiClientService } from '@rd/shared';
import { MapProviderService } from '../../../core/maps/map-provider.service';
import { LiveMapComponent } from './live-map.component';

describe('LiveMapComponent', () => {
  let fixture: ComponentFixture<LiveMapComponent>;

  beforeEach(async () => {
    const api = jasmine.createSpyObj('ApiClientService', ['getTeamLocations', 'getRequests', 'overrideTeamStatus']);
    api.getTeamLocations.and.returnValue(of({
      teams: [{
        id: 'RES-BOAT-01',
        name: 'Motorized Rescue Boat',
        kind: 'boat',
        status: 'dispatched',
        lat: 9.5,
        lng: 76.4,
        stale: true,
        simulated: true,
        source: 'simulated',
        assigned_request_id: 'req_live',
        case_lat: 9.55,
        case_lng: 76.42,
        distance_km: 1.8,
        eta_minutes: 6,
        no_nearby: false,
        trail: [{ lat: 9.48, lng: 76.39 }, { lat: 9.5, lng: 76.4 }],
        check_in: true,
        busy_minutes: 12,
        soon_free: false,
        share_token: 'tm_demo',
      }],
    }));
    api.getRequests.and.returnValue(of([
      { id: 'req_live', status: 'dispatched', lat: 9.55, lng: 76.42, type: 'rescue' },
    ]));
    await TestBed.configureTestingModule({
      imports: [LiveMapComponent],
      providers: [
        { provide: ApiClientService, useValue: api },
        { provide: MapProviderService, useValue: { decide: () => Promise.resolve('svg'), authFailed: false } },
      ],
    }).compileComponents();
    fixture = TestBed.createComponent(LiveMapComponent);
    fixture.detectChanges();
  });

  it('lists live status, a stale check-in, and simulated movement', () => {
    const text = fixture.nativeElement.textContent as string;
    expect(text).toContain('Live map');
    expect(text).toContain('Motorized Rescue Boat');
    expect(text).toContain('Stale');
    expect(text).toContain('Check in');
    expect(text).toContain('Simulated movement');
    expect(text).toContain('Busy for 12 min');
    fixture.componentInstance.selectTeam('RES-BOAT-01');
    expect(fixture.componentInstance.selectedCaseId()).toBe('req_live');
  });
});
