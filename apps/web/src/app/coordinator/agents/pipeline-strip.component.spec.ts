import { TestBed } from '@angular/core/testing';
import { PipelineStripComponent } from './pipeline-strip.component';

describe('PipelineStripComponent', () => {
  beforeEach(() => TestBed.configureTestingModule({ imports: [PipelineStripComponent] }));

  it('keeps the five pipeline steps and shows a measured dedupe percent', () => {
    const fixture = TestBed.createComponent(PipelineStripComponent);
    fixture.componentRef.setInput('steps', [
      { agent: 'extract', status: 'complete', summary: 'rescue' },
      { agent: 'dedupe', status: 'complete', similarity: 0.87, match_id: 'INC-012' },
    ]);
    fixture.detectChanges();
    const text = fixture.nativeElement.textContent as string;
    expect(text).toContain('Extract');
    expect(text).toContain('87%');
    expect(text).toContain('INC-012');
    expect(text).toContain('Triage');
    expect(text).toContain('Approval');
  });
});
