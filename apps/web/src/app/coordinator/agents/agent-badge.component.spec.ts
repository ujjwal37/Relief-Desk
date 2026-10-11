import { ComponentFixture, TestBed } from '@angular/core/testing';
import { AgentBadgeComponent } from './agent-badge.component';

describe('AgentBadgeComponent', () => {
  let fixture: ComponentFixture<AgentBadgeComponent>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({ imports: [AgentBadgeComponent] }).compileComponents();
    fixture = TestBed.createComponent(AgentBadgeComponent);
  });

  it('maps gemini, fallback, and replay to icon and word', () => {
    fixture.componentRef.setInput('source', 'gemini');
    fixture.detectChanges();
    expect(fixture.nativeElement.textContent).toContain('Gemini');
    expect(fixture.nativeElement.querySelector('.gemini')).not.toBeNull();

    fixture.componentRef.setInput('source', 'fallback');
    fixture.detectChanges();
    expect(fixture.nativeElement.textContent).toContain('Offline fallback');
    expect(fixture.nativeElement.querySelector('.fallback')).not.toBeNull();

    fixture.componentRef.setInput('source', 'replay');
    fixture.detectChanges();
    expect(fixture.nativeElement.textContent).toContain('Recorded Gemini run');
    expect(fixture.nativeElement.querySelector('.replay')).not.toBeNull();
  });
});
