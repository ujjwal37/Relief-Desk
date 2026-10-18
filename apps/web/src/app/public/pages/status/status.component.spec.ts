import { ComponentFixture, TestBed } from '@angular/core/testing';
import { of } from 'rxjs';
import { ActivatedRoute } from '@angular/router';
import { StatusComponent } from './status.component';
import {
  ApiClientService,
  ReportStatusResponse,
  LanguageService,
  resetKuttanadDemoPointIndex,
  KUTTANAD_DEMO_POINTS,
} from '@rd/shared';

describe('StatusComponent', () => {
  let component: StatusComponent;
  let fixture: ComponentFixture<StatusComponent>;
  let apiSpy: jasmine.SpyObj<ApiClientService>;
  let langService: LanguageService;

  const mockStatus: ReportStatusResponse = {
    report_id: 'R-0412',
    request_id: 'REQ-0412',
    status: 'on_the_way',
    hero_title: 'Sent. Help is being arranged.',
    hero_subtitle: 'Request R-0412 · 11:42 · you can close the app',
    eta_minutes: 18,
    eta_display: '~18 min',
    delivery_status: 'In progress',
    timeline: [
      {
        step: 1,
        name: 'received',
        title: 'Received / प्राप्त',
        state: 'done',
        timestamp: '11:42',
        description: 'Request R-0412 saved',
      },
      {
        step: 2,
        name: 'matched',
        title: 'Matched / मिलान हुआ',
        state: 'done',
        timestamp: '11:44',
        description: 'Volunteer boat team assigned',
      },
      {
        step: 3,
        name: 'on_the_way',
        title: 'On the way / सहायता रवाना',
        state: 'current',
        timestamp: '11:48',
        description: 'Boat B-03 · from Ward 6 jetty',
      },
      {
        step: 4,
        name: 'fulfilled',
        title: 'Fulfilled / सहायता पहुँची',
        state: 'pending',
        timestamp: null,
        description: 'You can confirm when help arrives',
      },
    ],
    while_you_wait_tips: [
      'Move to the highest safe place.',
      'Stay away from flood water and live wires.',
      'Keep your phone charged and stay reachable.',
    ],
    emergency_phone: '112',
    synthetic: true,
  };

  beforeEach(async () => {
    resetKuttanadDemoPointIndex();
    apiSpy = jasmine.createSpyObj('ApiClientService', ['getReportStatus', 'updateReportLocation']);
    apiSpy.getReportStatus.and.returnValue(of(mockStatus));
    apiSpy.updateReportLocation.and.returnValue(of({ status: 'ok', report_id: 'R-0412', lat: 9.47185, lng: 76.39571 }));

    await TestBed.configureTestingModule({
      imports: [StatusComponent],
      providers: [
        { provide: ApiClientService, useValue: apiSpy },
        {
          provide: ActivatedRoute,
          useValue: {
            snapshot: { queryParams: { id: 'R-0412', token: 'tok_demo' } },
          },
        },
      ],
    }).compileComponents();

    langService = TestBed.inject(LanguageService);
    langService.setLanguage('en');
    fixture = TestBed.createComponent(StatusComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  afterEach(() => {
    langService.setLanguage('en');
    fixture.destroy();
  });

  it('keeps watching until the request is finished', () => {
    expect(component.stillWaiting('new')).toBeTrue();
    expect(component.stillWaiting('dispatched')).toBeTrue();
    expect(component.stillWaiting('completed')).toBeFalse();
    expect(component.stillWaiting('resolved')).toBeFalse();
  });

  it('should create and load initial status', () => {
    expect(component).toBeTruthy();
    expect(component.statusData()?.report_id).toBe('R-0412');
    expect(component.statusData()?.eta_display).toBe('~18 min');
  });

  it('should render 4 timeline steps matching mockup', () => {
    const timeline = component.statusData()?.timeline;
    expect(timeline?.length).toBe(4);
    expect(timeline?.[0].state).toBe('done');
    expect(timeline?.[2].state).toBe('current');
  });

  it('should trigger fetchStatus on track submit', () => {
    component.reportIdInput.set('REQ-999');
    component.tokenInput.set('tok-999');
    component.onTrackSubmit();
    expect(apiSpy.getReportStatus).toHaveBeenCalledWith('REQ-999', 'tok-999');
  });

  it('renders receipt card when receipt is present', () => {
    component.statusData.set({
      ...mockStatus,
      receipt: 'Received RD-1234. I understood: 2 people, water rising. Place: not stated.',
      place_stated: false,
    });
    fixture.detectChanges();
    const receipt = fixture.nativeElement.querySelector('[data-testid="status-receipt"]');
    expect(receipt).toBeTruthy();
    expect(receipt.textContent).toContain('Received RD-1234');
    expect(receipt.textContent).toContain('Place: not stated');
  });

  it('picks fixed Kuttanad demo points round-robin without calling navigator.geolocation', () => {
    resetKuttanadDemoPointIndex();
    component.statusData.set({
      ...mockStatus,
      receipt: 'Received RD-1234. Place: not stated.',
      place_stated: false,
    });
    fixture.detectChanges();

    let geoCalled = false;
    if (typeof navigator !== 'undefined' && navigator.geolocation) {
      spyOn(navigator.geolocation, 'getCurrentPosition').and.callFake(() => {
        geoCalled = true;
      });
    }

    const shareBtn = fixture.nativeElement.querySelector('[data-testid="receipt-share-location"]') as HTMLButtonElement;
    expect(shareBtn).toBeTruthy();

    // First tap: Kainakary jetty
    shareBtn.click();
    fixture.detectChanges();

    expect(geoCalled).toBeFalse();
    expect(apiSpy.updateReportLocation).toHaveBeenCalledWith(
      'R-0412',
      'tok_demo',
      KUTTANAD_DEMO_POINTS[0].lat,
      KUTTANAD_DEMO_POINTS[0].lng,
      25,
      'demo_pin'
    );
    expect(component.locationUpdated()).toBeTrue();
    expect(component.isDemoLocation()).toBeTrue();

    // Second pick round-robin: Nedumudi
    component.locationUpdating.set(false);
    component.shareLocation('R-0412');
    expect(apiSpy.updateReportLocation).toHaveBeenCalledWith(
      'R-0412',
      'tok_demo',
      KUTTANAD_DEMO_POINTS[1].lat,
      KUTTANAD_DEMO_POINTS[1].lng,
      25,
      'demo_pin'
    );
  });

  it('shows demo location note with proper i18n in en, hi, hinglish, and ml', () => {
    component.statusData.set({
      ...mockStatus,
      receipt: 'Received RD-1234. Place: not stated.',
      place_stated: true,
      demo_location: true,
      location_source: 'demo_pin',
    });
    component.demoLocationUsed.set(true);

    // English
    langService.setLanguage('en');
    fixture.detectChanges();
    let note = fixture.nativeElement.querySelector('[data-testid="demo-location-note"]');
    expect(note).toBeTruthy();
    const enText = note.textContent.trim();
    expect(enText).toContain('Demo: location set to a Kuttanad point (Kerala-only pilot).');

    // Hindi
    langService.setLanguage('hi');
    fixture.detectChanges();
    note = fixture.nativeElement.querySelector('[data-testid="demo-location-note"]');
    expect(note.textContent.trim()).toContain('डेमो: स्थान कुट्टनाड बिंदु पर सेट किया गया (केवल केरल पायलट)।');

    // Hinglish (must differ from English)
    langService.setLanguage('hinglish');
    fixture.detectChanges();
    note = fixture.nativeElement.querySelector('[data-testid="demo-location-note"]');
    const hinglishText = note.textContent.trim();
    expect(hinglishText).toContain('Demo: location ko Kuttanad point par set kiya gaya (Kerala-only pilot).');
    expect(hinglishText).not.toEqual(enText);

    // Malayalam
    langService.setLanguage('ml');
    fixture.detectChanges();
    note = fixture.nativeElement.querySelector('[data-testid="demo-location-note"]');
    expect(note.textContent.trim()).toContain('ഡെമോ: ലൊക്കേഷൻ കുട്ടനാട് പോയിന്റിലേക്ക് മാറ്റി (കേരള പൈലറ്റ് മാത്രം).');
  });
});

