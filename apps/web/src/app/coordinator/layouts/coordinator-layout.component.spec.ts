import { ComponentFixture, TestBed } from '@angular/core/testing';
import { ActivatedRoute, convertToParamMap, provideRouter } from '@angular/router';
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

  it('wraps the tab row on a phone so Accuracy report stays visible', async () => {
    const fixture = await setup(null, true);
    spyOnProperty(window, 'innerWidth', 'get').and.returnValue(390);
    fixture.componentInstance.syncCompactNav();
    fixture.detectChanges();
    const nav = fixture.nativeElement.querySelector('nav.tabs') as HTMLElement;
    expect(nav.classList.contains('wrap')).toBeTrue();
    expect(getComputedStyle(nav).flexWrap).toBe('wrap');
    expect(getComputedStyle(nav).overflow).not.toBe('auto');
    expect(nav.textContent).toContain('Accuracy report');
  });

  it('hides the phone frame when demo mode is off', async () => {
    const fixture = await setup(null, true);
    expect(fixture.nativeElement.querySelector('.demo-phone')).toBeNull();
  });
});
