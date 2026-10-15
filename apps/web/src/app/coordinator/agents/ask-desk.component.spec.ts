import { TestBed } from '@angular/core/testing';
import { of } from 'rxjs';
import { ApiClientService, LanguageService } from '@rd/shared';
import { AskDeskComponent } from './ask-desk.component';

describe('AskDeskComponent', () => {
  const answer = {
    question: 'elderly in Aluva',
    reason: 'Searched waiting cases with elderly in Aluva.',
    total: 1,
    cases: [{ id: 'INC-001', type: 'rescue', ward_id: 'ward_4', ward_name: 'Aluva', place_text: null,
      people_count: 3, status: 'new', urgency_score: 9, vulnerable: ['elderly'], summary: 'Two elderly on a roof' }],
    ai: { provider: 'gemini', model: 'gemini-3.5-flash-lite' },
    trace: [
      { agent: 'Understand question', provider: 'gemini', model: 'gemini-3.5-flash-lite', latency_ms: 840, output: '{}' },
      { agent: 'Search cases (read-only)', provider: 'tool', model: null, latency_ms: 1, output: '1 match(es)' },
    ],
  };
  const api = { askDesk: jasmine.createSpy('askDesk').and.returnValue(of(answer)) };
  const lang = { currentLang: () => 'en', translate: (k: string) => k };

  beforeEach(() => {
    TestBed.configureTestingModule({
      imports: [AskDeskComponent],
      providers: [
        { provide: ApiClientService, useValue: api },
        { provide: LanguageService, useValue: lang },
      ],
    });
  });

  it('asks the API and maps the trace', () => {
    const c = TestBed.createComponent(AskDeskComponent).componentInstance;
    c.question = 'elderly in Aluva';
    c.ask();
    expect(api.askDesk).toHaveBeenCalledWith('elderly in Aluva', 'en');
    expect(c.answer()?.cases.length).toBe(1);
    expect(c.steps().map((s) => s.provider)).toEqual(['gemini', 'tool']);
    expect(c.viaText(answer as any)).toBe('gemini-3.5-flash-lite');
  });

  it('shows example cards until the first answer, then keeps a thread', () => {
    const fixture = TestBed.createComponent(AskDeskComponent);
    fixture.componentRef.setInput('fullPage', true);
    fixture.detectChanges();
    expect(fixture.nativeElement.textContent).toContain('ux.agentHello');
    expect(fixture.nativeElement.textContent).toContain('ux.exampleA1');
    expect(fixture.nativeElement.querySelectorAll('.example').length).toBe(3);
    expect(fixture.nativeElement.querySelector('.suggestions')).toBeNull();
    expect(fixture.nativeElement.querySelector('form.composer')).not.toBeNull();
    fixture.componentInstance.question = 'elderly in Aluva';
    fixture.componentInstance.ask();
    fixture.detectChanges();
    expect(fixture.componentInstance.thread().length).toBe(1);
    expect(fixture.nativeElement.textContent).toContain('INC-001');
    expect(fixture.nativeElement.querySelector('.example')).toBeNull();
    expect(fixture.nativeElement.querySelector('.suggestions')).toBeNull();
    expect(fixture.nativeElement.querySelector('.hello')).toBeNull();
    expect(fixture.nativeElement.querySelector('form.composer')).not.toBeNull();
    expect(fixture.nativeElement.querySelector('.case-link')).not.toBeNull();
    expect(fixture.nativeElement.querySelector('.page')?.classList.contains('has-thread')).toBeTrue();
  });

  it('labels rule answers', () => {
    const c = TestBed.createComponent(AskDeskComponent).componentInstance;
    expect(c.viaText({ ...answer, ai: { provider: 'fallback', model: null } } as any)).toBe('ux.deskByRules');
  });

  it('labels a test provider answer with its vendor, never Gemini', () => {
    lang.translate = (k: string) => (k === 'ux.badgeTest' ? 'Test model ({name})' : k);
    const c = TestBed.createComponent(AskDeskComponent).componentInstance;
    const via = c.viaText({ ...answer, ai: { provider: 'openai_compat', model: 'meta/llama-3.3-70b-instruct', vendor: 'NVIDIA' } } as any);
    lang.translate = (k: string) => k;
    expect(via).toBe('meta/llama-3.3-70b-instruct · Test model (NVIDIA)');
  });
});
