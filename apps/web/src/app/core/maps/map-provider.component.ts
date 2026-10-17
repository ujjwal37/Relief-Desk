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
import { boatMinutes, haversineKm, markerDataUrl, TONE_COLOR, vehiclePath, PinTone, VehicleKind } from './map-markers';
import { MapProviderService } from './map-provider.service';
import { computeRoadRoute, RoadRoute, RoutingDeniedError } from './road-route';
import { MarkerClusterer } from '@googlemaps/markerclusterer';

/** Points near the median, so one far-off team does not shrink the whole map. Off-frame pins stay drawn at the edge. */
function mainCluster(points: { lat: number; lng: number }[]): { lat: number; lng: number }[] {
  if (points.length < 4) return points;
  const med = (xs: number[]) => { const s = [...xs].sort((a, b) => a - b); return s[Math.floor(s.length / 2)]; };
  const mLat = med(points.map((p) => p.lat)); const mLng = med(points.map((p) => p.lng));
  const dist = points.map((p) => Math.hypot(p.lat - mLat, p.lng - mLng));
  const cut = Math.max(0.15, med(dist) * 2.5);
  const kept = points.filter((_, i) => dist[i] <= cut);
  return kept.length >= 2 ? kept : points;
}

/** Road route for one team->case pair. Shared by every map so a leg is routed once. */
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
  /** water: a boat leg. Dashed straight line, never a driving route. */
  mode?: 'road' | 'water';
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
      @if (routing() > 0) {
        <div class="rd-route-loading" role="status"><i aria-hidden="true"></i>{{ 'map.routing' | rdTranslate }}</div>
      }
    } @else {
      <div class="rd-zoom-wrap" [style.transform]="'scale(' + zoom() + ')'"><ng-content></ng-content>
      @if (builtin()) {
        <svg class="rd-schematic" viewBox="0 0 600 480" preserveAspectRatio="xMidYMid meet" role="img" aria-label="Relief map">
          <rect width="600" height="480" fill="var(--map-bg, #efeae0)"/>
          @for (leg of schematicLegs(); track leg.id) {
            <line [attr.x1]="leg.x1" [attr.y1]="leg.y1" [attr.x2]="leg.x2" [attr.y2]="leg.y2" [attr.stroke]="leg.stroke" [attr.stroke-width]="leg.width" [attr.stroke-dasharray]="leg.dash" stroke-linecap="round"/>
            @if (leg.title) {
              <text class="rd-leg" [attr.x]="leg.lx" [attr.y]="leg.ly" text-anchor="middle">{{ leg.title }}</text>
            }
          }
          @for (pin of schematicPins(); track pin.id) {
            <g [attr.transform]="'translate(' + pin.x + ' ' + pin.y + ')'" [attr.opacity]="pin.opacity">
              <circle r="16" [attr.fill]="pin.fill" stroke="#fff" stroke-width="2.5"/>
              @if (pin.path) {
                <path [attr.d]="pin.path" fill="#fff" transform="translate(-12 -12)"/>
              }
            </g>
          }
        </svg>
      }
      </div>
      <div class="rd-zoom" role="group" [attr.aria-label]="'map.zoom' | rdTranslate">
        <button type="button" data-testid="map-zoom-in" (click)="zoomBy(1)" [attr.aria-label]="'map.zoomIn' | rdTranslate">+</button>
        <button type="button" data-testid="map-zoom-out" (click)="zoomBy(-1)" [attr.aria-label]="'map.zoomOut' | rdTranslate">−</button>
      </div>
    }
  `,
  styles: [`
    :host { display: block; width: 100%; height: 100%; min-height: 250px; position: relative; overflow: hidden; background: var(--map-bg, #efeae0); }
    .rd-zoom-wrap { position: absolute; inset: 0; transform-origin: 50% 50%; transition: transform .2s ease; }
    .rd-zoom { position: absolute; right: 10px; top: 56px; z-index: 7; display: flex; flex-direction: column; gap: 4px; }
    .rd-zoom button { width: 34px; height: 34px; border-radius: 8px; border: 1px solid var(--border); background: var(--surface); color: var(--text); font-size: 18px; font-weight: 700; cursor: pointer; }
    .rd-zoom button:focus-visible { outline: 2px solid var(--focus, #1b3c53); }
    .rd-google-map, .rd-schematic { position: absolute; inset: 0; width: 100%; height: 100%; min-height: 250px; display: block; }
    .rd-map-loading { position: absolute; inset: 0; z-index: 5; display: grid; place-items: center; pointer-events: none; background: linear-gradient(90deg, var(--surface-2) 25%, var(--border) 50%, var(--surface-2) 75%); background-size: 200% 100%; animation: rd-map-pulse 1.8s ease-in-out infinite; }
    .rd-map-loading span { background: var(--surface); color: var(--text); padding: 8px 14px; border-radius: 999px; font-size: 13px; }
    @keyframes rd-map-pulse { to { background-position: -200% 0; } }
    @media (prefers-reduced-motion: reduce) { .rd-map-loading { animation: none; } }
    .rd-leg { font-size: 13px; font-weight: 700; fill: var(--text); paint-order: stroke; stroke: var(--surface); stroke-width: 4px; stroke-linejoin: round; }
    .rd-route-loading { position: absolute; z-index: 6; top: 10px; left: 50%; transform: translateX(-50%); display: inline-flex; align-items: center; gap: 8px; padding: 6px 12px; border-radius: 999px; background: var(--surface); color: var(--text); border: 1px solid var(--border); box-shadow: var(--e1); font-size: 12px; font-weight: 600; pointer-events: none; }
    .rd-route-loading i { width: 12px; height: 12px; border-radius: 50%; border: 2px solid var(--border); border-top-color: var(--brand, #166534); animation: rd-spin .8s linear infinite; }
    @keyframes rd-spin { to { transform: rotate(360deg); } }
    @media (prefers-reduced-motion: reduce) { .rd-route-loading i { animation: none; } }
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
  /** Zoom for the drawn fallback map (Google Maps has its own controls). */
  readonly zoom = signal(1);
  zoomBy(step: number): void { this.zoom.set(Math.min(3, Math.max(1, +(this.zoom() + step * 0.5).toFixed(1)))); }
  /** Road routes still on their way. Lines stay hidden until theirs arrives. */
  readonly routing = signal(0);
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
  /** Pin drawn larger and on top, kept out of clusters, and framed when no line is drawn. */
  @Input() selectedId: string | null = null;
  /** The page draws its own schematic, so never draw the built-in one over it. */
  @Input() ownSchematic = false;
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
    const pinKey = this.pins.map((pin) => `${pin.id}:${pin.lat}:${pin.lng}`).join('|') + '#' + JSON.stringify(this.legs ?? []) + '#' + (this.highlightId || '') + '#' + (this.selectedId || '');
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
    if (text.includes('Oops') || text.includes("didn't load") || /limit reached|quota|for development purposes/i.test(text)) {
      this.fallBackToSvg();
    }
  }

  /** A page schematic (Cases) wins. Otherwise this provider draws pins and legs. */
  private refreshBuiltin(): void {
    if (this.mode === 'google') {
      this.builtin.set(false);
      return;
    }
    const foreign = this.ownSchematic || [...this.host.nativeElement.querySelectorAll('svg')].some(
      (node) => !node.classList.contains('rd-schematic'),
    );
    this.builtin.set(!foreign);
  }

  schematicPins(): { id: string; x: number; y: number; fill: string; opacity: number; path: string }[] {
    const frame = this.schematicFrame();
    const suggested = new Set(this.legs.filter((leg) => leg.suggested).map((leg) => `${leg.to.lat},${leg.to.lng}`));
    return this.pins.map((pin) => {
      const onLeg = suggested.has(`${pin.lat},${pin.lng}`);
      const fill = pin.tone ? TONE_COLOR[pin.tone] : (onLeg ? '#166534' : '#0f1720');
      return {
        id: pin.id,
        ...this.toSvg(pin.lat, pin.lng, frame),
        fill,
        opacity: pin.tone === 'stale' ? 0.4 : 1,
        path: vehiclePath(pin.vehicle),
      };
    });
  }

  schematicLegs(): { id: string; x1: number; y1: number; x2: number; y2: number; lx: number; ly: number; title: string; stroke: string; width: number; dash: string | null }[] {
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
        title: this.legLabel(leg),
        dash: leg.mode === 'water' ? '8 6' : null,
        stroke: leg.suggested ? '#166534' : '#6b7280',
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
    const cluster = focused ? points : mainCluster(points);
    const lats = cluster.map((point) => point.lat);
    const lngs = cluster.map((point) => point.lng);
    const minLa = Math.min(...lats);
    const maxLa = Math.max(...lats);
    const minLo = Math.min(...lngs);
    const maxLo = Math.max(...lngs);
    const padLa = Math.max(0.02, (maxLa - minLa) * 0.2);
    const padLo = Math.max(0.02, (maxLo - minLo) * 0.2);
    return { minLa: minLa - padLa, maxLa: maxLa + padLa, minLo: minLo - padLo, maxLo: maxLo + padLo };
  }

  private toSvg(lat: number, lng: number, frame: { minLa: number; maxLa: number; minLo: number; maxLo: number }): { x: number; y: number } {
    const x = 28 + ((lng - frame.minLo) / Math.max(1e-6, frame.maxLo - frame.minLo)) * 544;
    const y = 28 + (1 - (lat - frame.minLa) / Math.max(1e-6, frame.maxLa - frame.minLa)) * 424;
    return { x: Math.min(584, Math.max(16, x)), y: Math.min(464, Math.max(16, y)) };
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
        this.lastCenter = { lat: this.center.lat, lng: this.center.lng };
      }
      const pinKey = this.pins.map((pin) => `${pin.id}:${pin.lat}:${pin.lng}`).join('|') + '#' + JSON.stringify(this.legs ?? []) + '#' + (this.highlightId || '') + '#' + (this.selectedId || '');
      this.lastPinKey = pinKey;
      this.markers.forEach((marker) => marker.setMap?.(null));
      this.lines.forEach((line) => line.setMap?.(null));
      this.clusterer?.clearMarkers();
      const seq = ++this.drawSeq;
      const waitForRoad = !routingBroken;
      this.lines = this.legs.map((leg) => {
        const hot = !!this.highlightId && this.highlightId === leg.id;
        return new maps.Polyline({
          map: this.map,
          path: [leg.from, leg.to],
          strokeColor: leg.suggested ? '#166534' : '#6b7280',
          strokeWeight: leg.suggested ? (hot ? 6 : 4) : (hot ? 5 : 2),
          geodesic: true,
          visible: !waitForRoad || leg.mode === 'water',
          ...(leg.mode === 'water' ? {
            strokeOpacity: 0,
            icons: [{ icon: { path: 'M 0,-1 0,1', strokeOpacity: 1, strokeColor: leg.suggested ? '#234c6a' : '#6b7280', scale: leg.suggested ? 4 : 3 }, offset: '0', repeat: '14px' }],
          } : {}),
        });
      });
      const labelFor = new Map<string, unknown>();
      const labels = this.legs.filter((leg) => leg.title).map((leg) => { const m = new maps.Marker({
        map: this.map,
        position: { lat: (leg.from.lat + leg.to.lat) / 2, lng: (leg.from.lng + leg.to.lng) / 2 },
        label: {
          text: this.legLabel(leg),
          color: '#fff',
          className: 'rd-distance-pill',
          fontSize: '12px',
          fontWeight: '700',
        },
        icon: { path: maps.SymbolPath?.CIRCLE ?? 0, scale: 0, labelOrigin: maps.Point ? new maps.Point(0, -38) : undefined },
        zIndex: 9999,
        clickable: false,
        visible: !waitForRoad || leg.mode === 'water',
      }); labelFor.set(leg.id, m); return m; });
      const clustered: unknown[] = [];
      this.markers = this.pins.map((pin) => {
        const hot = !!this.selectedId && pin.id === this.selectedId;
        const url = markerDataUrl(pin);
        const icon = url
          ? {
              url,
              scaledSize: maps.Size ? new maps.Size(hot ? 46 : 32, hot ? 46 : 32) : undefined,
              anchor: maps.Point ? new maps.Point(hot ? 23 : 16, hot ? 23 : 16) : undefined,
            }
          : undefined;
        const grouped = this.cluster && pin.marker === 'case' && !hot;
        const marker = new maps.Marker({
          map: grouped ? null : this.map,
          position: { lat: pin.lat, lng: pin.lng },
          title: pin.title,
          zIndex: hot ? 2000 : undefined,
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
  private routeLegs(_maps: any, seq: number, labelFor: Map<string, unknown>): void {
    if (!this.legs.length) { this.routing.set(0); return; }
    const roadCount = this.legs.filter((leg) => leg.mode !== 'water').length;
    if (routingBroken || !roadCount) { this.routing.set(0); return; }
    this.routing.set(roadCount);
    this.legs.forEach((leg, i) => {
      if (leg.mode === 'water') return;
      const key = `${leg.to.lat.toFixed(5)},${leg.to.lng.toFixed(5)}>${leg.from.lat.toFixed(5)},${leg.from.lng.toFixed(5)}`;
      let job = ROUTES.get(key);
      if (!job) {
        job = computeRoadRoute(leg.to, leg.from, this.maps.apiKey).catch((err) => {
          if (err instanceof RoutingDeniedError) routingBroken = true;
          return null;
        });
        ROUTES.set(key, job);
        job.then((r) => { if (!r) ROUTES.delete(key); });
      }
      job.then((route) => {
        if (seq !== this.drawSeq || this.destroyed) return;
        this.routing.update((n) => Math.max(0, n - 1));
        this.cdr.markForCheck();
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        const line = this.lines[i] as any;
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        const label = labelFor.get(leg.id) as any;
        if (!route || !route.path.length) {
          // Routing really failed: fall back to the straight line and its estimate.
          line?.setVisible?.(true);
          label?.setVisible?.(true);
          return;
        }
        line?.setOptions?.({ path: route.path, geodesic: false, visible: true });
        if (this.legs.length === 1 || leg.suggested) this.fitPath(route.path);
        if (label) {
          label.setVisible?.(true);
          const mid = route.path[Math.floor(route.path.length / 2)];
          label.setPosition?.(mid);
          const cur = label.getLabel?.() || {};
          label.setLabel?.({ ...cur, text: `~${route.mins} drive · ${route.km}` });
        }
      });
    });
  }

  /** Boats go by water: straight distance, never a drive time. */
  private legLabel(leg: MapLeg): string {
    if (leg.mode !== 'water') return leg.title;
    const km = haversineKm(leg.from.lat, leg.from.lng, leg.to.lat, leg.to.lng);
    const d = km < 10 ? km.toFixed(1) : String(Math.round(km));
    return km <= 30 ? `Boat · ~${boatMinutes(km)} min · ${d} km straight` : `Boat · ${d} km straight`;
  }

  private fitPath(path: { lat: number; lng: number }[]): void {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const g = (window as any).google?.maps;
    if (!this.map?.fitBounds || !g?.LatLngBounds || !path.length) return;
    const bounds = new g.LatLngBounds();
    path.forEach((p) => bounds.extend(p));
    this.map.fitBounds(bounds, 56);
  }

  /** A full pin set wins when asked. Otherwise lines frame the open case. */
  private fitView(maps: GoogleMapsNs): void {
    const chosen = this.selectedId ? this.pins.find((p) => p.id === this.selectedId) : null;
    if (chosen && !this.legs.length) {
      this.map?.panTo?.({ lat: chosen.lat, lng: chosen.lng });
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      (this.map as any)?.setZoom?.(14);
      return;
    }
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
  Marker: new (opts: Record<string, unknown>) => { setMap?: (map: null) => void; addListener?: (event: string, fn: () => void) => void };
  Polyline: new (opts: Record<string, unknown>) => { setMap?: (map: null) => void };
  SymbolPath?: { CIRCLE: number };
  Size?: new (width: number, height: number) => { width: number; height: number };
  Point?: new (x: number, y: number) => { x: number; y: number };
}
