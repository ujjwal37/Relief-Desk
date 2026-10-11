import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { of } from 'rxjs';
import { ApiClientService, LanguageService } from '@rd/shared';
import { OfflineSyncService } from '../../../core/services/offline-sync.service';
import { ReportComponent } from './report.component';

describe('ReportComponent confirmation gate', () => {
  let fixture: ComponentFixture<ReportComponent>;
  let api: jasmine.SpyObj<ApiClientService>;

  beforeEach(async () => {
    api = jasmine.createSpyObj('ApiClientService', ['sendChatTurn', 'submitReport']);
    api.sendChatTurn.and.returnValue(of({
      session_id: 's',
      bot_message: 'Please check the card.',
      turn_count: 1,
      missing_fields: [],
      confirmation_card: {
        incident_type: 'rescue',
        place_text: 'Ward 7 · Gandhi School',
        people_count: 5,
        vulnerable: { child: true, elderly: false, disabled: false, pregnant: false, medical_need: false },
        hazard: 'water_rising',
        summary: '5 people needing rescue at Ward 7 · Gandhi School',
        ready_to_submit: true,
      },
    }));
    api.submitReport.and.returnValue(of({
      report_id: 'rpt_1',
      request_id: 'req_1',
      status_token: 'tok_1',
      summary: 'ok',
      urgency_score: 10,
      dedupe_decision: 'new',
      flags: [],
      safety_line: 'Call 112',
    }));

    await TestBed.configureTestingModule({
      imports: [ReportComponent],
      providers: [
        provideRouter([]),
        { provide: ApiClientService, useValue: api },
        {
          provide: OfflineSyncService,
          useValue: {
            isOnline: () => true,
            pendingCount: () => 0,
            getPrefilledSmsLink: () => 'sms:112',
            saveReportOffline: () => ({ idempotency_key: 'k' }),
          },
        },
      ],
    }).compileComponents();

    fixture = TestBed.createComponent(ReportComponent);
    TestBed.inject(LanguageService).setLanguage('en');
    fixture.detectChanges();
  });

  it('does not call submitReport until the shared card Send now is tapped', () => {
    fixture.componentInstance.setQuickChip('Gandhi school ke paas 5 log');
    fixture.detectChanges();
    expect(api.sendChatTurn).toHaveBeenCalled();
    expect(api.submitReport).not.toHaveBeenCalled();
    expect(fixture.nativeElement.querySelector('rd-confirmation-card')).toBeTruthy();

    fixture.nativeElement.querySelector('.send-now').click();
    expect(api.submitReport).toHaveBeenCalledTimes(1);
    const payload = api.submitReport.calls.mostRecent().args[0];
    expect(payload.structured?.people_count).toBe(5);
    expect(payload.structured?.incident_type).toBe('rescue');
  });

  it('form mode uses the same card and still waits for Send now', () => {
    fixture.componentInstance.toggleMode();
    fixture.detectChanges();
    expect(fixture.nativeElement.querySelector('rd-confirmation-card')).toBeTruthy();
    expect(api.submitReport).not.toHaveBeenCalled();
    fixture.nativeElement.querySelector('.send-now').click();
    expect(api.submitReport).toHaveBeenCalledTimes(1);
  });
});
