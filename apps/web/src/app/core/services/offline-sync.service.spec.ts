import { TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import { OfflineSyncService } from './offline-sync.service';
import { ApiClientService, ReportSubmitRequest, ReportSubmitResponse } from '@rd/shared';
import { of } from 'rxjs';

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

  it('should generate prefilled SMS link with compact text for 112 emergency', () => {
    const smsLink = service.getPrefilledSmsLink('Stranded on roof with 2 children');
    expect(smsLink).toContain('sms:112?body=');
    expect(decodeURIComponent(smsLink)).toContain('RELIEF DESK: Stranded on roof with 2 children');
  });
});
