import { ComponentFixture, TestBed } from '@angular/core/testing';
import { ConfirmationCardComponent } from './confirmation-card.component';
import { ConfirmationCardData, LanguageService } from '@rd/shared';

const SAMPLE: ConfirmationCardData = {
  incident_type: 'rescue',
  place_text: 'Ward 7 · Gandhi School',
  people_count: 5,
  vulnerable: { child: true, elderly: true, disabled: false, pregnant: false, medical_need: false },
  hazard: 'water_rising',
  summary: '5 people needing rescue at Ward 7 · Gandhi School',
  safety_line: 'In an emergency call 112.',
  ready_to_submit: true,
};

describe('ConfirmationCardComponent', () => {
  let fixture: ComponentFixture<ConfirmationCardComponent>;
  let component: ConfirmationCardComponent;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [ConfirmationCardComponent],
    }).compileComponents();

    fixture = TestBed.createComponent(ConfirmationCardComponent);
    component = fixture.componentInstance;
    component.card = { ...SAMPLE, vulnerable: { ...SAMPLE.vulnerable } };
    TestBed.inject(LanguageService).setLanguage('en');
    fixture.detectChanges();
  });

  it('does not emit send until Send now is tapped', () => {
    const spy = jasmine.createSpy('send');
    component.send.subscribe(spy);
    expect(fixture.nativeElement.querySelector('.send-now')).toBeTruthy();
    expect(spy).not.toHaveBeenCalled();
    fixture.nativeElement.querySelector('.send-now').click();
    expect(spy).toHaveBeenCalledTimes(1);
    const emitted = spy.calls.mostRecent().args[0] as ConfirmationCardData;
    expect(emitted.people_count).toBe(5);
    expect(emitted.place_text).toContain('Gandhi School');
  });

  it('emits edited people count only after confirm', () => {
    const spy = jasmine.createSpy('send');
    component.send.subscribe(spy);
    const peopleEdit = fixture.nativeElement.querySelectorAll('.edit-btn')[2] as HTMLButtonElement;
    peopleEdit.click();
    fixture.detectChanges();
    const input = fixture.nativeElement.querySelector('.people-input') as HTMLInputElement;
    input.value = '8';
    input.dispatchEvent(new Event('input'));
    fixture.detectChanges();
    expect(spy).not.toHaveBeenCalled();
    fixture.nativeElement.querySelector('.send-now').click();
    expect(spy.calls.mostRecent().args[0].people_count).toBe(8);
  });

  it('renders the Hindi title when language is hi', () => {
    TestBed.inject(LanguageService).setLanguage('hi');
    fixture.detectChanges();
    const text = fixture.nativeElement.textContent as string;
    expect(text).toContain('हमारी समझ');
    expect(text).toContain('अभी भेजें');
    expect(text).toContain('बचाव');
    expect(text).toContain('पानी बढ़ रहा है');
    expect(text).not.toContain('water_rising');
  });
});
