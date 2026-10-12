import { Component } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { of } from 'rxjs';
import { ApiClientService } from '@rd/shared';
import { MapProviderComponent } from './map-provider.component';
import { MapProviderService } from './map-provider.service';

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
  pins: { id: string; lat: number; lng: number; title: string; spec?: { kind: 'case'; severity: 'critical'; queue: number; merged: number } }[] = [
    { id: 'INC-001', lat: 26.85, lng: 80.92, title: 'Ward 7' },
  ];
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

describe('MapProviderComponent advanced markers', () => {
  const previous = (window as unknown as { google?: unknown }).google;

  afterEach(() => {
    (window as unknown as { google?: unknown }).google = previous;
  });

  it('uses AdvancedMarkerElement with the configured map id and does not pass styles', async () => {
    const Map = jasmine.createSpy('Map').and.returnValue({ panTo: () => undefined });
    const AdvancedMarkerElement = jasmine.createSpy('AdvancedMarkerElement').and.returnValue({
      map: null,
      addListener: () => undefined,
    });
    (window as unknown as { google?: unknown }).google = {
      maps: {
        Map,
        ColorScheme: { LIGHT: 'LIGHT', DARK: 'DARK' },
        marker: { AdvancedMarkerElement },
      },
    };
    const maps = jasmine.createSpyObj('MapProviderService', ['decide', 'mapId']);
    maps.decide.and.returnValue(Promise.resolve('google'));
    maps.mapId.and.returnValue('DEMO_MAP_ID');
    await TestBed.configureTestingModule({
      imports: [HostComponent],
      providers: [{ provide: MapProviderService, useValue: maps }],
    }).compileComponents();
    const fixture = TestBed.createComponent(HostComponent);
    fixture.componentInstance.pins = [{
      id: 'INC-001',
      lat: 9.5,
      lng: 76.4,
      title: 'Case 1, critical, 2 reports',
      spec: { kind: 'case', severity: 'critical', queue: 1, merged: 2 },
    }];
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();
    expect(fixture.nativeElement.querySelector('.rd-google-map')).toBeTruthy();
    expect(Map).toHaveBeenCalled();
    const opts = Map.calls.mostRecent().args[1] as Record<string, unknown>;
    expect(opts['mapId']).toBe('DEMO_MAP_ID');
    expect(opts['styles']).toBeUndefined();
    expect(AdvancedMarkerElement).toHaveBeenCalled();
    const marker = AdvancedMarkerElement.calls.mostRecent().args[0] as Record<string, unknown>;
    expect(marker['gmpClickable']).toBeTrue();
    expect(marker['title']).toBe('Case 1, critical, 2 reports');
    expect(marker['content']).toBeTruthy();
    expect(marker['zIndex']).toBeGreaterThan(0);
  });
});

async function create(api: jasmine.SpyObj<ApiClientService>): Promise<ComponentFixture<HostComponent>> {
  await TestBed.configureTestingModule({
    imports: [HostComponent],
    providers: [{ provide: ApiClientService, useValue: api }],
  }).compileComponents();
  return TestBed.createComponent(HostComponent);
}
