import { ComponentFixture, TestBed } from '@angular/core/testing';
import { StoredRequest } from '@rd/shared';
import { AgentTraceDrawerComponent } from './agent-trace-drawer.component';

const REQUEST = {
  id: 'INC-001',
  ai_source: 'offline_fallback',
  trace: [
    { agent: 'Intake', status: 'complete', output: 'rescue', model: 'gemini-3.8-flash', latency_ms: 10, tool_calls: [], input_summary: 'report' },
    { agent: 'Triage', status: 'complete', output: 'score 90', model: 'gemini-3.8-flash', latency_ms: 30, tool_calls: ['score_urgency'], input_summary: 'report' },
    { agent: 'Matching', status: 'complete', output: '2 boat free', model: 'gemini-3.8-flash', latency_ms: 20, tool_calls: ['check_capacity'], input_summary: 'report' },
  ],
} as StoredRequest;

describe('AgentTraceDrawerComponent', () => {
  let fixture: ComponentFixture<AgentTraceDrawerComponent>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({ imports: [AgentTraceDrawerComponent] }).compileComponents();
    fixture = TestBed.createComponent(AgentTraceDrawerComponent);
    fixture.componentRef.setInput('request', REQUEST);
    fixture.componentRef.setInput('mobile', false);
    fixture.detectChanges();
  });

  it('lists five agents, the parallel group, and the offline badge', () => {
    const text = fixture.nativeElement.textContent as string;
    expect(fixture.nativeElement.querySelector('[role="dialog"]')).not.toBeNull();
    expect(text).toContain('Intake');
    expect(text).toContain('Duplicate check');
    expect(text).toContain('Triage');
    expect(text).toContain('Matching');
    expect(text).toContain('Explainer');
    expect(text).toContain('in parallel');
    expect(text).toContain('Offline fallback');
    expect(text).toContain('Not recorded');
    expect(text).toContain('gemini-3.8-flash');
    expect(fixture.nativeElement.querySelectorAll('.details').length).toBe(5);
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
    expect(fixture.nativeElement.textContent).toContain('No tools');
  });
});
