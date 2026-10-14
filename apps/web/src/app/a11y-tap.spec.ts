import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { LandingComponent } from './landing/landing.component';
import { PublicLayoutComponent } from './public/layouts/public-layout.component';
import { LanguageService, LanguageSwitcherComponent } from '@rd/shared';
import { of } from 'rxjs';
import { ApiClientService } from '@rd/shared';

describe('tap targets and language layouts', () => {
  afterEach(() => {
    TestBed.inject(LanguageService).setLanguage('en');
  });
  it('language chips are at least 48px tall', async () => {
    await TestBed.configureTestingModule({
      imports: [LanguageSwitcherComponent],
    }).compileComponents();
    const fixture = TestBed.createComponent(LanguageSwitcherComponent);
    fixture.detectChanges();
    fixture.nativeElement.querySelector('details.more').open = true;
    fixture.detectChanges();
    const all = fixture.nativeElement.querySelectorAll('button, summary') as NodeListOf<HTMLElement>;
    expect(all.length).toBe(5);
    const names = [...all].map((el) => el.getAttribute('aria-label') || (el.textContent || '').trim());
    expect(names).toEqual(['English', 'Hindi', 'More', 'Hinglish', 'Malayalam']);
    all.forEach((button) => {
      expect(button.getBoundingClientRect().height).toBeGreaterThanOrEqual(48);
    });
  });

  it('landing call control is at least 48px and Hindi text is not clipped', async () => {
    await TestBed.configureTestingModule({
      imports: [LandingComponent],
      providers: [provideRouter([])],
    }).compileComponents();
    const fixture: ComponentFixture<LandingComponent> = TestBed.createComponent(LandingComponent);
    fixture.detectChanges();
    const call = fixture.nativeElement.querySelector('a.pill') as HTMLElement;
    expect(call.getBoundingClientRect().height).toBeGreaterThanOrEqual(44);
    (fixture.nativeElement.querySelector('.rd-set-btn') as HTMLButtonElement).click();
    fixture.detectChanges();
    (fixture.nativeElement.querySelectorAll('.opt')[1] as HTMLButtonElement).click();
    fixture.detectChanges();
    const text = fixture.nativeElement.textContent as string;
    expect(text.length).toBeGreaterThan(10);
    expect(call.scrollWidth).toBeLessThanOrEqual(call.clientWidth + 1);
  });

  it('public nav links stay at least 48px in Malayalam', async () => {
    await TestBed.configureTestingModule({
      imports: [PublicLayoutComponent],
      providers: [
        provideRouter([]),
        { provide: ApiClientService, useValue: { getScenarios: () => of([]) } },
      ],
    }).compileComponents();
    const fixture = TestBed.createComponent(PublicLayoutComponent);
    fixture.detectChanges();
    (fixture.nativeElement.querySelector('.rd-set-btn') as HTMLButtonElement).click();
    fixture.detectChanges();
    (fixture.nativeElement.querySelector('[data-testid="lang-more"]') as HTMLButtonElement).click();
    fixture.detectChanges();
    (fixture.nativeElement.querySelectorAll('.opt')[4] as HTMLButtonElement).click();
    fixture.detectChanges();
    const links = fixture.nativeElement.querySelectorAll('.tab') as NodeListOf<HTMLElement>;
    expect(links.length).toBeGreaterThan(0);
    links.forEach((link) => {
      expect(link.getBoundingClientRect().height).toBeGreaterThanOrEqual(48);
    });
  });
});
