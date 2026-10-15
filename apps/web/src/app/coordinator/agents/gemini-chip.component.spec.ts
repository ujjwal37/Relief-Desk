import { TestBed } from '@angular/core/testing';
import { GeminiChipComponent } from './gemini-chip.component';

describe('GeminiChipComponent', () => {
  beforeEach(() => TestBed.configureTestingModule({ imports: [GeminiChipComponent] }));

  it('shows Gemini and puts confidence on the hover title', () => {
    const fixture = TestBed.createComponent(GeminiChipComponent);
    fixture.componentRef.setInput('confidence', 0.84);
    fixture.detectChanges();
    const chip = fixture.nativeElement.querySelector('[data-testid="gemini-chip"]') as HTMLElement;
    expect(chip.textContent).toMatch(/Gemini|जेमिनी/);
    expect(chip.getAttribute('title')).toContain('84%');
  });
});
