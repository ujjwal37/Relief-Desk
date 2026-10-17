import { ComponentFixture, TestBed } from '@angular/core/testing';
import { By } from '@angular/platform-browser';
import { provideRouter } from '@angular/router';
import { of } from 'rxjs';
import { ApiClientService, MatchProposal, StoredRequest, StoredResource } from '@rd/shared';
import { MapProviderComponent } from '../../../core/maps/map-provider.component';
import { CoordUiService } from '../../../core/services/coord-ui.service';
import { CoordinatorTeamsComponent } from './coordinator-teams.component';

describe('CoordinatorTeamsComponent', () => {
  let fixture: ComponentFixture<CoordinatorTeamsComponent>;
  const old = new Date(Date.now() - 40 * 60000).toISOString();
  const late = new Date(Date.now() - 130 * 60000).toISOString();
  const fresh = new Date().toISOString();
  const rows: StoredResource[] = [
    { id: 'm1', kind: 'medical', name: 'Medic One', ward_id: 'ward_2', lat: 10.3, lng: 76.2, capacity_total: 6, capacity_remaining: 0, status: 'depleted', location_updated_at: old, assigned_request_id: 'INC-9' },
    { id: 'd1', kind: 'food', name: 'Kitchen', ward_id: 'ward_4', lat: 12, lng: 76.2, capacity_total: 40, capacity_remaining: 10, status: 'dispatched', location_updated_at: fresh },
    { id: 'b1', kind: 'boat', name: 'Boat One', ward_id: 'ward_7', lat: 10.31, lng: 76.2, capacity_total: 12, capacity_remaining: 4, status: 'available', location_updated_at: fresh, location_trail: [{ lat: 10.3, lng: 76.2, at: '2026-10-12T10:00:00Z' }] },
    { id: 's1', kind: 'shelter', name: 'Hall', ward_id: 'ward_1', lat: 10.2, lng: 76.2, capacity_total: 20, capacity_remaining: 20, status: 'available', location_updated_at: late },
  ];

  beforeEach(async () => {
    const api = jasmine.createSpyObj('ApiClientService', ['getResources', 'getRequests', 'getRequestMatches', 'updateResourceLocation']);
    api.getResources.and.returnValue(of(rows));
    api.getRequests.and.returnValue(of([]));
    api.getRequestMatches.and.returnValue(of([]));
    api.updateResourceLocation.and.returnValue(of({ ...rows[2], lat: 9.5, lng: 76.3, simulated: false }));
    await TestBed.configureTestingModule({
      imports: [CoordinatorTeamsComponent],
      providers: [{ provide: ApiClientService, useValue: api }, provideRouter([])],
    }).compileComponents();
    fixture = TestBed.createComponent(CoordinatorTeamsComponent);
    fixture.detectChanges();
  });

  it('puts free teams first and hides details until the row is opened', () => {
    const cmp = fixture.componentInstance;
    expect(cmp.filtered().map((team) => team.id)).toEqual(['b1', 's1', 'd1', 'm1']);
    expect(cmp.counts()).toEqual({ free: 1, busy: 2, notUpdated: 1 });
    const total = cmp.counts();
    expect(total.free + total.busy + total.notUpdated).toBe(rows.length);
    expect(cmp.bucket(rows[3])).toBe('notUpdated');
    expect(cmp.bucket(rows[0])).toBe('busy');
    expect(cmp.bucket({ ...rows[0], location_updated_at: late })).toBe('busy');
    expect(cmp.bucket({ ...rows[2], location_updated_at: '' })).toBe('notUpdated');
    expect(cmp.checkInLate({ ...rows[2], location_updated_at: new Date(Date.now() - 120 * 60000).toISOString() })).toBeFalse();
    const text = fixture.nativeElement.textContent as string;
    expect(text).toContain('Free 1');
    expect(text).toContain('Busy 2');
    expect(text).toContain('Not updated 1');
    expect(text).not.toContain('Stale');
    const provider = fixture.debugElement.query(By.css('rd-map-provider')).componentInstance as MapProviderComponent;
    expect(provider.fitAll).toBeTrue();
    expect(provider.pins.map((pin) => pin.id).sort()).toEqual(['b1', 'd1', 'm1', 's1']);
    expect(text).toContain('Chalakudy');
    expect(text).toContain('On INC-9');
    expect(fixture.nativeElement.querySelector('form.loc')).toBeNull();
    expect(cmp.checkInLate(rows[0])).toBeFalse();
    expect(cmp.checkInLate(rows[3])).toBeTrue();
    const stale = fixture.nativeElement.querySelectorAll('time.stale');
    expect(stale.length).toBe(1);
  });

  it('filters from the summary chips', () => {
    const cmp = fixture.componentInstance;
    cmp.setStrip('free');
    expect(cmp.filtered().map((team) => team.id)).toEqual(['b1']);
    cmp.setStrip('free');
    expect(cmp.strip()).toBe('all');
    cmp.setStrip('busy');
    expect(cmp.filtered().map((team) => team.id)).toEqual(['d1', 'm1']);
    cmp.setStrip('notUpdated');
    expect(cmp.filtered().map((team) => team.id)).toEqual(['s1']);
  });

  it('shows Best for RD-xxxx label on teams rows for the nearest open case', () => {
    const cmp = fixture.componentInstance;
    cmp.requests.set([
      { id: 'near', public_code: 'RD-2135', lat: 10.3, lng: 76.2, status: 'new' } as StoredRequest,
      { id: 'done', lat: 12, lng: 76.2, status: 'completed' } as StoredRequest,
    ]);
    fixture.detectChanges();
    expect(cmp.leg(rows[2])).toBe('Best for RD-2135');
  });

  it('draws the top three legs for the selected case and highlights the hovered row', () => {
    const cmp = fixture.componentInstance;
    const api = TestBed.inject(ApiClientService) as jasmine.SpyObj<ApiClientService>;
    api.getRequestMatches.and.returnValue(of([{
      match_id: 'm',
      request_id: 'near',
      resource_id: 'b1',
      resource_name: 'Boat One',
      resource_kind: 'boat',
      resource_ward: 'ward_7',
      capacity_total: 12,
      capacity_remaining: 4,
      score: 90,
      breakdown: { distance_km: 1.2, distance_score: 1, capacity_fit_score: 1, urgency_score: 1, vulnerability_fit_score: 1, total_score: 90 },
      state: 'proposed',
      eta_minutes: 4,
      overcommit_warning: false,
    } as MatchProposal]));
    cmp.requests.set([{ id: 'near', lat: 10.3, lng: 76.2, status: 'new', urgency_score: 90 } as StoredRequest]);
    TestBed.inject(CoordUiService).selectedCaseId.set('near');
    fixture.detectChanges();
    expect(cmp.teamLegs().map((leg) => leg.title)).toEqual(['1.2 km · about 4 min']);
    expect(cmp.teamLegs()[0].suggested).toBeTrue();
    expect(cmp.leg(rows[2])).toBe('1.2 km · about 4 min');
    const provider = fixture.debugElement.query(By.css('rd-map-provider')).componentInstance as MapProviderComponent;
    expect(provider.fitAll).toBeFalse();
    expect(provider.legs.map((leg) => leg.title)).toEqual(['1.2 km · about 4 min']);
    expect(provider.pins.find((pin) => pin.id === 'b1')?.vehicle).toBe('boat');
    expect(provider.pins.find((pin) => pin.id === 'b1')?.tone).toBe('free');
    expect(provider.pins.find((pin) => pin.id === 'near')?.tone).toBe('critical');
    const legend = (fixture.nativeElement.querySelector('.legend') as HTMLElement).textContent || '';
    expect(legend).toContain('Boat');
    expect(legend).toContain('Ambulance / medical');
    (fixture.nativeElement.querySelector('button.row') as HTMLButtonElement).dispatchEvent(new Event('mouseenter'));
    fixture.detectChanges();
    expect(provider.highlightId).toBe('b1');
  });

  it('frames every team on the map provider', () => {
    const cmp = fixture.componentInstance;
    const provider = fixture.debugElement.query(By.css('rd-map-provider')).componentInstance as MapProviderComponent;
    expect(provider.fitAll).toBeTrue();
    expect(provider.pins.length).toBe(rows.length);
    expect(cmp.teamPins().map((pin) => pin.lat)).toContain(12);
    expect(fixture.nativeElement.querySelector('.team-map > svg')).toBeNull();
  });

  it('opens seats, history, and the location action', () => {
    const buttons = fixture.nativeElement.querySelectorAll('button.row');
    (buttons[0] as HTMLButtonElement).click();
    fixture.detectChanges();
    const text = fixture.nativeElement.textContent as string;
    expect(text).toContain('4 of 12 seats free');
    expect(text).toContain('2026-10-12T10:00:00Z');
    expect(text).toContain('On INC-9');
    const form = fixture.nativeElement.querySelector('form.loc') as HTMLFormElement;
    const inputs = form.querySelectorAll('input');
    (inputs[0] as HTMLInputElement).value = '9.5';
    (inputs[1] as HTMLInputElement).value = '76.3';
    form.dispatchEvent(new Event('submit'));
    fixture.detectChanges();
    const api = TestBed.inject(ApiClientService) as jasmine.SpyObj<ApiClientService>;
    expect(api.updateResourceLocation).toHaveBeenCalledWith('b1', 9.5, 76.3);
    expect(fixture.componentInstance.notice()).toContain('saved');
    (buttons[3] as HTMLButtonElement).click();
    fixture.detectChanges();
    expect(fixture.nativeElement.textContent).toContain('INC-9');
  });
});
