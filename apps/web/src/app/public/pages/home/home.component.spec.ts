import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { of, throwError } from 'rxjs';
import { ApiClientService, LanguageService, ReportStatusResponse } from '@rd/shared';
import { HomeComponent } from './home.component';

describe('HomeComponent my requests', () => {
  let fixture: ComponentFixture<HomeComponent>;

  const status: ReportStatusResponse = {
    report_id: 'rep_internal',
    request_id: 'req_internal',
    public_code: 'RD-1042',
    status: 'new',
    hero_title: 'status.heroReceived',
    hero_subtitle: 'RD-1042',
    eta_display: '',
    delivery_status: 'status.waiting',
    timeline: [],
    while_you_wait_tips: [],
    emergency_phone: '112',
    synthetic: true,
  };

  beforeEach(async () => {
    localStorage.setItem('rd_my_requests', JSON.stringify([
      { id: 'rep_internal', token: 'tok_real', at: 1 },
    ]));
    const api = jasmine.createSpyObj('ApiClientService', ['getReportStatus', 'getHealth']);
    api.getHealth.and.returnValue(of({ demo_mode: true }));
    api.getReportStatus.and.returnValue(of(status));

    await TestBed.configureTestingModule({
      imports: [HomeComponent],
      providers: [provideRouter([]), { provide: ApiClientService, useValue: api }],
    }).compileComponents();

    TestBed.inject(LanguageService).setLanguage('en');
    fixture = TestBed.createComponent(HomeComponent);
    fixture.detectChanges();
  });

  afterEach(() => localStorage.removeItem('rd_my_requests'));

  it('shows the translated status and the public code', () => {
    const text = fixture.nativeElement.textContent as string;
    expect(text).toContain('Sent. A coordinator will review it.');
    expect(text).toContain('RD-1042');
    expect(text).not.toContain('status.heroReceived');
    expect(text).not.toContain('rep_internal');
  });
});

describe('HomeComponent stale request', () => {
  afterEach(() => localStorage.removeItem('rd_my_requests'));

  it('shows a removed request with its type, time, and a remove button', async () => {
    localStorage.setItem('rd_my_requests', JSON.stringify([
      { id: 'rep_gone', token: 'tok', at: Date.parse('2026-10-12T11:42:00'), kind: 'rescue' },
    ]));
    const api = jasmine.createSpyObj('ApiClientService', ['getReportStatus', 'getHealth']);
    api.getHealth.and.returnValue(of({ demo_mode: false }));
    api.getReportStatus.and.returnValue(throwError(() => ({ status: 404 })));
    await TestBed.configureTestingModule({
      imports: [HomeComponent],
      providers: [provideRouter([]), { provide: ApiClientService, useValue: api }],
    }).compileComponents();
    TestBed.inject(LanguageService).setLanguage('en');
    const gone = TestBed.createComponent(HomeComponent);
    gone.detectChanges();
    const text = gone.nativeElement.textContent as string;
    expect(text).toContain('This request is no longer available');
    expect(text).toContain('Rescue');
    expect(text).toContain('Remove');
    expect(gone.nativeElement.querySelector('a.view')).toBeNull();
    (gone.nativeElement.querySelector('button.rm') as HTMLButtonElement).click();
    expect(localStorage.getItem('rd_my_requests')).toBe('[]');
  });
});
