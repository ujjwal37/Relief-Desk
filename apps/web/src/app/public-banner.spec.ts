import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { LandingComponent } from './landing/landing.component';
import { PublicLayoutComponent } from './public/layouts/public-layout.component';

describe('112 banner on public screens', () => {
  it('landing shows the emergency banner and a 112 link', async () => {
    await TestBed.configureTestingModule({
      imports: [LandingComponent],
      providers: [provideRouter([])],
    }).compileComponents();
    const fixture: ComponentFixture<LandingComponent> = TestBed.createComponent(LandingComponent);
    fixture.detectChanges();
    const text = fixture.nativeElement.textContent as string;
    expect(text).toContain('112');
    expect(fixture.nativeElement.querySelector('a[href="tel:112"]')).toBeTruthy();
  });

  it('public layout shows the emergency banner and a 112 link', async () => {
    await TestBed.configureTestingModule({
      imports: [PublicLayoutComponent],
      providers: [provideRouter([])],
    }).compileComponents();
    const fixture: ComponentFixture<PublicLayoutComponent> = TestBed.createComponent(PublicLayoutComponent);
    fixture.detectChanges();
    const text = fixture.nativeElement.textContent as string;
    expect(text).toContain('call 112');
    expect(fixture.nativeElement.querySelector('a[href="tel:112"]')).toBeTruthy();
  });
});
