import { CommonModule } from '@angular/common';
import {
  AfterContentInit,
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
  signal,
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
      @if (builtin()) {
        <svg class="rd-schematic" viewBox="0 0 600 480" preserveAspectRatio="xMidYMid meet" role="img" aria-label="Relief map">
          <rect width="600" height="480" fill="var(--map-bg, #efeae0)"/>
          @for (leg of schematicLegs(); track leg.id) {
            <line [attr.x1]="leg.x1" [attr.y1]="leg.y1" [attr.x2]="leg.x2" [attr.y2]="leg.y2" [attr.stroke]="leg.suggested ? '#0b6e4f' : '#5c6570'" [attr.stroke-width]="leg.suggested ? 4 : 2" stroke-linecap="round"/>
            @if (leg.title) {
              <text class="rd-leg" [attr.x]="leg.lx" [attr.y]="leg.ly" text-anchor="middle">{{ leg.title }}</text>
            }
          }
          @for (pin of schematicPins(); track pin.id) {
            <circle [attr.cx]="pin.x" [attr.cy]="pin.y" r="8" [attr.fill]="pin.onLeg ? '#0b6e4f' : '#1c2430'" stroke="#fff" stroke-width="2"/>
          }
        </svg>
      }
    }
  `,
  styles: [`
    :host { display: block; width: 100%; height: 100%; min-height: 250px; position: relative; }
    .rd-google-map, .rd-schematic { position: absolute; inset: 0; width: 100%; height: 100%; min-height: 250px; display: block; }
    .rd-leg { font-size: 13px; font-weight: 700; fill: #1c2430; }
  `],
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class MapProviderComponent implements AfterContentInit, AfterViewInit, OnChanges, OnDestroy {
  private maps = inject(MapProviderService);
  private cdr = inject(ChangeDetectorRef);
  private host = inject(ElementRef<HTMLElement>);
  /** Shown when Google Maps is off and the page did not supply its own schematic. */
  readonly builtin = signal(false);

  @Input() pins: MapPin[] = [];
  @Input() legs: MapLeg[] = [];
  @Input() center: { lat: number; lng: number } = { lat: 10.50, lng: 76.30 };
  /** Bump this to pan again even when the centre numbers did not change. */
  @Input() focusToken = 0;
  /** Frame every pin and every line. When false, an open case's lines frame the map. */
  @Input() fitAll = false;
  @Output() pinSelect = new EventEmitter<string>();

  @ViewChild('canvas') canvas?: ElementRef<HTMLDivElement>;

  mode: 'google' | 'svg' = 'svg';
  private map: { panTo?: (pos: { lat: number; lng: number }) => void; fitBounds?: (bounds: unknown, padding?: number) => void } | null = null;
  private markers: { setMap?: (map: null) => void }[] = [];
  private lines: { setMap?: (map: null) => void }[] = [];
  private lastCenter: { lat: number; lng: number } | null = null;
  private lastToken = 0;

  ngAfterContentInit(): void {
    this.refreshBuiltin();
  }

  ngAfterViewInit(): void {
    this.maps.decide().then((mode) => {
      this.mode = mode;
      this.refreshBuiltin();
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
    this.refreshBuiltin();
    this.cdr.markForCheck();
  };

  /** A page schematic (Cases) wins. Otherwise this provider draws pins and legs. */
  private refreshBuiltin(): void {
    if (this.mode === 'google') {
      this.builtin.set(false);
      return;
    }
    const foreign = [...this.host.nativeElement.querySelectorAll('svg')].some(
      (node) => !node.classList.contains('rd-schematic'),
    );
    this.builtin.set(!foreign);
  }

  schematicPins(): { id: string; x: number; y: number; onLeg: boolean }[] {
    const frame = this.schematicFrame();
    const suggested = new Set(this.legs.filter((leg) => leg.suggested).map((leg) => `${leg.to.lat},${leg.to.lng}`));
    return this.pins.map((pin) => ({
      id: pin.id,
      ...this.toSvg(pin.lat, pin.lng, frame),
      onLeg: suggested.has(`${pin.lat},${pin.lng}`),
    }));
  }

  schematicLegs(): { id: string; x1: number; y1: number; x2: number; y2: number; lx: number; ly: number; title: string; suggested: boolean }[] {
    const frame = this.schematicFrame();
    return this.legs.map((leg) => {
      const from = this.toSvg(leg.from.lat, leg.from.lng, frame);
      const to = this.toSvg(leg.to.lat, leg.to.lng, frame);
      return {
        id: leg.id,
        x1: from.x,
        y1: from.y,
        x2: to.x,
        y2: to.y,
        lx: (from.x + to.x) / 2,
        ly: (from.y + to.y) / 2 - 8,
        title: leg.title,
        suggested: !!leg.suggested,
      };
    });
  }

  private schematicFrame(): { minLa: number; maxLa: number; minLo: number; maxLo: number } {
    const points = [
      ...this.pins.map((pin) => ({ lat: pin.lat, lng: pin.lng })),
      ...this.legs.flatMap((leg) => [leg.from, leg.to]),
    ];
    if (!points.length) return { minLa: 9.2, maxLa: 11.9, minLo: 75.85, maxLo: 76.85 };
    const lats = points.map((point) => point.lat);
    const lngs = points.map((point) => point.lng);
    const minLa = Math.min(...lats);
    const maxLa = Math.max(...lats);
    const minLo = Math.min(...lngs);
    const maxLo = Math.max(...lngs);
    const padLa = Math.max(0.02, (maxLa - minLa) * 0.2);
    const padLo = Math.max(0.02, (maxLo - minLo) * 0.2);
    return { minLa: minLa - padLa, maxLa: maxLa + padLa, minLo: minLo - padLo, maxLo: maxLo + padLo };
  }

  private toSvg(lat: number, lng: number, frame: { minLa: number; maxLa: number; minLo: number; maxLo: number }): { x: number; y: number } {
    return {
      x: 28 + ((lng - frame.minLo) / Math.max(1e-6, frame.maxLo - frame.minLo)) * 544,
      y: 28 + (1 - (lat - frame.minLa) / Math.max(1e-6, frame.maxLa - frame.minLa)) * 424,
    };
  }

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
      this.fitView(maps);
    } catch {
      this.mode = 'svg';
      this.map = null;
      this.cdr.markForCheck();
    }
  }

  /** A full pin set wins when asked. Otherwise lines frame the open case. */
  private fitView(maps: GoogleMapsNs): void {
    if (this.fitAll && (this.pins.length || this.legs.length)) {
      this.fitPins(maps);
      return;
    }
    if (this.legs.length) {
      this.fitToLegs(maps);
      return;
    }
    if (this.pins.length) this.fitPins(maps);
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

  private fitPins(maps: GoogleMapsNs): void {
    const points = [
      ...this.pins.map((pin) => ({ lat: pin.lat, lng: pin.lng })),
      ...this.legs.flatMap((leg) => [leg.from, leg.to]),
    ];
    if (!this.map?.fitBounds || !points.length || !maps.LatLngBounds) return;
    const bounds = new maps.LatLngBounds();
    for (const point of points) bounds.extend(point);
    if (points.length === 1) {
      const pin = points[0];
      bounds.extend({ lat: pin.lat + 0.02, lng: pin.lng + 0.02 });
      bounds.extend({ lat: pin.lat - 0.02, lng: pin.lng - 0.02 });
    }
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
