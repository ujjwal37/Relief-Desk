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
import { panIfMoved } from './map-center';
import { MapProviderService } from './map-provider.service';

export interface MapPin {
  id: string;
  lat: number;
  lng: number;
  title: string;
}

export interface MapLeg {
  id: string;
  from: { lat: number; lng: number };
  to: { lat: number; lng: number };
  title: string;
  suggested?: boolean;
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
  @Input() legs: MapLeg[] = [];
  @Input() center: { lat: number; lng: number } = { lat: 10.50, lng: 76.30 };
  /** Bump this to pan again even when the centre numbers did not change. */
  @Input() focusToken = 0;
  @Output() pinSelect = new EventEmitter<string>();

  @ViewChild('canvas') canvas?: ElementRef<HTMLDivElement>;

  mode: 'google' | 'svg' = 'svg';
  private map: { panTo?: (pos: { lat: number; lng: number }) => void; fitBounds?: (bounds: unknown, padding?: number) => void } | null = null;
  private markers: { setMap?: (map: null) => void }[] = [];
  private lines: { setMap?: (map: null) => void }[] = [];
  private lastCenter: { lat: number; lng: number } | null = null;
  private lastToken = 0;

  ngAfterViewInit(): void {
    this.maps.decide().then((mode) => {
      this.mode = mode;
      this.cdr.detectChanges();
      if (mode === 'google') {
        this.draw();
      }
    });
    window.addEventListener('offline', this.onOffline);
  }

  ngOnDestroy(): void {
    window.removeEventListener('offline', this.onOffline);
  }

  ngOnChanges(): void {
    const force = this.focusToken !== this.lastToken;
    this.lastToken = this.focusToken;
    if (force && this.map && Number.isFinite(this.center?.lat) && Number.isFinite(this.center?.lng)) {
      this.map.panTo?.(this.center);
      this.lastCenter = { lat: this.center.lat, lng: this.center.lng };
    } else {
      this.lastCenter = panIfMoved(this.map, this.lastCenter, this.center);
    }
    if (this.mode === 'google' && this.map) {
      this.draw();
    }
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
    if (!el || !maps) {
      this.mode = 'svg';
      this.cdr.markForCheck();
      return;
    }
    try {
      if (!this.map) {
        this.map = new maps.Map(el, {
          center: this.center,
          zoom: 13,
          mapTypeControl: false,
          streetViewControl: false,
          fullscreenControl: false,
        });
        this.lastCenter = { lat: this.center.lat, lng: this.center.lng };
      }
      this.markers.forEach((marker) => marker.setMap?.(null));
      this.lines.forEach((line) => line.setMap?.(null));
      this.lines = this.legs.map((leg) => new maps.Polyline({
        map: this.map,
        path: [leg.from, leg.to],
        strokeColor: leg.suggested ? '#0b6e4f' : '#5c6570',
        strokeWeight: leg.suggested ? 4 : 2,
        geodesic: true,
      }));
      const labels = this.legs.filter((leg) => leg.title).map((leg) => new maps.Marker({
        map: this.map,
        position: { lat: (leg.from.lat + leg.to.lat) / 2, lng: (leg.from.lng + leg.to.lng) / 2 },
        label: {
          text: leg.title,
          color: leg.suggested ? '#0b6e4f' : '#1c2430',
          fontSize: '12px',
          fontWeight: '700',
        },
        icon: { path: maps.SymbolPath?.CIRCLE ?? 0, scale: 0 },
        clickable: false,
      }));
      this.markers = this.pins.map((pin) => {
        const marker = new maps.Marker({
          map: this.map,
          position: { lat: pin.lat, lng: pin.lng },
          title: pin.title,
        });
        marker.addListener?.('click', () => this.pinSelect.emit(pin.id));
        return marker;
      });
      this.markers.push(...labels);
      this.fitToLegs(maps);
    } catch {
      this.mode = 'svg';
      this.map = null;
      this.cdr.markForCheck();
    }
  }

  /** When a case is open, keep the case pin and its candidate teams in view. */
  private fitToLegs(maps: GoogleMapsNs): void {
    if (!this.map?.fitBounds || !this.legs.length || !maps.LatLngBounds) return;
    const bounds = new maps.LatLngBounds();
    for (const leg of this.legs) {
      bounds.extend(leg.from);
      bounds.extend(leg.to);
    }
    const anchor = this.legs[0].from;
    bounds.extend({ lat: anchor.lat + 0.012, lng: anchor.lng + 0.012 });
    bounds.extend({ lat: anchor.lat - 0.012, lng: anchor.lng - 0.012 });
    this.map.fitBounds(bounds, 48);
  }
}

interface GoogleMapsNs {
  Map: new (el: HTMLElement, opts: Record<string, unknown>) => {
    panTo?: (pos: { lat: number; lng: number }) => void;
    fitBounds?: (bounds: unknown, padding?: number) => void;
  };
  LatLngBounds?: new () => { extend: (pos: { lat: number; lng: number }) => void };
  Marker: new (opts: Record<string, unknown>) => { setMap?: (map: null) => void; addListener?: (event: string, fn: () => void) => void };
  Polyline: new (opts: Record<string, unknown>) => { setMap?: (map: null) => void };
  SymbolPath?: { CIRCLE: number };
}
