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
        { provide: ApiClientService, useValue: { getScenarios: () => of([]) } },
      ],
    }).compileComponents();
    const fixture = TestBed.createComponent(CoordinatorLayoutComponent);
    fixture.detectChanges();
    return fixture;
  }

  afterEach(() => TestBed.resetTestingModule());

  it('shows a 390px phone frame beside the coordinator when ?demo=1 on a wide screen', async () => {
    const fixture = await setup('1', true);
    const frame = fixture.nativeElement.querySelector('.demo-phone') as HTMLElement;
    const iframe = fixture.nativeElement.querySelector('iframe') as HTMLIFrameElement;
    expect(frame).toBeTruthy();
    expect(iframe.getAttribute('src')).toBe('/report');
    expect(getComputedStyle(frame).width === '' || frame.classList.contains('demo-phone')).toBeTrue();
    expect(fixture.nativeElement.querySelector('.coordinator-shell.with-phone')).toBeTruthy();
  });

  it('hides the phone frame when the viewport is under 600px', async () => {
    const fixture = await setup('1', false);
    expect(fixture.nativeElement.querySelector('.demo-phone')).toBeNull();
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
    expect(rows.size).toBeLessThanOrEqual(2);
    expect(getComputedStyle(nav).overflow).not.toBe('auto');
    const labels = Array.from(nav.querySelectorAll('a, button')).map((el) => (el.textContent || '').trim());
    expect(labels.some((label) => label.includes('Overview'))).toBeTrue();
    expect(labels.some((label) => label.includes('Cases'))).toBeTrue();
    expect(labels.some((label) => label.includes('Agent'))).toBeTrue();
    expect(labels.join(' ')).not.toContain('Accuracy report');
    (fixture.nativeElement.querySelector('.avatar') as HTMLButtonElement).click();
    fixture.detectChanges();
    const accuracy = Array.from(fixture.nativeElement.querySelectorAll('.menu a')).find((link) =>
      ((link as HTMLElement).textContent || '').includes('Accuracy report'),
    ) as HTMLElement;
    expect(accuracy).toBeTruthy();
  });

  it('opens Cases when the top search box is used from another tab', async () => {
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

  it('hides the phone frame when demo mode is off', async () => {
    const fixture = await setup(null, true);
    expect(fixture.nativeElement.querySelector('.demo-phone')).toBeNull();
  });
});
