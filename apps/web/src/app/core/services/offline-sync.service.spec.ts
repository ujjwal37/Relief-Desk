import { TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import { OfflineSyncService } from './offline-sync.service';
import { ApiClientService, ReportSubmitRequest, ReportSubmitResponse } from '@rd/shared';
import { of, throwError } from 'rxjs';

describe('OfflineSyncService (T-028 Offline + SMS Fallback)', () => {
  let service: OfflineSyncService;
  let apiClient: ApiClientService;

  beforeEach(() => {
    localStorage.clear();
    TestBed.configureTestingModule({
      providers: [OfflineSyncService, ApiClientService, provideHttpClient()],
    });
    service = TestBed.inject(OfflineSyncService);
    apiClient = TestBed.inject(ApiClientService);
  });

  afterEach(() => {
    localStorage.clear();
  });

  it('should save report to offline queue with unique idempotency key', () => {
    const payload: ReportSubmitRequest = {
      text: 'Stranded in flood near Gandhi School, 4 people',
      channel: 'text',
      lang: 'en',
    };

    const saved = service.saveReportOffline(payload);
    expect(saved.idempotency_key).toContain('idem_');
    expect(service.pendingCount()).toBe(1);

    const pending = service.getPendingReports();
    expect(pending.length).toBe(1);
    expect(pending[0].payload.text).toBe(payload.text);
  });

  it('should auto-retry and drain pending queue upon reconnection once only', () => {
    const payload: ReportSubmitRequest = {
      text: 'Offline test rescue',
      channel: 'text',
      lang: 'hi',
    };
    service.saveReportOffline(payload);
    expect(service.pendingCount()).toBe(1);

    const mockResponse: ReportSubmitResponse = {
      report_id: 'rep_123',
      request_id: 'req_123',
      status_token: 'ST-998877',
      summary: 'Test summary',
      urgency_score: 10,
      dedupe_decision: 'new',
      flags: [],
      safety_line: 'Call 112',
    };

    spyOn(apiClient, 'submitReport').and.returnValue(of(mockResponse));

    service.syncPendingReports();

    expect(apiClient.submitReport).toHaveBeenCalledTimes(1);
    expect(service.pendingCount()).toBe(0);
    expect(service.lastSyncedToken()).toBe('ST-998877');
  });

  it('keeps one queued report and retries the same idempotency key', () => {
    const saved = service.saveReportOffline({
      text: 'Ward 7 Temple Road, bachcha stranded',
      channel: 'text',
      lang: 'hinglish',
    });
    const again = service.saveReportOffline({
      ...saved.payload,
      idempotency_key: saved.idempotency_key,
    });
    expect(again.client_id).toBe(saved.client_id);
    expect(service.pendingCount()).toBe(1);

    const submit = spyOn(apiClient, 'submitReport').and.returnValue(throwError(() => new Error('offline')));
    service.syncPendingReports();
    expect(service.pendingCount()).toBe(1);
    expect(service.getPendingReports()[0].attempts).toBe(1);
    expect(submit.calls.mostRecent().args[0].idempotency_key).toBe(saved.idempotency_key);

    submit.and.returnValue(of({
      report_id: 'rep_once',
      request_id: 'req_once',
      status_token: 'tok_once',
      summary: 'ok',
      urgency_score: 80,
      dedupe_decision: 'new',
      flags: [],
      safety_line: 'Call 112',
    }));
    service.syncPendingReports();
    expect(service.pendingCount()).toBe(0);
    expect(submit).toHaveBeenCalledTimes(2);
    const keys = submit.calls.allArgs().map((args) => args[0].idempotency_key);
    expect(keys).toEqual([saved.idempotency_key, saved.idempotency_key]);
    expect(localStorage.getItem('rd_last_report_id')).toBe('rep_once');
  });

  it('should generate prefilled SMS link with compact text for 112 emergency', () => {
    const smsLink = service.getPrefilledSmsLink('Stranded on roof with 2 children');
    expect(smsLink).toContain('sms:112?body=');
    expect(decodeURIComponent(smsLink)).toContain('RELIEF DESK: Stranded on roof with 2 children');
  });
});
