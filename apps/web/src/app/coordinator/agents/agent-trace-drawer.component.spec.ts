import { ComponentFixture, TestBed } from '@angular/core/testing';
import { LanguageService, StoredRequest } from '@rd/shared';
import { AgentTraceDrawerComponent } from './agent-trace-drawer.component';

const REQUEST = {
  id: 'INC-001',
  ai_source: 'offline_fallback',
  trace: [
    { agent: 'Intake', status: 'complete', output: 'rescue', model: 'gemini-3.8-flash', provider: 'fallback', latency_ms: 10, tool_calls: [], input_summary: 'report' },
    { agent: 'Triage', status: 'complete', output: 'score 90', model: null, provider: 'tool', latency_ms: 30, tool_calls: ['score_urgency'], input_summary: 'report' },
    { agent: 'Matching', status: 'complete', output: '2 boat free', model: null, provider: 'tool', latency_ms: 20, tool_calls: ['check_capacity'], input_summary: 'report' },
  ],
} as unknown as StoredRequest;

describe('AgentTraceDrawerComponent', () => {
  let fixture: ComponentFixture<AgentTraceDrawerComponent>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({ imports: [AgentTraceDrawerComponent] }).compileComponents();
    TestBed.inject(LanguageService).setLanguage('en');
    fixture = TestBed.createComponent(AgentTraceDrawerComponent);
    fixture.componentRef.setInput('request', REQUEST);
    fixture.componentRef.setInput('mobile', false);
    fixture.detectChanges();
  });

  it('lists five agents, the parallel group, and the offline badge', () => {
    const text = fixture.nativeElement.textContent as string;
    expect(fixture.nativeElement.querySelector('[role="dialog"]')).not.toBeNull();
    expect(text).toContain('Understood the report');
    expect(text).toContain('Checked for duplicates');
    expect(text).toContain('Rated urgency');
    expect(text).toContain('Found the closest team');
    expect(text).toContain('Explained the choice');
    expect(text).toContain('At the same time');
    expect(fixture.nativeElement.querySelector('.run-badge')?.textContent).toContain('Rules');
    expect(text).not.toContain('Offline fallback');
    expect(text).toContain('Waiting');
    expect(text).toContain('Rules');
    expect(text).toContain('Python tool');
    expect(text).not.toContain('gemini-3.8-flash');
    expect(fixture.nativeElement.querySelectorAll('.details').length).toBe(3);
  });

  it('names a test provider honestly and never as Gemini', () => {
    const local = TestBed.createComponent(AgentTraceDrawerComponent);
    local.componentRef.setInput('request', {
      id: 'INC-009',
      ai_source: 'openai_compat',
      ai: { provider: 'openai_compat', model: 'meta/llama-3.3-70b-instruct', cached: true },
      trace: [
        { agent: 'Intake', status: 'complete', output: 'rescue', model: 'meta/llama-3.3-70b-instruct', provider: 'openai_compat', vendor: 'NVIDIA', latency_ms: 900, tool_calls: [] },
        { agent: 'Triage', status: 'complete', output: 'score 90', model: null, provider: 'tool', latency_ms: 3, tool_calls: [] },
      ],
    } as unknown as StoredRequest);
    local.detectChanges();
    expect(local.nativeElement.querySelector('.run-badge')?.textContent).toContain('Test model');
    const intake = local.nativeElement.querySelector('app-trace-step')?.textContent as string;
    expect(intake).toContain('Test model');
    expect(intake).not.toContain('Gemini');
  });

  it('shows a complete urgency reason once and does not call Python steps timeouts', () => {
    const reason = 'Vulnerable flags: child, elderly, medical need + 7 persons + stranded on structure (Urgency score: 88)';
    fixture.componentRef.setInput('request', { ...REQUEST, urgency_reason: reason, trace: [
      { agent: 'Triage', status: 'complete', provider: 'tool', output: 'score 88', tool_calls: ['score_urgency'] },
    ] });
    fixture.detectChanges();
    const text = fixture.nativeElement.textContent as string;
    expect(text).toContain(reason);
    expect(text).not.toContain('Vulnerable flags: Vulnerable flags:');
    expect(fixture.nativeElement.querySelector('.banner.warn')).toBeNull();
  });

  it('previews fallback without mutating saved provenance', () => {
    const original = JSON.stringify(REQUEST);
    fixture.componentInstance.simulateOutage.set(true);
    fixture.detectChanges();
    expect(fixture.nativeElement.textContent).toContain('Preview only');
    expect(fixture.componentInstance.steps().find((step) => step.agent === 'Triage')?.provider).toBe('fallback');
    expect(JSON.stringify(REQUEST)).toBe(original);
    fixture.componentInstance.simulateOutage.set(false);
    expect(fixture.componentInstance.steps().find((step) => step.agent === 'Triage')?.provider).toBe('tool');
  });

  it('keeps a single step expanded', () => {
    const buttons = fixture.nativeElement.querySelectorAll('.details') as NodeListOf<HTMLButtonElement>;
    buttons[0].click();
    fixture.detectChanges();
    buttons[1].click();
    fixture.detectChanges();
    const open = Array.from(fixture.nativeElement.querySelectorAll('.details') as NodeListOf<HTMLButtonElement>)
      .filter((button) => button.getAttribute('aria-expanded') === 'true');
    expect(open.length).toBe(1);
    expect(fixture.nativeElement.textContent).not.toContain('No tools');
  });
});
