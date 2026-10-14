import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter, Router } from '@angular/router';
import { signal } from '@angular/core';
import { of } from 'rxjs';
import { ApiClientService, LanguageService, ReportSubmitResponse, canonicalRequestJson } from '@rd/shared';
import { OfflineSyncService, SyncedReport } from '../../../core/services/offline-sync.service';
import { ReportComponent } from './report.component';

describe('ReportComponent confirmation gate', () => {
  let fixture: ComponentFixture<ReportComponent>;
  let api: jasmine.SpyObj<ApiClientService>;
  const online = signal(true);
  const lastSynced = signal<SyncedReport | null>(null);

  beforeEach(async () => {
    api = jasmine.createSpyObj('ApiClientService', ['sendChatTurn', 'submitReport', 'getScenario', 'getScenarios']);
    api.getScenarios.and.returnValue(of([
      { id: 'flood', title: 'Urban Flood Relief', description: '', incident_types: ['rescue'], tiles: [], follow_up_questions: {}, urgency_rules: {}, resource_types: [], safety_line_ids: ['call_112'] },
    ]));
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
    api.getScenario.and.returnValue(of({
      id: 'flood',
      title: 'Urban Flood Relief',
      description: 'Flood',
      incident_types: ['rescue', 'medical', 'food', 'shelter'],
      tiles: [
        { id: 'trapped_water', label_en: 'Trapped in Water', label_hi: 'पानी में फंसे हैं', incident_type: 'rescue', icon: 'water' },
        { id: 'medical_urgent', label_en: 'Medical Assistance', label_hi: 'चिकित्सा सहायता', incident_type: 'medical', icon: 'medkit' },
      ],
      follow_up_questions: {},
      urgency_rules: {},
      resource_types: ['boat'],
      safety_line_ids: ['call_112'],
    }));

    await TestBed.configureTestingModule({
      imports: [ReportComponent],
      providers: [
        provideRouter([]),
        { provide: ApiClientService, useValue: api },
        {
          provide: OfflineSyncService,
          useValue: {
            isOnline: online,
            pendingCount: signal(0),
            lastSynced,
            readOnline: () => online(),
            getPrefilledSmsLink: () => 'sms:112',
            saveReportOffline: () => ({ idempotency_key: 'k' }),
          },
        },
      ],
    }).compileComponents();

    online.set(true);
    lastSynced.set(null);
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

  it('keeps entered data when switching chat and form, and the Request JSON matches', () => {
    const card = {
      incident_type: 'rescue',
      place_text: 'Ward 7 · Gandhi School',
      people_count: 5,
      vulnerable: { child: true, elderly: true, disabled: false, pregnant: false, medical_need: false },
      hazard: 'water_rising',
      summary: '5 people needing rescue at Ward 7 · Gandhi School',
      ready_to_submit: true,
    };
    fixture.componentInstance.pendingCard.set(card);
    fixture.componentInstance.locationPin.set({ lat: 26.852, lng: 80.925 });
    const chatJson = fixture.componentInstance.requestJson(card);
    fixture.componentInstance.openForm();
    fixture.detectChanges();
    const formCard = fixture.componentInstance.pendingCard();
    expect(formCard?.people_count).toBe(5);
    expect(formCard?.place_text).toContain('Gandhi School');
    expect(fixture.componentInstance.requestJson(formCard!)).toBe(chatJson);
    expect(chatJson).toBe(canonicalRequestJson({
      card,
      lang: 'en',
      locationPin: { lat: 26.852, lng: 80.925 },
      scenarioId: 'flood',
    }));
    expect(fixture.nativeElement.textContent).toContain('Trapped in Water');
  });

  it('opens status after an offline report is replayed', () => {
    const navigate = spyOn(TestBed.inject(Router), 'navigate');
    online.set(false);
    const card = {
      incident_type: 'rescue' as const,
      place_text: 'Nedumudi Boat Jetty',
      people_count: 2,
      vulnerable: { child: false, elderly: false, disabled: false, pregnant: false, medical_need: false },
      hazard: 'water_rising' as const,
      summary: '2 people',
      ready_to_submit: true,
    };
    fixture.componentInstance.confirmAndSubmit(card);
    expect(navigate).not.toHaveBeenCalled();
    const response: ReportSubmitResponse = {
      report_id: 'rep_offline',
      request_id: 'req_offline',
      status_token: 'tok_offline',
      summary: 'ok',
      urgency_score: 10,
      dedupe_decision: 'new',
      flags: [],
      safety_line: 'Call 112',
    };
    lastSynced.set({ client_id: 'cli_k', response });
    fixture.detectChanges();
    expect(navigate).toHaveBeenCalledWith(['/status'], {
      queryParams: { id: 'rep_offline', token: 'tok_offline', new: 1 },
    });
  });

  it('follows Hindi for labels, example chips, and the mic locale', () => {
    const lang = TestBed.inject(LanguageService);
    lang.setLanguage('hi');
    fixture.detectChanges();
    const box = fixture.nativeElement.querySelector('textarea') as HTMLTextAreaElement;
    expect(box.lang).toBe('hi-IN');
    expect(box.placeholder).toBe('बताइए क्या हुआ');
    expect(fixture.nativeElement.textContent).toContain('बाढ़ या पानी बढ़ रहा है');
    expect(fixture.componentInstance.inputLocale()).toBe('hi-IN');
    expect(fixture.componentInstance.sampleUtterance()).toContain('4 लोग');

    (fixture.nativeElement.querySelector('.rd-set-btn') as HTMLButtonElement).click();
    fixture.detectChanges();
    const sheet = fixture.nativeElement.querySelector('.rd-sheet') as HTMLElement;
    expect(sheet.textContent).toContain('EN');
    expect(sheet.textContent).toContain('हिंदी');
    expect(sheet.querySelector('[aria-label="Hinglish"]')).toBeNull();
    (sheet.querySelector('[data-testid="lang-more"]') as HTMLButtonElement).click();
    fixture.detectChanges();
    expect(sheet.querySelector('[aria-label="Hinglish"]')).toBeTruthy();
    expect(sheet.querySelector('[aria-label="Malayalam"]')).toBeTruthy();

    fixture.componentInstance.openForm();
    fixture.detectChanges();
    const form = fixture.nativeElement.textContent as string;
    expect(form).toContain('स्थान / लैंडमार्क');
    expect(form).toContain('प्रभावित व्यक्तियों की संख्या');
    expect(form).toContain('पानी में फंसे हैं');

    lang.setLanguage('en');
    fixture.componentInstance.mode.set('chat');
    fixture.detectChanges();
    expect(fixture.componentInstance.inputLocale()).toBe('en-IN');
    expect((fixture.nativeElement.querySelector('textarea') as HTMLTextAreaElement).lang).toBe('en-IN');
    expect(fixture.componentInstance.sampleUtterance()).toContain('Ward 7');
  });

  it('fast path stays at chip then Send now, with no login control', () => {
    expect(fixture.nativeElement.querySelector('input[type="password"]')).toBeNull();
    const chip = fixture.nativeElement.querySelector('.chip') as HTMLButtonElement;
    expect(chip.getBoundingClientRect).toBeTruthy();
    chip.click();
    fixture.detectChanges();
    expect(api.submitReport).not.toHaveBeenCalled();
    const send = fixture.nativeElement.querySelector('.send-now') as HTMLButtonElement;
    send.click();
    expect(api.submitReport).toHaveBeenCalledTimes(1);
  });
});
