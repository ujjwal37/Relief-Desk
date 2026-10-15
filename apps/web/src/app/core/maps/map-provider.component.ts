import { RdTranslatePipe } from '@rd/shared';
import { CommonModule } from '@angular/common';
import { PINE_SAND_MAP_STYLE } from './pine-sand-map-style';
import { LatLng, panIfMoved } from './map-center';
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
import { markerDataUrl, TONE_COLOR, vehiclePath, PinTone, VehicleKind } from './map-markers';
import { MapProviderService } from './map-provider.service';
import { MarkerClusterer } from '@googlemaps/markerclusterer';

/** Road route for one team->case pair. Shared by every map so a leg is routed once. */
interface RoadRoute { path: { lat: number; lng: number }[]; km: string; mins: string; meters: number; seconds: number }
const ROUTES = new Map<string, Promise<RoadRoute | null>>();
let routingBroken = false;

export interface MapPin {
  id: string;
  lat: number;
  lng: number;
  title: string;
  /** Case pins take an urgency colour. Team pins take a vehicle glyph. */
  marker?: 'case' | 'team';
  vehicle?: VehicleKind;
  tone?: PinTone;
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
  imports: [CommonModule, RdTranslatePipe],
  template: `
    @if (loading()) {
      <div class="rd-map-loading" role="status"><span>{{ 'map.loading' | rdTranslate }}</span></div>
    }
    @if (mode === 'google') {
      <div #canvas class="rd-google-map" role="application" aria-label="Relief map"></div>
    } @else {
      <ng-content></ng-content>
      @if (builtin()) {
        <svg class="rd-schematic" viewBox="0 0 600 480" preserveAspectRatio="xMidYMid meet" role="img" aria-label="Relief map">
          <rect width="600" height="480" fill="var(--map-bg, #efeae0)"/>
          @for (leg of schematicLegs(); track leg.id) {
            <line [attr.x1]="leg.x1" [attr.y1]="leg.y1" [attr.x2]="leg.x2" [attr.y2]="leg.y2" [attr.stroke]="leg.stroke" [attr.stroke-width]="leg.width" stroke-linecap="round"/>
            @if (leg.title) {
              <text class="rd-leg" [attr.x]="leg.lx" [attr.y]="leg.ly" text-anchor="middle">{{ leg.title }}</text>
            }
          }
          @for (pin of schematicPins(); track pin.id) {
            <g [attr.transform]="'translate(' + pin.x + ' ' + pin.y + ')'" [attr.opacity]="pin.opacity">
              <circle r="11" [attr.fill]="pin.fill" stroke="#fff" stroke-width="2"/>
              @if (pin.path) {
                <path [attr.d]="pin.path" fill="#fff" transform="translate(-12 -12)"/>
              }
            </g>
          }
        </svg>
      }
    }
  `,
  styles: [`
    :host { display: block; width: 100%; height: 100%; min-height: 250px; position: relative; }
    .rd-google-map, .rd-schematic { position: absolute; inset: 0; width: 100%; height: 100%; min-height: 250px; display: block; }
    .rd-map-loading { position: absolute; inset: 0; z-index: 5; display: grid; place-items: center; pointer-events: none; background: linear-gradient(90deg, var(--surface-2) 25%, var(--border) 50%, var(--surface-2) 75%); background-size: 200% 100%; animation: rd-map-pulse 1.8s ease-in-out infinite; }
    .rd-map-loading span { background: var(--surface); color: var(--text); padding: 8px 14px; border-radius: 999px; font-size: 13px; }
    @keyframes rd-map-pulse { to { background-position: -200% 0; } }
    @media (prefers-reduced-motion: reduce) { .rd-map-loading { animation: none; } }
    .rd-leg { font-size: 13px; font-weight: 700; fill: #0f1720; }
  `],
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class MapProviderComponent implements AfterContentInit, AfterViewInit, OnChanges, OnDestroy {
  private maps = inject(MapProviderService);
  private cdr = inject(ChangeDetectorRef);
  private host = inject(ElementRef<HTMLElement>);
  /** Shown when Google Maps is off and the page did not supply its own schematic. */
  readonly builtin = signal(false);
  readonly loading = signal(true);
  private destroyed = false;
  private loadTimer?: ReturnType<typeof setTimeout>;
  private readyListener?: { remove: () => void };

  @Input() pins: MapPin[] = [];
  @Input() legs: MapLeg[] = [];
  @Input() center: { lat: number; lng: number } = { lat: 10.50, lng: 76.30 };
  /** Bump this to pan again even when the centre numbers did not change. */
  @Input() focusToken = 0;
  /** Frame every pin and every line. When false, an open case's lines frame the map. */
  @Input() fitAll = false;
  /** Team id whose line should draw thicker while its row is hovered. */
  @Input() highlightId: string | null = null;
  /** Group case pins into urgency-coloured clusters (Overview). */
  @Input() cluster = false;
  @Output() pinSelect = new EventEmitter<string>();

  @ViewChild('canvas') canvas?: ElementRef<HTMLDivElement>;

  mode: 'google' | 'svg' = 'svg';
  private map: { panTo?: (pos: { lat: number; lng: number }) => void; fitBounds?: (bounds: unknown, padding?: number) => void } | null = null;
  private markers: { setMap?: (map: null) => void }[] = [];
  private lines: { setMap?: (map: null) => void }[] = [];
  private clusterer: MarkerClusterer | null = null;
  private drawSeq = 0;
  private lastToken = 0;
  private gaveUp = false;
  private lastPinKey = '';
  private lastCenter: LatLng | null = null;

  ngAfterContentInit(): void {
    this.refreshBuiltin();
  }

  ngAfterViewInit(): void {
    const w = window as unknown as { gm_authFailure?: () => void };
    w.gm_authFailure = () => this.fallBackToSvg();
    this.maps.decide().then((mode) => {
      if (this.destroyed) return;
      if (this.gaveUp || this.maps.authFailed || mode !== 'google') {
        this.mode = 'svg';
        this.loading.set(false);
        this.refreshBuiltin();
        this.cdr.markForCheck();
        return;
      }
      this.mode = 'google';
      this.refreshBuiltin();
      this.cdr.detectChanges();
      this.draw();
      this.loadTimer = setTimeout(() => { this.fallbackIfBroken(); this.loading.set(false); }, 6000);
    });
    window.addEventListener('offline', this.onOffline);
  }

  ngOnDestroy(): void {
    this.destroyed = true;
    clearTimeout(this.loadTimer);
    this.readyListener?.remove();
    this.markers.forEach((marker) => marker.setMap?.(null));
    this.lines.forEach((line) => line.setMap?.(null));
    this.clusterer?.clearMarkers();
    window.removeEventListener('offline', this.onOffline);
  }

  ngOnChanges(): void {
    if (this.gaveUp || !this.map) {
      return;
    }
    const force = this.focusToken !== this.lastToken;
    this.lastToken = this.focusToken;
    if (force && Number.isFinite(this.center?.lat) && Number.isFinite(this.center?.lng)) {
      this.map.panTo?.(this.center);
      this.lastCenter = { lat: this.center.lat, lng: this.center.lng };
    } else {
      this.lastCenter = panIfMoved(this.map, this.lastCenter, this.center);
    }
    const pinKey = this.pins.map((pin) => `${pin.id}:${pin.lat}:${pin.lng}`).join('|') + '#' + JSON.stringify(this.legs ?? []) + '#' + (this.highlightId || '');
    if (this.mode !== 'google' || pinKey === this.lastPinKey) {
      return;
    }
    this.draw();
  }

  private onOffline = (): void => {
    this.fallBackToSvg();
  };

  private fallBackToSvg(): void {
    this.loading.set(false);
    clearTimeout(this.loadTimer);
    this.readyListener?.remove();
    this.gaveUp = true;
    this.maps.authFailed = true;
    this.mode = 'svg';
    this.map = null;
    this.refreshBuiltin();
    this.markers = [];
    this.cdr.markForCheck();
  }

  private fallbackIfBroken(): void {
    const text = this.canvas?.nativeElement?.innerText || '';
    if (text.includes('Oops') || text.includes("didn't load")) {
      this.fallBackToSvg();
    }
  }

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

  schematicPins(): { id: string; x: number; y: number; fill: string; opacity: number; path: string }[] {
    const frame = this.schematicFrame();
    const suggested = new Set(this.legs.filter((leg) => leg.suggested).map((leg) => `${leg.to.lat},${leg.to.lng}`));
    return this.pins.map((pin) => {
      const onLeg = suggested.has(`${pin.lat},${pin.lng}`);
      const fill = pin.tone ? TONE_COLOR[pin.tone] : (onLeg ? '#047857' : '#0f1720');
      return {
        id: pin.id,
        ...this.toSvg(pin.lat, pin.lng, frame),
        fill,
        opacity: pin.tone === 'stale' ? 0.4 : 1,
        path: vehiclePath(pin.vehicle),
      };
    });
  }

  schematicLegs(): { id: string; x1: number; y1: number; x2: number; y2: number; lx: number; ly: number; title: string; stroke: string; width: number }[] {
    const frame = this.schematicFrame();
    return this.legs.map((leg) => {
      const from = this.toSvg(leg.from.lat, leg.from.lng, frame);
      const to = this.toSvg(leg.to.lat, leg.to.lng, frame);
      const hot = !!this.highlightId && this.highlightId === leg.id;
      return {
        id: leg.id,
        x1: from.x,
        y1: from.y,
        x2: to.x,
        y2: to.y,
        lx: (from.x + to.x) / 2,
        ly: (from.y + to.y) / 2 - 8,
        title: leg.title,
        stroke: leg.suggested ? '#047857' : '#6b7280',
        width: leg.suggested ? (hot ? 6 : 4) : (hot ? 5 : 2),
      };
    });
  }

  private schematicFrame(): { minLa: number; maxLa: number; minLo: number; maxLo: number } {
    const focused = !this.fitAll && this.legs.length > 0;
    const points = focused
      ? this.legs.flatMap((leg) => [leg.from, leg.to])
      : [
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
      this.loading.set(false);
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
          styles: PINE_SAND_MAP_STYLE,
        });
        const ready = () => {
          this.loading.set(false);
          clearTimeout(this.loadTimer);
          this.cdr.markForCheck();
        };
        this.readyListener = maps.event?.addListenerOnce(this.map, 'tilesloaded', ready);
        maps.event?.addListenerOnce(this.map, 'idle', ready);
        this.lastCenter = { lat: this.center.lat, lng: this.center.lng };
      }
      const pinKey = this.pins.map((pin) => `${pin.id}:${pin.lat}:${pin.lng}`).join('|') + '#' + JSON.stringify(this.legs ?? []) + '#' + (this.highlightId || '');
      this.lastPinKey = pinKey;
      this.markers.forEach((marker) => marker.setMap?.(null));
      this.lines.forEach((line) => line.setMap?.(null));
      this.clusterer?.clearMarkers();
      const seq = ++this.drawSeq;
      this.lines = this.legs.map((leg) => {
        const hot = !!this.highlightId && this.highlightId === leg.id;
        return new maps.Polyline({
          map: this.map,
          path: [leg.from, leg.to],
          strokeColor: leg.suggested ? '#047857' : '#6b7280',
          strokeWeight: leg.suggested ? (hot ? 6 : 4) : (hot ? 5 : 2),
          geodesic: true,
        });
      });
      const labelFor = new Map<string, unknown>();
      const labels = this.legs.filter((leg) => leg.title).map((leg) => { const m = new maps.Marker({
        map: this.map,
        position: { lat: (leg.from.lat + leg.to.lat) / 2, lng: (leg.from.lng + leg.to.lng) / 2 },
        label: {
          text: leg.title,
          color: '#fff',
          className: 'rd-distance-pill',
          fontSize: '12px',
          fontWeight: '700',
        },
        icon: { path: maps.SymbolPath?.CIRCLE ?? 0, scale: 0, labelOrigin: maps.Point ? new maps.Point(0, -22) : undefined },
        clickable: false,
      }); labelFor.set(leg.id, m); return m; });
      const clustered: unknown[] = [];
      this.markers = this.pins.map((pin) => {
        const url = markerDataUrl(pin);
        const icon = url
          ? {
              url,
              scaledSize: maps.Size ? new maps.Size(32, 32) : undefined,
              anchor: maps.Point ? new maps.Point(16, 16) : undefined,
            }
          : undefined;
        const grouped = this.cluster && pin.marker === 'case';
        const marker = new maps.Marker({
          map: grouped ? null : this.map,
          position: { lat: pin.lat, lng: pin.lng },
          title: pin.title,
          ...(icon ? { icon } : {}),
        });
        marker.addListener?.('click', () => this.pinSelect.emit(pin.id));
        if (grouped) clustered.push(marker);
        return marker;
      });
      this.markers.push(...labels);
      if (this.cluster && clustered.length) this.clusterPins(clustered);
      this.routeLegs(maps, seq, labelFor);
      this.fitView(maps);
    } catch {
      this.mode = 'svg';
      this.loading.set(false);
      this.map = null;
      this.cdr.markForCheck();
    }
  }

  /** Urgency-coloured clusters: the colour is the most urgent case inside. */
  private clusterPins(markers: unknown[]): void {
    const rank: Record<string, number> = { critical: 4, high: 3, medium: 2, low: 1 };
    const tones = new Map<unknown, string>();
    this.pins.filter((p) => p.marker === 'case').forEach((p, i) => tones.set(markers[i], p.tone || 'low'));
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const g = (window as any).google;
    this.clusterer = new MarkerClusterer({
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      map: this.map as any,
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      markers: markers as any,
      renderer: {
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        render: ({ count, position, markers: inside }: any) => {
          let top = 'low';
          for (const m of inside || []) {
            const t = tones.get(m) || 'low';
            if ((rank[t] || 0) > (rank[top] || 0)) top = t;
          }
          const color = TONE_COLOR[top as PinTone] || TONE_COLOR.low;
          const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="44" height="44"><circle cx="22" cy="22" r="18" fill="${color}" fill-opacity="0.92" stroke="#fff" stroke-width="3"/></svg>`;
          return new g.maps.Marker({
            position,
            icon: { url: 'data:image/svg+xml;charset=UTF-8,' + encodeURIComponent(svg), scaledSize: new g.maps.Size(44, 44), anchor: new g.maps.Point(22, 22) },
            label: { text: String(count), color: '#fff', fontSize: '13px', fontWeight: '700' },
            zIndex: 1000 + count,
          });
        },
      },
    });
  }

  /** Swap each straight line for the road route and its drive time. Straight stays on failure. */
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  private routeLegs(maps: any, seq: number, labelFor: Map<string, unknown>): void {
    if (routingBroken || !maps.DirectionsService || !this.legs.length) return;
    const service = new maps.DirectionsService();
    this.legs.forEach((leg, i) => {
      const key = `${leg.to.lat.toFixed(5)},${leg.to.lng.toFixed(5)}>${leg.from.lat.toFixed(5)},${leg.from.lng.toFixed(5)}`;
      let job = ROUTES.get(key);
      if (!job) {
        job = new Promise<RoadRoute | null>((resolve) => {
          try {
            service.route(
              { origin: leg.to, destination: leg.from, travelMode: maps.TravelMode?.DRIVING ?? 'DRIVING' },
              // eslint-disable-next-line @typescript-eslint/no-explicit-any
              (res: any, status: string) => {
                const r = res?.routes?.[0];
                const l = r?.legs?.[0];
                if (status !== 'OK' || !r || !l) {
                  if (status === 'REQUEST_DENIED') routingBroken = true;
                  resolve(null);
                  return;
                }
                // eslint-disable-next-line @typescript-eslint/no-explicit-any
                const path = (r.overview_path || []).map((p: any) => ({ lat: p.lat(), lng: p.lng() }));
                resolve({ path, km: l.distance?.text || '', mins: l.duration?.text || '', meters: l.distance?.value || 0, seconds: l.duration?.value || 0 });
              },
            );
          } catch {
            resolve(null);
          }
        });
        ROUTES.set(key, job);
        job.then((r) => { if (!r) ROUTES.delete(key); });
      }
      job.then((route) => {
        if (!route || seq !== this.drawSeq || this.destroyed || !route.path.length) return;
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        const line = this.lines[i] as any;
        line?.setOptions?.({ path: route.path, geodesic: false });
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        const label = labelFor.get(leg.id) as any;
        if (label) {
          const mid = route.path[Math.floor(route.path.length / 2)];
          label.setPosition?.(mid);
          const cur = label.getLabel?.() || {};
          label.setLabel?.({ ...cur, text: `${route.km} · ${route.mins} drive` });
        }
      });
    });
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
  event?: { addListenerOnce: (target: unknown, event: string, callback: () => void) => { remove: () => void } };
  Map: new (el: HTMLElement, opts: Record<string, unknown>) => {
    panTo?: (pos: { lat: number; lng: number }) => void;
    fitBounds?: (bounds: unknown, padding?: number) => void;
  };
  LatLngBounds?: new () => { extend: (pos: { lat: number; lng: number }) => void };
  DirectionsService?: new () => unknown;
  TravelMode?: { DRIVING: string };
  Marker: new (opts: Record<string, unknown>) => { setMap?: (map: null) => void; addListener?: (event: string, fn: () => void) => void };
  Polyline: new (opts: Record<string, unknown>) => { setMap?: (map: null) => void };
  SymbolPath?: { CIRCLE: number };
  Size?: new (width: number, height: number) => { width: number; height: number };
  Point?: new (x: number, y: number) => { x: number; y: number };
}
