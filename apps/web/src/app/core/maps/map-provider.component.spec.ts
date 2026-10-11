import { Component } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { of } from 'rxjs';
import { ApiClientService } from '@rd/shared';
import { MapProviderComponent } from './map-provider.component';

@Component({
  standalone: true,
  imports: [MapProviderComponent],
  template: `
    <rd-map-provider [pins]="pins">
      <span class="fallback-mark">svg-fallback</span>
    </rd-map-provider>
  `,
})
class HostComponent {
  pins = [{ id: 'INC-001', lat: 26.85, lng: 80.92, title: 'Ward 7' }];
}

describe('MapProviderComponent', () => {
  let api: jasmine.SpyObj<ApiClientService>;

  beforeEach(() => {
    api = jasmine.createSpyObj('ApiClientService', ['getMapsConfig']);
  });

  it('keeps the SVG fallback when no maps key is configured', async () => {
    api.getMapsConfig.and.returnValue(of({ enabled: false, apiKey: null }));
    const fixture = await create(api);
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();
    expect(fixture.nativeElement.textContent).toContain('svg-fallback');
    expect(fixture.nativeElement.querySelector('.rd-google-map')).toBeNull();
  });

  it('keeps the SVG fallback when the browser is offline', async () => {
    spyOnProperty(navigator, 'onLine', 'get').and.returnValue(false);
    const fixture = await create(api);
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();
    expect(api.getMapsConfig).not.toHaveBeenCalled();
    expect(fixture.nativeElement.textContent).toContain('svg-fallback');
  });
});

async function create(api: jasmine.SpyObj<ApiClientService>): Promise<ComponentFixture<HostComponent>> {
  await TestBed.configureTestingModule({
    imports: [HostComponent],
    providers: [{ provide: ApiClientService, useValue: api }],
  }).compileComponents();
  return TestBed.createComponent(HostComponent);
}
