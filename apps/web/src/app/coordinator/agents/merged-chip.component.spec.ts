import { ComponentFixture, TestBed } from '@angular/core/testing';
import { of } from 'rxjs';
import { ApiClientService } from '@rd/shared';
import { MergedChipComponent } from './merged-chip.component';

describe('MergedChipComponent', () => {
  let fixture: ComponentFixture<MergedChipComponent>;
  let api: jasmine.SpyObj<ApiClientService>;

  beforeEach(async () => {
    api = jasmine.createSpyObj('ApiClientService', ['getMerge']);
    api.getMerge.and.returnValue(of({
      why: 'duplicate',
      reports: [
        { id: 'INC-001', text: null, at: null, channel: null, lang: null },
      ],
    }));
    await TestBed.configureTestingModule({
      imports: [MergedChipComponent],
      providers: [{ provide: ApiClientService, useValue: api }],
    }).compileComponents();
    fixture = TestBed.createComponent(MergedChipComponent);
    fixture.componentRef.setInput('count', 3);
    fixture.componentRef.setInput('requestId', 'INC-001');
    fixture.componentRef.setInput('mobile', false);
    fixture.detectChanges();
  });

  it('opens stored evidence and leaves missing quotes as not recorded', () => {
    expect(fixture.nativeElement.textContent).toContain('3 reports');
    (fixture.nativeElement.querySelector('.chip') as HTMLButtonElement).click();
    fixture.detectChanges();
    const text = fixture.nativeElement.textContent as string;
    expect(text).toContain('Reports merged into this case');
    expect(text).toContain('Text not stored');
    expect(text).toContain('duplicate');
    expect(text).toContain('Undo merge');
    expect(api.getMerge).toHaveBeenCalledWith('INC-001');
  });
});
