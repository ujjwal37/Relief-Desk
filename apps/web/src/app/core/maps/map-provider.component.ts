import { CommonModule } from '@angular/common';
import {
  AfterViewInit,
  ChangeDetectionStrategy,
  ChangeDetectorRef,
  Component,
  ElementRef,
  EventEmitter,
  Input,
  OnChanges,
  OnDestroy,
  Output,
  ViewChild,
  inject,
} from '@angular/core';
import { MapProviderService } from './map-provider.service';
import { DEMO_MAP_ID, MarkerInput, PinSpec, clusterMapPins, pinMarkerContent, pinZ } from './map-pins';

export interface MapPin extends MarkerInput {}

/**
 * Google map options. A mapId is required for AdvancedMarkerElement, and a mapId
 * ignores the styles array, so the muted basemap is a Cloud style (see README).
 */
export function googleMapOptions(
  center: { lat: number; lng: number },
  mapId: string,
  colorScheme: unknown,
): Record<string, unknown> {
  const opts: Record<string, unknown> = {
    center,
    zoom: 13,
    mapId: mapId || DEMO_MAP_ID,
    mapTypeControl: false,
    streetViewControl: false,
    fullscreenControl: false,
  };
  if (colorScheme != null) opts['colorScheme'] = colorScheme;
  return opts;
}

export function themeIsDark(): boolean {
  const mode = document.documentElement.getAttribute('data-theme');
  if (mode === 'dark') return true;
  if (mode === 'light') return false;
  return window.matchMedia?.('(prefers-color-scheme: dark)').matches ?? false;
}

@Component({
  selector: 'rd-map-provider',
  standalone: true,
  imports: [CommonModule],
  template: `
    @if (mode === 'google') {
      <div #canvas class="rd-google-map" role="application" aria-label="Relief map"></div>
    } @else {
      <ng-content></ng-content>
    }
  `,
  styles: [`
    :host { display: block; width: 100%; height: 100%; min-height: 250px; position: relative; }
    .rd-google-map { width: 100%; height: 100%; min-height: 250px; }
  `],
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class MapProviderComponent implements AfterViewInit, OnChanges, OnDestroy {
  private maps = inject(MapProviderService);
  private cdr = inject(ChangeDetectorRef);

  @Input() pins: MapPin[] = [];
  @Input() center: { lat: number; lng: number } = { lat: 10.50, lng: 76.30 };
  @Output() pinSelect = new EventEmitter<string>();

  @ViewChild('canvas') canvas?: ElementRef<HTMLDivElement>;

  mode: 'google' | 'svg' = 'svg';
  private map: { panTo?: (pos: { lat: number; lng: number }) => void } | null = null;
  private markers: { map: unknown }[] = [];
  private themeObserver = new MutationObserver(() => {
    if (this.mode !== 'google') return;
    this.map = null;
    this.draw();
  });

  ngAfterViewInit(): void {
    this.themeObserver.observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] });
    this.maps.decide().then((mode) => {
      this.mode = mode;
      this.cdr.detectChanges();
      if (mode === 'google') this.draw();
    });
    window.addEventListener('offline', this.onOffline);
  }

  ngOnDestroy(): void {
    this.themeObserver.disconnect();
    window.removeEventListener('offline', this.onOffline);
  }

  ngOnChanges(): void {
    if (this.mode === 'google' && this.map) this.draw();
  }

  private onOffline = (): void => {
    this.mode = 'svg';
    this.map = null;
    this.cdr.markForCheck();
  };

  private draw(): void {
    const el = this.canvas?.nativeElement;
    const google = (window as unknown as { google?: { maps?: GoogleMapsNs } }).google;
    const maps = google?.maps;
    const Advanced = maps?.marker?.AdvancedMarkerElement;
    if (!el || !maps || !Advanced) {
      this.mode = 'svg';
      this.map = null;
      this.cdr.markForCheck();
      return;
    }
    try {
      if (!this.map) {
        const scheme = themeIsDark() ? maps.ColorScheme?.DARK : maps.ColorScheme?.LIGHT;
        this.map = new maps.Map(el, googleMapOptions(this.center, this.maps.mapId(), scheme));
      } else {
        this.map.panTo?.(this.center);
      }
      this.markers.forEach((marker) => { marker.map = null; });
      const prepared = clusterMapPins(this.pins);
      this.markers = prepared.map((pin) => {
        const spec: PinSpec = pin.spec ?? { kind: 'case', severity: 'low' };
        const marker = new Advanced({
          map: this.map,
          position: { lat: pin.lat, lng: pin.lng },
          title: pin.title,
          content: pinMarkerContent(spec, !!pin.dim),
          gmpClickable: true,
          zIndex: pin.zIndex ?? pinZ(spec),
        });
        marker.addListener?.('click', () => this.pinSelect.emit(pin.id));
        return marker;
      });
    } catch {
      this.mode = 'svg';
      this.map = null;
      this.cdr.markForCheck();
    }
  }
}

interface GoogleMapsNs {
  Map: new (el: HTMLElement, opts: Record<string, unknown>) => { panTo?: (pos: { lat: number; lng: number }) => void };
  ColorScheme?: { LIGHT: unknown; DARK: unknown };
  marker?: {
    AdvancedMarkerElement: new (opts: Record<string, unknown>) => {
      map: unknown;
      addListener?: (event: string, fn: () => void) => void;
    };
  };
}
