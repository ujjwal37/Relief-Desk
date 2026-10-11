import { ComponentFixture, TestBed } from '@angular/core/testing';
import { AssistBannerComponent } from './assist-banner.component';

describe('AssistBannerComponent', () => {
  let fixture: ComponentFixture<AssistBannerComponent>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({ imports: [AssistBannerComponent] }).compileComponents();
    fixture = TestBed.createComponent(AssistBannerComponent);
  });

  it('uses a singular line for one assignment and a plural line otherwise', () => {
    fixture.componentRef.setInput('count', 1);
    fixture.detectChanges();
    expect(fixture.nativeElement.textContent).toContain('Staff low: dispatcher suggests 1 assignment');
    fixture.componentRef.setInput('count', 4);
    fixture.detectChanges();
    expect(fixture.nativeElement.textContent).toContain('Staff low: dispatcher suggests 4 assignments');
    expect(fixture.nativeElement.querySelector('button')?.textContent).toContain('Review');
  });
});
