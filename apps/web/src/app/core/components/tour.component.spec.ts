import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import { provideHttpClientTesting } from '@angular/common/http/testing';
import { TourComponent } from './tour.component';
import { CoordUiService } from '../services/coord-ui.service';
import { LanguageService } from '@rd/shared';

describe('TourComponent', () => {
  let fixture: ComponentFixture<TourComponent>;
  let component: TourComponent;
  let ui: CoordUiService;

  beforeEach(async () => {
    localStorage.removeItem('rd_tour_v2_off');
    await TestBed.configureTestingModule({
      imports: [TourComponent],
      providers: [CoordUiService, LanguageService, provideHttpClient(), provideHttpClientTesting()],
    }).compileComponents();

    TestBed.inject(LanguageService).setLanguage('en');
    ui = TestBed.inject(CoordUiService);
    ui.cornerPromptOpen.set(true);
    fixture = TestBed.createComponent(TourComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  afterEach(() => {
    localStorage.removeItem('rd_tour_v2_off');
  });

  it('renders corner card when cornerPromptOpen is true', () => {
    const card = fixture.nativeElement.querySelector('.tour-corner-card');
    expect(card).toBeTruthy();
    expect(card.textContent).toContain('Take a 60-second tour');
  });

  it('adds with-panel class to corner card when phone panel is open', () => {
    ui.phonePanelOpen.set(true);
    fixture.detectChanges();
    const card = fixture.nativeElement.querySelector('.tour-corner-card');
    expect(card.classList.contains('with-panel')).toBeTrue();
  });

  it('dismisses corner prompt on Skip click', () => {
    const skipBtn = fixture.nativeElement.querySelector('[data-testid="tour-skip"]') as HTMLButtonElement;
    expect(skipBtn).toBeTruthy();
    skipBtn.click();
    fixture.detectChanges();
    expect(ui.cornerPromptOpen()).toBeFalse();
  });

  it('clamps tour callout to not cover the phone panel when phone panel is open', () => {
    ui.phonePanelOpen.set(true);
    ui.tourOpen.set(true);
    component.place(false);
    fixture.detectChanges();

    const pos = component.cardPos();
    const vw = window.innerWidth;
    const maxExpectedLeft = vw - 390;
    // Left position + card width (max 320) must be <= available width
    expect(pos.left + 320).toBeLessThanOrEqual(maxExpectedLeft + 24);
  });
});
