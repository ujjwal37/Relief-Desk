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
  const fresh = new Date().toISOString();
  const rows: StoredResource[] = [
    { id: 'm1', kind: 'medical', name: 'Medic One', ward_id: 'ward_2', lat: 10.3, lng: 76.2, capacity_total: 6, capacity_remaining: 0, status: 'depleted', location_updated_at: old, assigned_request_id: 'INC-9' },
    { id: 'd1', kind: 'food', name: 'Kitchen', ward_id: 'ward_4', lat: 12, lng: 76.2, capacity_total: 40, capacity_remaining: 10, status: 'dispatched', location_updated_at: fresh },
    { id: 'b1', kind: 'boat', name: 'Boat One', ward_id: 'ward_7', lat: 10.31, lng: 76.2, capacity_total: 12, capacity_remaining: 4, status: 'available', location_updated_at: fresh, location_trail: [{ lat: 10.3, lng: 76.2, at: '2026-10-12T10:00:00Z' }] },
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
    TestBed.inject(CoordUiService).selectedCaseId.set('');
    fixture = TestBed.createComponent(CoordinatorTeamsComponent);
    fixture.detectChanges();
  });

  it('puts free teams first and hides details until the row is opened', () => {
    const cmp = fixture.componentInstance;
    expect(cmp.filtered().map((team) => team.id)).toEqual(['b1', 'd1', 'm1']);
    expect(cmp.counts()).toEqual({ free: 1, busy: 2 });
    const text = fixture.nativeElement.textContent as string;
    expect(text).toContain('Free 1');
    expect(text).toContain('Busy 2');
    expect(text).not.toContain('Stale');
    expect(fixture.nativeElement.querySelector('.team-map')).toBeNull();
    expect(text).toContain('Chalakudy');
    expect(text).not.toContain('INC-9');
    expect(fixture.nativeElement.querySelector('form.loc')).toBeNull();
    expect(cmp.stale(rows[0])).toBeTrue();
    expect(cmp.stale(rows[2])).toBeFalse();
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
  });

  it('quotes the same distance style as the case card when a case is open', () => {
    const cmp = fixture.componentInstance;
    TestBed.inject(CoordUiService).selectedCaseId.set('INC-1');
    cmp.requests.set([{ id: 'INC-1', lat: 10.3, lng: 76.2 } as StoredRequest]);
    fixture.detectChanges();
    expect(cmp.leg(rows[2])).toBe('1.11 km · about 3 min');
    expect(cmp.leg(rows[1])).toContain('km');
    expect(cmp.leg(rows[1])).toContain('min');
    expect(cmp.leg(rows[1])).not.toContain('No nearby team');
  });

  it('draws a line from the open case to each candidate team', () => {
    const cmp = fixture.componentInstance;
    TestBed.inject(CoordUiService).selectedCaseId.set('INC-1');
    cmp.requests.set([{ id: 'INC-1', lat: 10.3, lng: 76.2 } as StoredRequest]);
    cmp.matches.set([{
      match_id: 'm',
      request_id: 'INC-1',
      resource_id: 'b1',
      resource_name: 'Boat One',
      resource_kind: 'boat',
      resource_ward: 'ward_7',
      capacity_total: 12,
      capacity_remaining: 4,
      score: 80,
      breakdown: { distance_km: 1.11, distance_score: 20, capacity_fit_score: 20, urgency_score: 20, vulnerability_fit_score: 10 },
      state: 'proposed',
      overcommit_warning: false,
      eta_minutes: 3,
    } as MatchProposal]);
    fixture.detectChanges();
    expect(cmp.teamPins().map((pin) => pin.id).sort()).toEqual(['INC-1', 'b1', 'd1', 'm1']);
    const lats = cmp.teamPins().map((pin) => pin.lat);
    expect(Math.max(...lats)).toBe(12);
    expect(Math.min(...lats)).toBe(10.3);
    const legs = cmp.teamLegs();
    expect(legs.length).toBe(1);
    expect(legs[0].suggested).toBeTrue();
    expect(legs[0].title).toContain('1.11 km · about 3 min');
    expect(legs[0].from).toEqual({ lat: 10.3, lng: 76.2 });
    expect(legs[0].to.lat).toBe(10.31);
    const provider = fixture.debugElement.query(By.css('rd-map-provider')).componentInstance as MapProviderComponent;
    expect(provider.pins.length).toBe(4);
    expect(provider.legs.length).toBe(1);
    expect(provider.legs[0].suggested).toBeTrue();
    expect(provider.fitAll).toBeTrue();
    expect(provider.focusToken).toBe(cmp.focusToken());
    expect(fixture.nativeElement.querySelector('.team-map > svg')).toBeNull();
    fixture.detectChanges();
    const line = fixture.nativeElement.querySelector('rd-map-provider .rd-schematic line') as SVGLineElement | null;
    expect(line).not.toBeNull();
    expect(line?.getAttribute('stroke')).toBe('#0b6e4f');
  });

  it('opens seats, history, and the location action', () => {
    const buttons = fixture.nativeElement.querySelectorAll('button.row');
    (buttons[0] as HTMLButtonElement).click();
    fixture.detectChanges();
    const text = fixture.nativeElement.textContent as string;
    expect(text).toContain('4 of 12 seats free');
    expect(text).toContain('2026-10-12T10:00:00Z');
    expect(text).not.toContain('INC-9');
    const form = fixture.nativeElement.querySelector('form.loc') as HTMLFormElement;
    const inputs = form.querySelectorAll('input');
    (inputs[0] as HTMLInputElement).value = '9.5';
    (inputs[1] as HTMLInputElement).value = '76.3';
    form.dispatchEvent(new Event('submit'));
    fixture.detectChanges();
    const api = TestBed.inject(ApiClientService) as jasmine.SpyObj<ApiClientService>;
    expect(api.updateResourceLocation).toHaveBeenCalledWith('b1', 9.5, 76.3);
    expect(fixture.componentInstance.notice()).toContain('saved');
    (buttons[2] as HTMLButtonElement).click();
    fixture.detectChanges();
    expect(fixture.nativeElement.textContent).toContain('INC-9');
  });
});
