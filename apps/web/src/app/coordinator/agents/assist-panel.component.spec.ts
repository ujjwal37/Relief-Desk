import { ComponentFixture, TestBed } from '@angular/core/testing';
import { AssistPanelComponent } from './assist-panel.component';

describe('AssistPanelComponent', () => {
  let fixture: ComponentFixture<AssistPanelComponent>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({ imports: [AssistPanelComponent] }).compileComponents();
    fixture = TestBed.createComponent(AssistPanelComponent);
    fixture.componentRef.setInput('proposals', [
      {
        match_id: 'm1',
        request_id: 'INC-001',
        title: 'School lane',
        team_name: 'Boat 2',
        team_kind: 'boat',
        why: 'Nearest free boat',
        expires_at: new Date(Date.now() + 60000).toISOString(),
        expired: false,
      },
      {
        match_id: 'm2',
        request_id: 'INC-002',
        title: 'Canal',
        team_name: 'Boat 3',
        team_kind: 'boat',
        why: null,
        expires_at: null,
        expired: true,
      },
    ]);
    fixture.componentRef.setInput('shortages', [
      { kind: 'boat', have: 2, need: 3, explanation: 'Not enough teams for the demand.' },
    ]);
    fixture.detectChanges();
  });

  it('keeps the approval sentence visible and shows shortage and an ended hold', () => {
    const text = fixture.nativeElement.textContent as string;
    expect(text).toContain('Nothing is dispatched until you approve');
    expect(text).toContain('Assist mode');
    expect(text).toContain('Why only 2 of 3?');
    expect(text).toContain('Not enough teams for the demand.');
    expect(text).toContain('Hold ended. Ask again');
    expect(text).toContain('Nearest free boat');
    expect(text).toContain('Approve all (1)');
  });
});
