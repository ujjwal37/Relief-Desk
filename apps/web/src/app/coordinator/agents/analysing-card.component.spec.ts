import { ComponentFixture, TestBed } from '@angular/core/testing';
import { StoredRequest } from '@rd/shared';
import { AnalysingCardComponent } from './analysing-card.component';

describe('AnalysingCardComponent', () => {
  let fixture: ComponentFixture<AnalysingCardComponent>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({ imports: [AnalysingCardComponent] }).compileComponents();
    fixture = TestBed.createComponent(AnalysingCardComponent);
    fixture.componentRef.setInput('request', {
      id: 'INC-NEW',
      analysis_status: 'analysing',
      trace: [
        { agent: 'Intake', status: 'complete' },
        { agent: 'Dedupe', status: 'complete' },
        { agent: 'Triage', status: 'working' },
      ],
    } as StoredRequest);
    fixture.detectChanges();
  });

  it('shows the four steps and how many agents are done', () => {
    const text = fixture.nativeElement.textContent as string;
    expect(text).toContain('Analysing new report');
    expect(text).toContain('New report · just now');
    expect(text).toContain('Duplicate check + Triage');
    expect(text).toContain('2 of 5 agents done');
    expect(text).toContain('Usually under 5 seconds');
    expect(fixture.nativeElement.querySelector('.spin')).not.toBeNull();
    expect(fixture.nativeElement.getAttribute('role') || fixture.nativeElement.querySelector('[role="status"]')).toBeTruthy();
  });
});
