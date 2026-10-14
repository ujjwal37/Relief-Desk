import { ComponentFixture, TestBed } from '@angular/core/testing';
import { of } from 'rxjs';
import { ApiClientService, LanguageService, RecentReport } from '@rd/shared';
import { JustReportedStripComponent } from './just-reported-strip.component';
import { JustReportedService } from './just-reported.service';

describe('JustReportedStripComponent', () => {
  let fixture: ComponentFixture<JustReportedStripComponent>;
  let store: JustReportedService;

  const now = new Date().toISOString();
  const older = new Date(Date.now() - 4 * 60 * 1000).toISOString();
  const rows: RecentReport[] = [
    {
      id: 'rep-old',
      case_id: 'INC-OLD',
      type: 'rescue',
      summary: 'Water at the ferry',
      ward_id: 'ward_1',
      place_text: 'Kainakary Ferry',
      created_at: older,
      joined_existing: false,
    },
    {
      id: 'rep-new',
      case_id: 'INC-OLD',
      type: 'medical',
      summary: 'Medicine needed',
      ward_id: 'ward_1',
      place_text: 'Kainakary',
      created_at: now,
      joined_existing: true,
    },
  ];

  beforeEach(async () => {
    const api = jasmine.createSpyObj('ApiClientService', ['getRecentReports']);
    api.getRecentReports.and.returnValue(of([]));
    await TestBed.configureTestingModule({
      imports: [JustReportedStripComponent],
      providers: [{ provide: ApiClientService, useValue: api }],
    }).compileComponents();
    TestBed.inject(LanguageService).setLanguage('en');
    store = TestBed.inject(JustReportedService);
    fixture = TestBed.createComponent(JustReportedStripComponent);
    fixture.detectChanges();
  });

  it('keeps the strip to three newest reports', () => {
    const extra: RecentReport[] = [1, 2, 3, 4].map((n) => ({
      id: `rep-${n}`,
      case_id: `INC-${n}`,
      type: 'rescue',
      summary: `Report ${n}`,
      ward_id: 'ward_1',
      place_text: 'Kainakary',
      created_at: new Date(Date.now() - n * 1000).toISOString(),
      joined_existing: false,
    }));
    store.apply(extra);
    fixture.detectChanges();
    expect(fixture.nativeElement.querySelectorAll('button.chip').length).toBe(3);
  });

  it('lists newest first with a ward, a New badge, and a merge note', () => {
    store.apply(rows);
    fixture.detectChanges();
    const strip = fixture.nativeElement.querySelector('[data-testid="just-reported"]') as HTMLElement;
    const buttons = strip.querySelectorAll('button.chip');
    expect(buttons.length).toBe(2);
    expect(buttons[0].textContent).toContain('Medicine needed');
    expect(buttons[0].textContent).toContain('Kainakary');
    expect(buttons[0].textContent).toContain('New');
    expect(buttons[0].textContent).toContain('Joined an existing case');
    expect(buttons[0].querySelector('.ico')?.getAttribute('data-type')).toBe('medical');
    expect(buttons[1].textContent).toContain('Water at the ferry');
    expect(buttons[1].textContent).not.toContain('Joined an existing case');
  });

  it('opens the case and toasts a later arrival', () => {
    store.apply([rows[0]]);
    fixture.detectChanges();
    const picked: string[] = [];
    fixture.componentInstance.picked.subscribe((id) => picked.push(id));
    (fixture.nativeElement.querySelector('button.chip') as HTMLButtonElement).click();
    expect(picked).toEqual(['INC-OLD']);

    store.apply(rows);
    fixture.detectChanges();
    expect(fixture.nativeElement.querySelector('.arrival-toast')?.textContent).toContain('New report: Kainakary, medical');
  });
});