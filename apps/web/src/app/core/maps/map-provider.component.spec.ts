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

  it('fits bounds to the case and its teams and labels the line', async () => {
    api.getMapsConfig.and.returnValue(of({ enabled: false, apiKey: null }));
    const fixture = await create(api);
    fixture.detectChanges();
    await fixture.whenStable();
    const provider = fixture.debugElement.children[0].componentInstance as MapProviderComponent;
    const fitBounds = jasmine.createSpy('fitBounds');
    const extended: { lat: number; lng: number }[] = [];
    const created: Record<string, unknown>[] = [];
    const canvas = document.createElement('div');
    (provider as unknown as { canvas: { nativeElement: HTMLElement } }).canvas = { nativeElement: canvas };
    (provider as unknown as { mode: string }).mode = 'google';
    (window as unknown as { google: unknown }).google = {
      maps: {
        Map: class {
          fitBounds = fitBounds;
        },
        LatLngBounds: class {
          extend(pos: { lat: number; lng: number }) { extended.push(pos); }
        },
        Marker: class {
          constructor(opts: Record<string, unknown>) { created.push(opts); }
          setMap() {}
          addListener() {}
        },
        Polyline: class {
          constructor(opts: Record<string, unknown>) { created.push(opts); }
          setMap() {}
        },
        SymbolPath: { CIRCLE: 0 },
      },
    };
    provider.pins = [{ id: 'INC-001', lat: 9.436, lng: 76.398, title: 'Nedumudi' }];
    provider.legs = [{
      id: 'RES-BOAT-01',
      from: { lat: 9.436, lng: 76.398 },
      to: { lat: 9.43, lng: 76.398 },
      title: '0.7 km · about 2 min',
      suggested: true,
    }];
    provider.center = { lat: 9.436, lng: 76.398 };
    (provider as unknown as { draw: () => void }).draw();
    expect(fitBounds).toHaveBeenCalled();
    expect(extended.some((point) => point.lat === 9.43 && point.lng === 76.398)).toBeTrue();
    expect(created.some((opts) => (opts['label'] as { text?: string } | undefined)?.text === '0.7 km · about 2 min')).toBeTrue();
    delete (window as unknown as { google?: unknown }).google;
  });

  it('fits bounds to every pin when the overview map has no lines', async () => {
    api.getMapsConfig.and.returnValue(of({ enabled: false, apiKey: null }));
    const fixture = await create(api);
    fixture.detectChanges();
    await fixture.whenStable();
    const provider = fixture.debugElement.children[0].componentInstance as MapProviderComponent;
    const fitBounds = jasmine.createSpy('fitBounds');
    const extended: { lat: number; lng: number }[] = [];
    const canvas = document.createElement('div');
    (provider as unknown as { canvas: { nativeElement: HTMLElement } }).canvas = { nativeElement: canvas };
    (provider as unknown as { mode: string }).mode = 'google';
    (window as unknown as { google: unknown }).google = {
      maps: {
        Map: class { fitBounds = fitBounds; },
        LatLngBounds: class {
          extend(pos: { lat: number; lng: number }) { extended.push(pos); }
        },
        Marker: class {
          setMap() {}
          addListener() {}
        },
        Polyline: class { setMap() {} },
        SymbolPath: { CIRCLE: 0 },
      },
    };
    provider.fitAll = true;
    provider.pins = [
      { id: 'a', lat: 9.43, lng: 76.35, title: 'A' },
      { id: 'b', lat: 11.6, lng: 76.08, title: 'B' },
    ];
    provider.legs = [];
    (provider as unknown as { draw: () => void }).draw();
    expect(fitBounds).toHaveBeenCalled();
    expect(extended.some((point) => point.lat === 9.43)).toBeTrue();
    expect(extended.some((point) => point.lat === 11.6)).toBeTrue();
    delete (window as unknown as { google?: unknown }).google;
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
