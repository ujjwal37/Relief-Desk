import { TestBed } from '@angular/core/testing';
import { MyRequestsService } from './my-requests.service';

describe('MyRequestsService', () => {
  beforeEach(() => {
    localStorage.removeItem('rd_my_requests');
    localStorage.removeItem('rd_last_report_id');
    localStorage.removeItem('rd_last_status_token');
  });

  it('saves, dedupes and removes requests on the device', () => {
    const s = TestBed.inject(MyRequestsService);
    expect(s.latest()).toBeUndefined();
    s.add('R-1', 't1', 'rescue');
    s.add('R-2', 't2');
    s.add('R-1', 't1b');
    expect(s.list()[0].kind).toBe('rescue');
    expect(s.list().map((r) => r.id)).toEqual(['R-1', 'R-2']);
    expect(localStorage.getItem('rd_last_report_id')).toBe('R-1');
    s.remove('R-1');
    expect(s.latest()?.id).toBe('R-2');
  });
});
