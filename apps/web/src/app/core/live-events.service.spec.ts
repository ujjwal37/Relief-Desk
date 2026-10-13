import { TestBed } from '@angular/core/testing';
import { of } from 'rxjs';
import { ApiClientService } from '@rd/shared';
import { DeskStore } from './desk-store';
import { backoffMs, kindsFor, LiveEventsService } from './live-events.service';

describe('live event routing', () => {
  it('maps each event to the lists that should refresh', () => {
    expect(kindsFor('case.created')).toEqual(['cases', 'recent', 'alerts']);
    expect(kindsFor('case.merged')).toEqual(['cases', 'recent', 'alerts']);
    expect(kindsFor('case.updated')).toEqual(['cases', 'recent', 'alerts']);
    expect(kindsFor('dispatch.created')).toEqual(['cases', 'recent', 'alerts', 'teams']);
    expect(kindsFor('team.updated')).toEqual(['teams']);
    expect(kindsFor('alert.created')).toEqual(['alerts']);
    expect(kindsFor('heartbeat')).toEqual([]);
  });

  it('waits longer between reconnects, up to 15 seconds', () => {
    expect(backoffMs(0)).toBe(1000);
    expect(backoffMs(1)).toBe(2000);
    expect(backoffMs(2)).toBe(4000);
    expect(backoffMs(4)).toBe(15000);
    expect(backoffMs(8)).toBe(15000);
  });
});

describe('LiveEventsService', () => {
  let service: LiveEventsService;
  let desk: DeskStore;

  beforeEach(() => {
    const api = jasmine.createSpyObj('ApiClientService', ['getRequests', 'getResources', 'getAlerts', 'getRecentReports']);
    api.getRequests.and.returnValue(of([{ id: 'INC-1' }]));
    api.getResources.and.returnValue(of([{ id: 'boat' }]));
    api.getAlerts.and.returnValue(of([]));
    api.getRecentReports.and.returnValue(of([{ id: 'rep-1', case_id: 'INC-1' }]));
    TestBed.configureTestingModule({
      providers: [{ provide: ApiClientService, useValue: api }],
    });
    service = TestBed.inject(LiveEventsService);
    desk = TestBed.inject(DeskStore);
  });

  it('refreshes the case, recent, and alert stores when a case is created', () => {
    service.ingest({ type: 'case.created', request_id: 'INC-1' });
    expect(desk.requests().map((row) => row.id)).toEqual(['INC-1']);
    expect(desk.recent().map((row) => row.id)).toEqual(['rep-1']);
    expect(desk.alertsReady()).toBeTrue();
    expect(desk.teamsReady()).toBeFalse();
  });

  it('refreshes teams when a team moves or a dispatch is approved', () => {
    service.ingest({ type: 'team.updated', id: 'boat' });
    expect(desk.resources().map((row) => row.id)).toEqual(['boat']);
    service.ingest({ type: 'dispatch.created', request_id: 'INC-1' });
    expect(desk.teamsReady()).toBeTrue();
    expect(desk.casesReady()).toBeTrue();
  });
});
