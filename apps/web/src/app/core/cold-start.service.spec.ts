import { fakeAsync, TestBed, tick } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { ApiClientService, HealthResponse, LanguageService } from '@rd/shared';
import { of, Subject } from 'rxjs';
import { CoordinatorLoginComponent } from '../coordinator/pages/login/coordinator-login.component';
import { ColdStartBannerComponent } from './cold-start-banner.component';
import {
  COLD_START_ATTEMPT_MS,
  COLD_START_BACKOFF_MS,
  COLD_START_REVEAL_MS,
  ColdStartService,
} from './cold-start.service';

describe('ColdStartService', () => {
  let pending: Subject<HealthResponse>[];
  let api: jasmine.SpyObj<ApiClientService>;
  let service: ColdStartService;

  const ok = (): HealthResponse => ({
    status: 'ok',
    app: 'relief-desk',
    version: '0',
    gemini_enabled: false,
    demo_mode: true,
  });

  beforeEach(() => {
    pending = [];
    api = jasmine.createSpyObj('ApiClientService', ['getHealth']);
    api.getHealth.and.callFake(() => {
      const subject = new Subject<HealthResponse>();
      pending.push(subject);
      return subject.asObservable();
    });
    TestBed.configureTestingModule({
      providers: [{ provide: ApiClientService, useValue: api }],
    });
    service = TestBed.inject(ColdStartService);
  });

  it('pings /api/health on start and stays quiet when the server is already warm', fakeAsync(() => {
    service.start();
    service.start();
    expect(api.getHealth).toHaveBeenCalledTimes(1);
    expect(service.phase()).toBe('idle');

    tick(COLD_START_REVEAL_MS - 1);
    expect(service.phase()).toBe('idle');
    pending[0].next(ok());
    pending[0].complete();
    tick(COLD_START_REVEAL_MS);
    expect(service.phase()).toBe('idle');
    expect(api.getHealth).toHaveBeenCalledTimes(1);
  }));

  it('shows the waking state only after the first call is still pending', fakeAsync(() => {
    service.start();
    tick(COLD_START_REVEAL_MS);
    expect(service.phase()).toBe('waking');
    pending[0].next(ok());
    expect(service.phase()).toBe('idle');
    tick(COLD_START_ATTEMPT_MS);
    expect(api.getHealth).toHaveBeenCalledTimes(1);
  }));

  it('retries with backoff and then asks the user to try again', fakeAsync(() => {
    service.start();
    pending[0].error(new Error('down'));
    tick(COLD_START_BACKOFF_MS[0]);
    expect(api.getHealth).toHaveBeenCalledTimes(2);
    expect(service.phase()).toBe('idle');

    pending[1].error(new Error('down'));
    tick(COLD_START_REVEAL_MS - COLD_START_BACKOFF_MS[0]);
    expect(service.phase()).toBe('waking');

    tick(COLD_START_BACKOFF_MS[1] - (COLD_START_REVEAL_MS - COLD_START_BACKOFF_MS[0]));
    expect(api.getHealth).toHaveBeenCalledTimes(3);
    pending[2].error(new Error('down'));
    tick(COLD_START_BACKOFF_MS[2]);
    expect(api.getHealth).toHaveBeenCalledTimes(4);
    pending[3].error(new Error('down'));
    expect(service.phase()).toBe('failed');
    tick(COLD_START_ATTEMPT_MS);
    expect(api.getHealth).toHaveBeenCalledTimes(4);
  }));

  it('treats a hung health call as a failure and retries', fakeAsync(() => {
    service.start();
    tick(COLD_START_ATTEMPT_MS);
    expect(api.getHealth).toHaveBeenCalledTimes(1);
    tick(COLD_START_BACKOFF_MS[0]);
    expect(api.getHealth).toHaveBeenCalledTimes(2);
    pending[1].next(ok());
    expect(service.phase()).toBe('idle');
    tick(COLD_START_ATTEMPT_MS);
    expect(api.getHealth).toHaveBeenCalledTimes(2);
  }));

  it('hides the banner when a timed-out health call still returns 200', fakeAsync(() => {
    service.start();
    tick(COLD_START_REVEAL_MS);
    expect(service.phase()).toBe('waking');
    tick(COLD_START_ATTEMPT_MS - COLD_START_REVEAL_MS);
    expect(service.phase()).toBe('waking');
    pending[0].next(ok());
    expect(service.phase()).toBe('idle');
    tick(COLD_START_BACKOFF_MS[0] + COLD_START_ATTEMPT_MS);
    expect(api.getHealth).toHaveBeenCalledTimes(1);
  }));

  it('starts a fresh wake when the user retries', fakeAsync(() => {
    service.start();
    pending[0].error(new Error('down'));
    tick(COLD_START_BACKOFF_MS[0]);
    pending[1].error(new Error('down'));
    tick(COLD_START_BACKOFF_MS[1]);
    pending[2].error(new Error('down'));
    tick(COLD_START_BACKOFF_MS[2]);
    pending[3].error(new Error('down'));
    expect(service.phase()).toBe('failed');

    service.retry();
    expect(service.phase()).toBe('waking');
    expect(api.getHealth).toHaveBeenCalledTimes(5);
    pending[4].next(ok());
    expect(service.phase()).toBe('idle');
    tick(COLD_START_ATTEMPT_MS);
  }));
});

describe('ColdStartBannerComponent', () => {
  let pending: Subject<HealthResponse>[];
  let api: jasmine.SpyObj<ApiClientService>;

  beforeEach(async () => {
    pending = [];
    api = jasmine.createSpyObj('ApiClientService', ['getHealth']);
    api.getHealth.and.callFake(() => {
      const subject = new Subject<HealthResponse>();
      pending.push(subject);
      return subject.asObservable();
    });
    await TestBed.configureTestingModule({
      imports: [ColdStartBannerComponent],
      providers: [{ provide: ApiClientService, useValue: api }],
    }).compileComponents();
    TestBed.inject(LanguageService).setLanguage('en');
  });

  it('renders the waking copy, then the retry message, and retries from the button', fakeAsync(() => {
    const fixture = TestBed.createComponent(ColdStartBannerComponent);
    const service = TestBed.inject(ColdStartService);
    service.start();
    fixture.detectChanges();
    expect(fixture.nativeElement.textContent).not.toContain('Waking up the demo server');

    tick(COLD_START_REVEAL_MS);
    fixture.detectChanges();
    const waking = fixture.nativeElement.querySelector('.cold-banner') as HTMLElement;
    expect(waking.textContent).toContain('Waking up the demo server, this can take a few seconds on first load.');
    expect(waking.querySelector('button')).toBeNull();
    expect(fixture.nativeElement.querySelector('[role="status"]')).toBeTruthy();

    pending[0].error(new Error('down'));
    tick(COLD_START_BACKOFF_MS[0]);
    pending[1].error(new Error('down'));
    tick(COLD_START_BACKOFF_MS[1]);
    pending[2].error(new Error('down'));
    tick(COLD_START_BACKOFF_MS[2]);
    pending[3].error(new Error('down'));
    fixture.detectChanges();

    const failed = fixture.nativeElement.querySelector('.cold-banner.is-failed') as HTMLElement;
    expect(failed.textContent).toContain('The demo server did not respond. Check your connection and try again.');
    const button = failed.querySelector('button') as HTMLButtonElement;
    expect(button.textContent?.trim()).toBe('Try again');
    expect(button.getBoundingClientRect().height).toBeGreaterThanOrEqual(44);

    button.click();
    fixture.detectChanges();
    expect(fixture.nativeElement.textContent).toContain('Waking up the demo server');
    expect(api.getHealth).toHaveBeenCalledTimes(5);
    pending[4].next({
      status: 'ok',
      app: 'relief-desk',
      version: '0',
      gemini_enabled: false,
      demo_mode: true,
    });
    fixture.detectChanges();
    expect(fixture.nativeElement.querySelector('.cold-banner')).toBeNull();
    tick(COLD_START_ATTEMPT_MS);
  }));
});

describe('free-tier note on the login page', () => {
  it('places the note next to the demo login button', async () => {
    const api = jasmine.createSpyObj('ApiClientService', ['getHealth']);
    api.getHealth.and.returnValue(of({ status: 'ok', demo_mode: true }));
    await TestBed.configureTestingModule({
      imports: [CoordinatorLoginComponent],
      providers: [provideRouter([]), { provide: ApiClientService, useValue: api }],
    }).compileComponents();
    TestBed.inject(LanguageService).setLanguage('en');
    const fixture = TestBed.createComponent(CoordinatorLoginComponent);
    fixture.detectChanges();
    const demo = fixture.nativeElement.querySelector('.demo') as HTMLElement;
    const note = demo.querySelector('.cold-note') as HTMLElement;
    const button = demo.querySelector('.demo-btn') as HTMLElement;
    expect(note.textContent?.trim()).toBe('Free-tier demo: first load may take a few seconds.');
    expect(button.compareDocumentPosition(note) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });
});
