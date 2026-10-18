import { ComponentFixture, TestBed } from '@angular/core/testing';
import { ActivatedRoute, convertToParamMap, provideRouter, Router } from '@angular/router';
import { of } from 'rxjs';
import { ApiClientService } from '@rd/shared';
import { CoordinatorLayoutComponent } from './coordinator-layout.component';

describe('CoordinatorLayoutComponent demo phone', () => {
  function media(matches: boolean): void {
    spyOn(window, 'matchMedia').and.returnValue({
      matches,
      media: '(min-width: 600px)',
      addEventListener: () => undefined,
      removeEventListener: () => undefined,
      addListener: () => undefined,
      removeListener: () => undefined,
      dispatchEvent: () => false,
      onchange: null,
    } as MediaQueryList);
  }

  async function setup(demo: string | null, wide: boolean): Promise<ComponentFixture<CoordinatorLayoutComponent>> {
    media(wide);
    await TestBed.configureTestingModule({
      imports: [CoordinatorLayoutComponent],
      providers: [
        provideRouter([]),
        {
          provide: ActivatedRoute,
          useValue: { queryParamMap: of(convertToParamMap(demo ? { demo } : {})) },
        },
        { provide: ApiClientService, useValue: {
          getScenarios: () => of([]),
          getHealth: () => of({ demo_mode: false }),
          getAiHealth: () => of({ provider: 'fallback', model: '', label: 'Rules fallback' }),
          generateSitrep: () => of({ brief: '', counts: { pending: 0, by_tier: {}, rescue_open: 0, rooftop_like: 0, free_boats: 0, free_medical: 0, free_food: 0, free_shelter: 0, boat_gap: 0, gaps: [] }, drafts: { sms_en: '', sms_hi: '', sms_ml: '', whatsapp_en: '', whatsapp_hi: '', whatsapp_ml: '' }, ai: { provider: 'fallback' }, cached: false, send: false }),
          submitSampleReport: () => of({ request_id: 'INC-S', report_id: 'r', status_token: 't', summary: '', urgency_score: 0, dedupe_decision: 'new', flags: [], safety_line: '' }),
        } },
      ],
    }).compileComponents();
    const fixture = TestBed.createComponent(CoordinatorLayoutComponent);
    fixture.detectChanges();
    return fixture;
  }

  afterEach(() => TestBed.resetTestingModule());

  it('shows the three steps once, then stays dismissed', async () => {
    localStorage.removeItem('rd_guide_dismissed');
    localStorage.removeItem('rd_tour_done');
    const fixture = await setup(null, true);
    expect(fixture.nativeElement.textContent).toContain('1 A report arrives');
    (fixture.nativeElement.querySelector('.guide-inline button') as HTMLButtonElement).click();
    fixture.detectChanges();
    expect(fixture.nativeElement.querySelector('.guide-inline')).toBeNull();
    expect(localStorage.getItem('rd_guide_dismissed')).toBe('1');
    localStorage.setItem('rd_tour_done', '1');
  });

  it('opens and closes the 390px citizen phone panel via try-citizen button', async () => {
    const fixture = await setup(null, true);
    expect(fixture.nativeElement.querySelector('.citizen-phone-panel')).toBeNull();

    const tryCitizen = fixture.nativeElement.querySelector('[data-testid="try-citizen"]') as HTMLButtonElement;
    expect(tryCitizen).toBeTruthy();
    tryCitizen.click();
    fixture.detectChanges();

    const panel = fixture.nativeElement.querySelector('.citizen-phone-panel') as HTMLElement;
    const iframe = fixture.nativeElement.querySelector('.citizen-frame') as HTMLIFrameElement;
    expect(panel).toBeTruthy();
    expect(iframe.getAttribute('src')).toBe('/report');

    const closeBtn = fixture.nativeElement.querySelector('[data-testid="close-phone-panel"]') as HTMLButtonElement;
    expect(closeBtn).toBeTruthy();
    closeBtn.click();
    fixture.detectChanges();
    expect(fixture.nativeElement.querySelector('.citizen-phone-panel')).toBeNull();
  });

  it('keeps the logo, tabs and avatar on at most two rows', async () => {
    const fixture = await setup(null, true);
    spyOnProperty(window, 'innerWidth', 'get').and.returnValue(390);
    fixture.componentInstance.syncCompactNav();
    fixture.detectChanges();
    const header = fixture.nativeElement.querySelector('.top-nav') as HTMLElement;
    header.style.width = '390px';
    const brand = header.querySelector('.brand') as HTMLElement;
    const nav = header.querySelector('nav.tabs') as HTMLElement;
    const avatar = header.querySelector('.avatar') as HTMLElement;
    const rows = new Set(
      [brand, nav, avatar].map((el) => Math.round(el.getBoundingClientRect().top / 8)),
    );
    expect(nav.classList.contains('wrap')).toBeTrue();
    expect(header.getBoundingClientRect().width).toBe(390); // Media-query geometry is covered by Playwright at a real 390px viewport.
    expect(getComputedStyle(nav).overflow).not.toBe('auto');
    const labels = Array.from(nav.querySelectorAll('a:not(.wide-only), button')).map((el) => (el.textContent || '').trim());
    expect(labels.some((label) => label.includes('Command'))).toBeTrue();
    expect(labels.some((label) => label === 'Cases')).toBeFalse();
    expect(labels.some((label) => label === 'Dispatched')).toBeFalse();
    expect(labels.some((label) => label.includes('Ask'))).toBeTrue();
    expect(labels.join(' ')).not.toContain('Overview');
    expect(labels.join(' ')).not.toContain('Accuracy report');
    (fixture.nativeElement.querySelector('.avatar') as HTMLButtonElement).click();
    fixture.detectChanges();
    const accuracy = Array.from(fixture.nativeElement.querySelectorAll('.menu a')).find((link) =>
      ((link as HTMLElement).textContent || '').includes('Accuracy report'),
    ) as HTMLElement;
    // Rules-only runs have no Gemini-vs-rules numbers, so Accuracy stays off the menu.
    expect(accuracy).toBeFalsy();
    const teams = Array.from(fixture.nativeElement.querySelectorAll('.menu a')).find((link) =>
      ((link as HTMLElement).textContent || '').includes('Teams'),
    ) as HTMLElement;
    expect(teams).toBeTruthy();
  });

  it('opens Home when the top search box is used from another tab', async () => {
    const fixture = await setup(null, true);
    const router = TestBed.inject(Router);
    spyOnProperty(router, 'url', 'get').and.returnValue('/coordinator/teams');
    const nav = spyOn(router, 'navigateByUrl').and.resolveTo(true);
    const input = fixture.nativeElement.querySelector('#coord-search') as HTMLInputElement;
    input.value = 'Chalakudy';
    input.dispatchEvent(new Event('input'));
    expect(fixture.componentInstance.ui.searchQuery()).toBe('Chalakudy');
    expect(nav).toHaveBeenCalledWith('/coordinator/command');
    fixture.componentInstance.ui.searchQuery.set('');
  });

  it('shows an honest AI health pill from /api/health/ai', async () => {
    const fixture = await setup(null, true);
    const pill = fixture.nativeElement.querySelector('[data-testid="ai-health"]') as HTMLElement;
    expect(pill).toBeTruthy();
    expect(pill.textContent).toContain('Rules mode');
    expect(pill.textContent).not.toContain('Gemini live');
  });

  it('hides the phone frame when demo mode is off', async () => {
    const fixture = await setup(null, true);
    expect(fixture.nativeElement.querySelector('.demo-phone')).toBeNull();
  });

  it('hides the demo tools menu when demoTools is false', async () => {
    const fixture = await setup(null, true);
    (fixture.nativeElement.querySelector('.avatar') as HTMLButtonElement).click();
    fixture.detectChanges();
    expect(fixture.componentInstance.demoTools()).toBeFalse();
    expect(fixture.nativeElement.querySelector('[data-testid="menu-live-demo"]')).toBeNull();
    expect(fixture.nativeElement.textContent).not.toContain('Demo tools');
  });

  it('shows the demo tools menu when demoTools is true', async () => {
    const fixture = await setup(null, true);
    fixture.componentInstance.demoTools.set(true);
    (fixture.nativeElement.querySelector('.avatar') as HTMLButtonElement).click();
    fixture.detectChanges();
    expect(fixture.nativeElement.querySelector('[data-testid="menu-live-demo"]')).toBeTruthy();
  });
});

