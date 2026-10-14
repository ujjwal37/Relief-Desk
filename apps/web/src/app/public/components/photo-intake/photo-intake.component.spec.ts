import { TestBed } from '@angular/core/testing';
import { of } from 'rxjs';
import { ApiClientService, LanguageService } from '@rd/shared';
import { PhotoIntakeComponent } from './photo-intake.component';

describe('PhotoIntakeComponent', () => {
  let api: jasmine.SpyObj<ApiClientService>;
  beforeEach(async () => {
    api = jasmine.createSpyObj('ApiClientService', ['analysePhoto']);
    api.analysePhoto.and.returnValue(of({
      reading: { water_level: 'waist', structural_damage: 'unclear', confidence: 0.6 },
      ai: { provider: 'gemini' }, needs_human_review: true, image_stored: false,
    }));
    await TestBed.configureTestingModule({ imports: [PhotoIntakeComponent], providers: [{ provide: ApiClientService, useValue: api }] }).compileComponents();
    TestBed.inject(LanguageService).setLanguage('en');
  });

  it('requires explicit analysis and reporter review before emitting any details', () => {
    const fixture = TestBed.createComponent(PhotoIntakeComponent);
    const component = fixture.componentInstance;
    const accepted: string[] = [];
    component.accepted.subscribe((text) => accepted.push(text));
    component.preview.set('data:image/png;base64,abcd');
    component.mime.set('image/png');
    fixture.detectChanges();
    component.analyse();
    expect(api.analysePhoto).not.toHaveBeenCalled();
    component.synthetic.set(true);
    component.analyse();
    fixture.detectChanges();
    expect(api.analysePhoto).toHaveBeenCalledWith(jasmine.objectContaining({ image_base64: 'abcd', synthetic: true }));
    expect(fixture.nativeElement.textContent).toContain('unverified');
    expect(fixture.nativeElement.textContent).not.toContain('Vision Verified');
    component.accept();
    expect(accepted).toEqual([]);
    component.reviewed.set(true);
    component.accept();
    expect(accepted[0]).toContain('Water appears waist-high');
    expect(component.preview()).toBe('');
  });

  it('leaves photo analysis off while offline', () => {
    const fixture = TestBed.createComponent(PhotoIntakeComponent);
    fixture.componentRef.setInput('online', false);
    fixture.componentInstance.preview.set('data:image/png;base64,abcd');
    fixture.componentInstance.synthetic.set(true);
    fixture.componentInstance.analyse();
    expect(api.analysePhoto).not.toHaveBeenCalled();
  });

  it('shows a model outage without inventing a reading', () => {
    api.analysePhoto.and.returnValue(of({ reading: null, ai: { provider: 'fallback', fallback_reason: 'timeout' }, needs_human_review: true, image_stored: false }));
    const fixture = TestBed.createComponent(PhotoIntakeComponent);
    fixture.componentInstance.preview.set('data:image/png;base64,abcd');
    fixture.componentInstance.synthetic.set(true);
    fixture.componentInstance.analyse();
    fixture.detectChanges();
    expect(fixture.nativeElement.textContent).toContain('Photo analysis is unavailable');
    expect(fixture.nativeElement.textContent).not.toContain('AI photo suggestions');
  });
});
