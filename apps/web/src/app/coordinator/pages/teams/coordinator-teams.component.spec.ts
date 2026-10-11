import { ComponentFixture, TestBed } from '@angular/core/testing';
import { of } from 'rxjs';
import { ApiClientService, StoredResource } from '@rd/shared';
import { CoordinatorTeamsComponent } from './coordinator-teams.component';

describe('CoordinatorTeamsComponent', () => {
  let fixture: ComponentFixture<CoordinatorTeamsComponent>;
  const old = new Date(Date.now() - 40 * 60000).toISOString();
  const rows: StoredResource[] = [
    { id: 'b1', kind: 'boat', name: 'Boat One', ward_id: 'ward_7', lat: 1, lng: 2, capacity_total: 12, capacity_remaining: 4, status: 'available', location_updated_at: new Date().toISOString() },
    { id: 'm1', kind: 'medical', name: 'Medic One', ward_id: 'ward_2', lat: 1, lng: 2, capacity_total: 6, capacity_remaining: 0, status: 'depleted', location_updated_at: old, assigned_request_id: 'INC-9' },
  ];

  beforeEach(async () => {
    const api = jasmine.createSpyObj('ApiClientService', ['getResources', 'updateResourceLocation']);
    api.getResources.and.returnValue(of(rows));
    api.updateResourceLocation.and.returnValue(of({ ...rows[0], lat: 9.5, lng: 76.3, simulated: false }));
    await TestBed.configureTestingModule({
      imports: [CoordinatorTeamsComponent],
      providers: [{ provide: ApiClientService, useValue: api }],
    }).compileComponents();
    fixture = TestBed.createComponent(CoordinatorTeamsComponent);
    fixture.detectChanges();
  });

  it('lists every resource and filters by type', () => {
    const cmp = fixture.componentInstance;
    expect(cmp.filtered().length).toBe(2);
    expect(fixture.nativeElement.textContent).toContain('Boat One');
    expect(fixture.nativeElement.textContent).toContain('INC-9');
    cmp.typeFilter.set('boat');
    fixture.detectChanges();
    expect(cmp.filtered().map((t) => t.id)).toEqual(['b1']);
    expect(cmp.stale(rows[1])).toBeTrue();
    expect(cmp.stale(rows[0])).toBeFalse();
  });

  it('saves a manual location', () => {
    const form = fixture.nativeElement.querySelector('form.loc') as HTMLFormElement;
    const inputs = form.querySelectorAll('input');
    (inputs[0] as HTMLInputElement).value = '9.5';
    (inputs[1] as HTMLInputElement).value = '76.3';
    form.dispatchEvent(new Event('submit'));
    fixture.detectChanges();
    const api = TestBed.inject(ApiClientService) as jasmine.SpyObj<ApiClientService>;
    expect(api.updateResourceLocation).toHaveBeenCalledWith('b1', 9.5, 76.3);
    expect(fixture.componentInstance.notice()).toContain('saved');
  });
});
