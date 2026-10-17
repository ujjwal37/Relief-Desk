import { ComponentFixture, TestBed } from '@angular/core/testing';
import { DIALOG_DATA, DialogRef } from '@angular/cdk/dialog';
import { LanguageService, StoredRequest } from '@rd/shared';
import { StepDetailDialogComponent, StepDetailData } from './step-detail-dialog.component';

describe('StepDetailDialogComponent', () => {
  const request = {
    id: 'INC-004',
    type: 'rescue',
    place_text: 'Kalpetta',
    people_count: 12,
    hazard: 'water_rising',
    urgency_score: 91,
    urgency_reason: 'Children and a wheelchair user are trapped',
    vulnerable: { child: true, elderly: false, disabled: true, pregnant: false, medical_need: false },
  } as StoredRequest;

  async function setup(extra: Partial<StepDetailData>): Promise<ComponentFixture<StepDetailDialogComponent>> {
    const data: StepDetailData = {
      request,
      stepIndex: 0,
      totalSteps: 6,
      stepNameKey: 'flow.intake',
      badge: 'gemini',
      prompt: 'SYSTEM\nRead this report.',
      tools: [],
      rawOutput: '12 people need a boat at Kalpetta.',
      model: 'gemini-3.5-flash-lite',
      latencyMs: 17200,
      ...extra,
    };
    await TestBed.configureTestingModule({
      imports: [StepDetailDialogComponent],
      providers: [
        { provide: DIALOG_DATA, useValue: data },
        { provide: DialogRef, useValue: { close() { /* dialog stays in the test */ } } },
      ],
    }).compileComponents();
    TestBed.inject(LanguageService).setLanguage('en');
    const fixture = TestBed.createComponent(StepDetailDialogComponent);
    fixture.detectChanges();
    return fixture;
  }

  afterEach(() => TestBed.resetTestingModule());

  it('says what Gemini understood, then hides the prompt until asked', async () => {
    const fixture = await setup({});
    const root = fixture.nativeElement as HTMLElement;
    expect(root.querySelector('.headline')?.textContent).toContain('Kalpetta');
    expect(root.querySelector('.chips')?.textContent).toContain('Rescue');
    expect(root.querySelector('.chips')?.textContent).toContain('12');
    expect(root.querySelector('.chips')?.textContent).toContain('Water rising');
    expect(root.querySelector('.chips')?.textContent).not.toContain('ux.none');
    expect(root.querySelector('.why')?.textContent).toContain('Inputs used');
    expect(root.querySelector('.note')?.textContent).toBe('Gemini gemini-3.5-flash-lite · 17.2 s');
    expect(root.querySelector('[data-testid="prompt-and-response"]')).toBeNull();
    (root.querySelector('[data-testid="show-prompt"]') as HTMLButtonElement).click();
    fixture.detectChanges();
    const block = root.querySelector('[data-testid="prompt-and-response"]') as HTMLElement;
    expect(block.textContent).toContain('Read this report.');
    expect(block.querySelector('[data-testid="step-tools"]')?.textContent).toContain('No tools');
    expect(block.textContent).toContain('12 people need a boat');
    expect(root.textContent).not.toContain('Offline fallback');
    expect(root.textContent).not.toContain('No model ran for this step');
  });

  it('labels the map step Google Maps and the approval step You', async () => {
    const maps = await setup({
      stepIndex: 3,
      stepNameKey: 'flow.badgeTool',
      badge: 'tool',
      providerLabel: 'Google Maps',
      model: undefined,
      prompt: undefined,
      tools: ['check_capacity', 'match_score'],
      rawOutput: JSON.stringify({ team: 'Rescue Boat #02', km: 1.4 }),
      distanceKm: 1.4,
    });
    expect(maps.nativeElement.querySelector('.note')?.textContent).toBe('Google Maps');
    expect(maps.nativeElement.querySelector('.headline')?.textContent).toContain('Rescue Boat #02');
    expect(maps.nativeElement.querySelector('.headline')?.textContent).toContain('1.4');
    TestBed.resetTestingModule();

    const you = await setup({
      stepIndex: 5,
      stepNameKey: 'flow.badgeYou',
      badge: 'you',
      providerLabel: 'You',
      model: undefined,
      prompt: undefined,
      rawOutput: '',
    });
    expect(you.nativeElement.querySelector('.note')?.textContent).toBe('You');
    expect(you.nativeElement.querySelector('.headline')?.textContent).toContain('Nothing is sent until you approve');
  });

  it('fills a blank distance and says no model only when none ran', async () => {
    const fixture = await setup({
      stepIndex: 4,
      stepNameKey: 'flow.explain',
      badge: 'fallback',
      model: undefined,
      prompt: undefined,
      rawOutput: '5 boat free: — km',
      distanceKm: 2.4,
    });
    expect(fixture.nativeElement.querySelector('.headline')?.textContent).toContain('2.4 km');
    expect(fixture.nativeElement.textContent).not.toContain('—');
    // With no prompt there is nothing to reveal; the no-model line shows directly.
    const reveal = fixture.nativeElement.querySelector('[data-testid="show-prompt"]') as HTMLButtonElement | null;
    reveal?.click();
    fixture.detectChanges();
    expect(fixture.nativeElement.textContent).toContain('Rules mode');
    expect(fixture.nativeElement.querySelector('[data-testid="prompt-and-response"]')).toBeNull();
  });
});
