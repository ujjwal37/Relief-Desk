import { ComponentFixture, TestBed } from '@angular/core/testing';
import { of } from 'rxjs';
import { ApiClientService } from '@rd/shared';
import { MapProviderService } from '../../../core/maps/map-provider.service';
import { CitizenTrackComponent } from './citizen-track.component';

describe('CitizenTrackComponent', () => {
  let fixture: ComponentFixture<CitizenTrackComponent>;

  beforeEach(async () => {
    const api = jasmine.createSpyObj('ApiClientService', ['getCitizenTrack']);
    api.getCitizenTrack.and.returnValue(of({
      visible: true,
      state: 'dispatched',
      team_name: 'Motorized Rescue Boat',
      distance_km: 1.8,
      eta_minutes: 6,
      no_nearby: false,
      lat: 9.45,
      lng: 76.4,
      case_lat: 9.5,
      case_lng: 76.41,
      updated_at: new Date().toISOString(),
      simulated: true,
      stale: false,
      trail: [{ lat: 9.44, lng: 76.39 }],
    }));
    await TestBed.configureTestingModule({
      imports: [CitizenTrackComponent],
      providers: [
        { provide: ApiClientService, useValue: api },
        { provide: MapProviderService, useValue: { decide: () => Promise.resolve('svg'), authFailed: false } },
      ],
    }).compileComponents();
    fixture = TestBed.createComponent(CitizenTrackComponent);
    fixture.componentRef.setInput('reportId', 'R-0412');
    fixture.componentRef.setInput('token', 'tok_demo');
    fixture.detectChanges();
  });

  it('shows the assigned team distance and says the movement is simulated', () => {
    const text = fixture.nativeElement.textContent as string;
    expect(text).toContain('Motorized Rescue Boat is 1.8 km away, about 6 min');
    expect(text).toContain('Simulated movement');
    expect(fixture.nativeElement.querySelector('[data-testid="citizen-track"]')).toBeTruthy();
  });
});
