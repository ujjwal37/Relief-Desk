import { ComponentFixture, TestBed } from '@angular/core/testing';
import { By } from '@angular/platform-browser';
import { provideRouter } from '@angular/router';
import { of } from 'rxjs';
import { ApiClientService, StoredRequest, StoredResource } from '@rd/shared';
import { MapProviderComponent } from '../../../core/maps/map-provider.component';
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
    expect(text).not.toContain('INC-9');
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

  it('measures distance to the nearest open case and caps it at 50 km', () => {
    const cmp = fixture.componentInstance;
    cmp.requests.set([
      { id: 'near', lat: 10.3, lng: 76.2, status: 'new' } as StoredRequest,
      { id: 'done', lat: 12, lng: 76.2, status: 'completed' } as StoredRequest,
    ]);
    fixture.detectChanges();
    expect(cmp.leg(rows[2])).toBe('1.11 km · about 3 min');
    expect(cmp.leg(rows[1])).toBe('50+ km');
    expect(cmp.leg(rows[1])).not.toContain('No nearby team');
    for (const team of rows) {
      const shown = Number((cmp.leg(team).match(/(\d+(?:\.\d+)?)/) || [])[1]);
      expect(shown).toBeLessThanOrEqual(50);
    }
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
    (buttons[3] as HTMLButtonElement).click();
    fixture.detectChanges();
    expect(fixture.nativeElement.textContent).toContain('INC-9');
  });
});
