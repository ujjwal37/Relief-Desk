import { ComponentFixture, TestBed } from '@angular/core/testing';
import { LanguageService } from '@rd/shared';
import { TraceStepComponent, TraceStepView } from './trace-step.component';

const STEP: TraceStepView = {
  agent: 'Triage',
  status: 'done',
  output: 'score 90',
  model: 'gemini-3.8-flash',
  latencyMs: 420,
  provider: 'gemini',
  input: 'five people',
  tools: ['score_urgency'],
  asked: 'five people',
  raw: 'score 90',
  note: null,
};

describe('TraceStepComponent', () => {
  let fixture: ComponentFixture<TraceStepComponent>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({ imports: [TraceStepComponent] }).compileComponents();
    TestBed.inject(LanguageService).setLanguage('en');
    fixture = TestBed.createComponent(TraceStepComponent);
    fixture.componentRef.setInput('step', STEP);
    fixture.componentRef.setInput('nameKey', 'ux.agentTriage');
    fixture.componentRef.setInput('open', false);
    fixture.detectChanges();
  });

  it('shows the output, model, and a collapsed details control', () => {
    const text = fixture.nativeElement.textContent as string;
    expect(text).toContain('Triage');
    expect(text).toContain('Done');
    expect(text).toContain('score 90');
    expect(text).toContain('Gemini');
    expect(text).not.toContain('gemini-3.8-flash');
    expect(text).toContain('420 ms');
    const button = fixture.nativeElement.querySelector('.details') as HTMLButtonElement;
    expect(button.getAttribute('aria-expanded')).toBe('false');
    expect(fixture.nativeElement.querySelector('.tools')).toBeNull();
  });

  it('expands tools and says when none were used', () => {
    fixture.componentRef.setInput('open', true);
    fixture.detectChanges();
    expect(fixture.nativeElement.querySelector('.details')?.getAttribute('aria-expanded')).toBe('true');
    expect(fixture.nativeElement.textContent).toContain('score_urgency');
    fixture.componentRef.setInput('step', { ...STEP, tools: [], model: null, latencyMs: null, output: null, input: null, asked: null, raw: null });
    fixture.detectChanges();
    const text = fixture.nativeElement.textContent as string;
    expect(text).toContain('Rules');
    expect(text).not.toContain('No tools');
    expect(text).not.toContain('Not recorded');
  });

  it('shows a test provider as Test model (vendor), even when cached', () => {
    fixture.componentRef.setInput('step', { ...STEP, provider: 'openai_compat', vendor: 'NVIDIA', model: 'meta/llama-3.3-70b-instruct' });
    fixture.detectChanges();
    const text = fixture.nativeElement.textContent as string;
    expect(text).toContain('Test model (NVIDIA)');
    expect(text).not.toContain('Gemini');
  });
});
