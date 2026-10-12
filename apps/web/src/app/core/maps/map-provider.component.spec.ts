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

  it('pans the map when View on map asks for the same centre again', async () => {
    api.getMapsConfig.and.returnValue(of({ enabled: false, apiKey: null }));
    const fixture = await create(api);
    fixture.detectChanges();
    await fixture.whenStable();
    const provider = fixture.debugElement.children[0].componentInstance as MapProviderComponent;
    const panTo = jasmine.createSpy('panTo');
    (provider as unknown as { map: { panTo: (pos: { lat: number; lng: number }) => void } }).map = { panTo };
    provider.center = { lat: 10.308, lng: 76.331 };
    provider.focusToken = 1;
    provider.ngOnChanges();
    expect(panTo).toHaveBeenCalledWith({ lat: 10.308, lng: 76.331 });
    panTo.calls.reset();
    provider.focusToken = 2;
    provider.ngOnChanges();
    expect(panTo).toHaveBeenCalledWith({ lat: 10.308, lng: 76.331 });
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
