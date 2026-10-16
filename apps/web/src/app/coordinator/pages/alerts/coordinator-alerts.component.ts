import { ChangeDetectionStrategy, Component, OnInit, computed, effect, inject, input, signal, output } from '@angular/core';
import { CommonModule } from '@angular/common';
import { AnomalyAlert, ApiClientService, LanguageService, RdTranslatePipe } from '@rd/shared';
import { MapPin, MapProviderComponent } from '../../../core/maps/map-provider.component';
import { DeskStore } from '../../../core/desk-store';

type Kind = 'spike' | 'silent_zone' | 'resource_gap' | 'conflict' | 'stale';
interface Ward { id: string; name: string; district: string; lat: number; lng: number; }
interface Pt { x: number; y: number; }
interface Landmark { name: string; lat: number; lng: number; }
interface ResPin { id: string; name: string; lat: number; lng: number; free: boolean; }
export interface MapAlert {
  n: number; alert: AnomalyAlert; kind: Kind; at: Pt | null; ward?: Ward;
  stat?: string; claims?: [string, string]; window?: string; demand?: string;
}

const W = 800;
const H = 560;
const LAT_MAX = 11.70;
const LNG_MIN = 75.98;
const proj = (lat: number, lng: number): Pt => ({ x: (lng - LNG_MIN) * 1100, y: (LAT_MAX - lat) * 230 });

/** Real Kerala panchayats used by the synthetic flood pack. */
const WARDS: Ward[] = [
  { id: 'ward_1', name: 'Kainakary', district: 'Alappuzha', lat: 9.470, lng: 76.390 },
  { id: 'ward_2', name: 'Champakulam', district: 'Alappuzha', lat: 9.416, lng: 76.411 },
  { id: 'ward_3', name: 'Nedumudi', district: 'Alappuzha', lat: 9.430, lng: 76.398 },
  { id: 'ward_4', name: 'Aluva', district: 'Ernakulam', lat: 10.108, lng: 76.352 },
  { id: 'ward_5', name: 'Varapuzha', district: 'Ernakulam', lat: 10.078, lng: 76.268 },
  { id: 'ward_6', name: 'Kothamangalam', district: 'Ernakulam', lat: 10.065, lng: 76.628 },
  { id: 'ward_7', name: 'Chalakudy', district: 'Thrissur', lat: 10.308, lng: 76.331 },
  { id: 'ward_8', name: 'Mala', district: 'Thrissur', lat: 10.241, lng: 76.267 },
  { id: 'ward_9', name: 'Anthikad', district: 'Thrissur', lat: 10.466, lng: 76.130 },
  { id: 'ward_10', name: 'Meppadi', district: 'Wayanad', lat: 11.557, lng: 76.140 },
  { id: 'ward_11', name: 'Vythiri', district: 'Wayanad', lat: 11.550, lng: 76.038 },
  { id: 'ward_12', name: 'Kalpetta', district: 'Wayanad', lat: 11.608, lng: 76.082 },
];
const LANDMARKS: Landmark[] = [
  { name: 'Little Flower Hospital', lat: 10.108, lng: 76.352 },
  { name: 'Nedumudi Boat Jetty', lat: 9.430, lng: 76.398 },
  { name: 'Chalakudy River Jetty', lat: 10.308, lng: 76.331 },
  { name: 'Kainakary Relief Camp', lat: 9.470, lng: 76.390 },
];
const FALLBACK_MEDICAL: ResPin[] = [{ id: 'm1', name: 'Medical team', lat: 10.108, lng: 76.352, free: true }];

function clip(poly: Pt[], p: Pt, q: Pt): Pt[] {
  // keep points closer to p than to q
  const a = q.x - p.x, b = q.y - p.y, c = (q.x * q.x + q.y * q.y - p.x * p.x - p.y * p.y) / 2;
  const f = (pt: Pt) => a * pt.x + b * pt.y - c;
  const out: Pt[] = [];
  for (let i = 0; i < poly.length; i++) {
    const cur = poly[i], nxt = poly[(i + 1) % poly.length];
    const fc = f(cur), fn = f(nxt);
    if (fc <= 0) out.push(cur);
    if ((fc < 0 && fn > 0) || (fc > 0 && fn < 0)) {
      const t = fc / (fc - fn);
      out.push({ x: cur.x + t * (nxt.x - cur.x), y: cur.y + t * (nxt.y - cur.y) });
    }
  }
  return out;
}

const RAW_CELLS = WARDS.map((w) => {
  const p = proj(w.lat, w.lng);
  let poly: Pt[] = [{ x: 0, y: 0 }, { x: W, y: 0 }, { x: W, y: H }, { x: 0, y: H }];
  for (const o of WARDS) {
    if (o !== w) poly = clip(poly, p, proj(o.lat, o.lng));
  }
  const lines = [w.name];
  return { ward: w, c: p, d: poly.map((v) => `${v.x.toFixed(1)},${v.y.toFixed(1)}`).join(' '), lines };
});

function withLabelOffsets<T extends { c: Pt }>(cells: T[]): (T & { lx: number; ly: number })[] {
  const placed: Pt[] = [];
  return cells.map((cell) => {
    let dx = 0;
    let dy = 18;
    for (let n = 0; n < 8; n++) {
      const x = cell.c.x + dx;
      const y = cell.c.y + dy;
      const hit = placed.some((p) => Math.hypot(p.x - x, p.y - y) < 34);
      if (!hit) {
        dx = x - cell.c.x;
        dy = y - cell.c.y;
        break;
      }
      dx = (n % 2 === 0 ? 1 : -1) * (40 + n * 6);
      dy = 18 + (n + 1) * 16;
    }
    placed.push({ x: cell.c.x + dx, y: cell.c.y + dy });
    return { ...cell, lx: cell.c.x + dx, ly: cell.c.y + dy };
  });
}

const CELLS = withLabelOffsets(RAW_CELLS);

@Component({
  selector: 'app-coordinator-alerts',
  standalone: true,
  imports: [CommonModule, RdTranslatePipe, MapProviderComponent],
  templateUrl: './coordinator-alerts.component.html',
  styleUrl: './coordinator-alerts.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class CoordinatorAlertsComponent implements OnInit {
  private api = inject(ApiClientService);
  private lang = inject(LanguageService);
  private desk = inject(DeskStore);

  constructor() {
    effect(() => {
      if (!this.desk.alertsReady()) return;
      this.alerts.set(this.desk.alerts());
    });
  }
  /** Overview shows the list beside its own map. The alerts route keeps this map. */
  readonly listOnly = input(false);
  /** Overview frames its own map on the picked alert's ward. */
  readonly focus = output<{ id: string; ward_id: string | null; lat: number; lng: number } | null>();

  readonly W = W;
  readonly H = H;
  readonly cells = CELLS;
  readonly spikeRadius = 28;
  readonly landmarks = LANDMARKS.map((l) => ({ ...l, ...proj(l.lat, l.lng) }));
  readonly kinds: Kind[] = ['spike', 'silent_zone', 'resource_gap', 'conflict'];
  readonly alerts = signal<AnomalyAlert[]>([]);
  readonly medical = signal<ResPin[]>([]);
  readonly selectedId = signal<string | null>(null);
  readonly focusNonce = signal(0);
  readonly error = signal<string | null>(null);

  readonly items = computed<MapAlert[]>(() => this.alerts().map((a, i) => this.toItem(a, i + 1)));
  readonly selected = computed(() => this.items().find((i) => i.alert.id === this.selectedId()) ?? null);
  readonly medPins = computed(() => this.medical().map((r) => ({ ...r, ...proj(r.lat, r.lng) })));
  readonly selectedWard = computed(() => this.selected()?.ward?.id ?? null);

  /** Zoom on the selected location; everything else stays in place and dims. */
  readonly transform = computed(() => {
    const s = this.selected();
    const at = s?.at;
    if (!at) return 'translate(0px,0px) scale(1)';
    const k = 1.35;
    const tx = Math.min(0, Math.max(W - W * k, W / 2 - at.x * k));
    const ty = Math.min(0, Math.max(H - H * k, H / 2 - at.y * k));
    return `translate(${tx}px,${ty}px) scale(${k})`;
  });

  readonly googlePins = computed<MapPin[]>(() =>
    this.items().filter((i) => i.at).map((i) => ({ id: i.alert.id, ...this.latlng(i), title: `${i.n}. ${i.alert.title}` })),
  );
  readonly center = computed(() => {
    const s = this.selected();
    return s?.at ? this.latlng(s) : { lat: 10.50, lng: 76.30 };
  });

  isSample(alert: AnomalyAlert): boolean {
    return (alert.reason || '').startsWith('Sample.') || (alert.title || '').startsWith('Sample');
  }

  titleOf(alert: AnomalyAlert): string {
    this.lang.currentLang();
    const key = `alerts.k.${alert.kind}`;
    const text = this.lang.translate(key);
    return text === key ? (alert.title || alert.kind) : text;
  }

  /** Localise a known English reason. Unknown wording stays as stored. */
  reasonOf(alert: AnomalyAlert): string {
    this.lang.currentLang();
    const reason = (alert.reason || '').replace(/^Sample\.\s*/, '');
    const fill = (key: string, parts: Record<string, string>): string => {
      const template = this.lang.translate(key);
      if (template === key) return reason;
      return Object.entries(parts).reduce((text, [name, value]) => text.replace(`{${name}}`, value), template);
    };
    const spike = /^(.+?): (\d+) reports in (.+?) \(baseline ([^)]+)\)/.exec(reason);
    if (alert.kind === 'spike' && spike) {
      return fill('alerts.reasonSpike', { place: spike[1], n: spike[2], window: spike[3], base: spike[4] });
    }
    const silent = /^(.+?): 0 reports in ([^,]+)/.exec(reason);
    if (alert.kind === 'silent_zone' && silent) {
      return fill('alerts.reasonSilent', { place: silent[1], window: silent[2].trim() });
    }
    const gapNone = /^No (\w+) team free\. (\d+) cases are still waiting\./.exec(reason);
    if (gapNone) return fill('alerts.reasonGapNone', { kind: gapNone[1], n: gapNone[2] });
    const gap = /^(\w+) demand (\d+), only (\d+) free/.exec(reason);
    if (gap) return fill('alerts.reasonGapDemand', { kind: gap[1], demand: gap[2], free: gap[3] });
    const conflict = /^"(.+?)" vs "(.+?)" in (.+)$/.exec(reason);
    if (conflict) return fill('alerts.reasonConflict', { left: conflict[1], right: conflict[2], place: conflict[3] });
    const stale = /^(\d+) requests unconfirmed for (\d+) min/.exec(reason);
    if (stale) return fill('alerts.reasonStale', { n: stale[1], mins: stale[2] });
    return reason;
  }

  ageText(alert: AnomalyAlert): string {
    const stamp = alert.detected_at;
    if (!stamp) {
      return alert.age_label && alert.age_label !== 'sample' ? alert.age_label : '11 min ago';
    }
    const m = Math.max(1, Math.round((Date.now() - new Date(stamp).getTime()) / 60000));
    const key = m < 60 ? 'coord.updatedMin' : 'coord.updatedHour';
    const n = m < 60 ? m : Math.max(1, Math.round(m / 60));
    return this.lang.translate(key).replace('{n}', String(n));
  }

  ngOnInit(): void {
    this.reload();
    const res = (this.api as Partial<ApiClientService>).getResources?.('medical');
    res?.subscribe({
      next: (rows) => {
        const pins = (rows || [])
          .filter((r) => typeof r.lat === 'number' && typeof r.lng === 'number')
          .slice(0, 6)
          .map((r) => ({ id: String(r.id), name: String(r.name || 'Medical team'), lat: r.lat as number, lng: r.lng as number, free: (r.capacity_remaining ?? 1) > 0 && r.status !== 'busy' }));
        this.medical.set(pins.length ? pins : FALLBACK_MEDICAL);
      },
      error: () => this.medical.set(FALLBACK_MEDICAL),
    });
  }

  reload(): void {
    this.error.set(null);
    this.api.getAlerts().subscribe({
      next: (rows) => {
        this.alerts.set(rows);
        if (rows.length) this.selectedId.set(rows[0].id);
      },
      error: () => this.error.set('Could not load alerts.'),
    });
  }

  select(alert: AnomalyAlert): void {
    const again = this.listOnly() && this.selectedId() === alert.id;
    this.selectedId.set(again ? null : alert.id);
    const item = this.items().find((i) => i.alert.id === alert.id);
    if (again || !item || (!item.ward && !item.at)) {
      this.focus.emit(null);
      return;
    }
    const at = this.latlng(item);
    this.focus.emit({ id: alert.id, ward_id: item.ward?.id ?? alert.ward_id ?? null, lat: at.lat, lng: at.lng });
  }

  /** Focus the map on this alert, including when the row was already selected. */
  viewOnMap(alert: AnomalyAlert): void {
    this.select(alert);
    this.focusNonce.update((n) => n + 1);
    document.querySelector('.map-panel')?.scrollIntoView({ block: 'nearest', inline: 'nearest' });
  }

  acknowledge(alert: AnomalyAlert): void {
    this.api.acknowledgeAlert(alert.id).subscribe({
      next: (updated) => this.alerts.update((rows) => rows.map((row) => (row.id === updated.id ? updated : row))),
    });
  }

  private latlng(i: MapAlert): { lat: number; lng: number } {
    if (i.ward) return { lat: i.ward.lat, lng: i.ward.lng };
    const at = i.at as Pt;
    return { lat: LAT_MAX - at.y / 230, lng: LNG_MIN + at.x / 1100 };
  }

  private kindOf(a: AnomalyAlert): Kind {
    const k = a.kind;
    return k === 'spike' || k === 'silent_zone' || k === 'resource_gap' || k === 'conflict' ? k : 'stale';
  }

  private toItem(alert: AnomalyAlert, n: number): MapAlert {
    const kind = this.kindOf(alert);
    const m = /(\d+)/.exec(`${alert.ward_id ?? ''}`) || /Ward (\d+)/i.exec(alert.reason);
    const ward = m ? WARDS.find((w) => w.id === `ward_${m[1]}`) : undefined;
    const cell = ward ? CELLS.find((c) => c.ward === ward) : undefined;
    const item: MapAlert = { n, alert, kind, at: cell ? cell.c : null, ward };
    if (kind === 'spike') {
      const r = /(\d+) reports in ([\w ]+?)(?: \(|$)/.exec(alert.reason);
      item.stat = r ? r[1] : undefined;
      item.window = r ? r[2] : undefined;
    }
    if (kind === 'silent_zone') {
      item.window = (/in (\d+ ?h|\d+ min)/.exec(alert.reason) || [])[1] || '3 h';
    }
    if (kind === 'conflict') {
      const r = /"(.+?)" vs "(.+?)"/.exec(alert.reason);
      if (r) item.claims = [r[1], r[2]];
    }
    if (kind === 'resource_gap') {
      const pins = this.medical().length ? this.medical() : FALLBACK_MEDICAL;
      const free = pins.filter((p) => p.free);
      const base = (free.length ? free : pins).map((p) => proj(p.lat, p.lng));
      item.at = { x: base.reduce((s, p) => s + p.x, 0) / base.length, y: base.reduce((s, p) => s + p.y, 0) / base.length };
      item.demand = alert.reason;
    }
    return item;
  }

  trackId(_: number, i: MapAlert): string { return i.alert.id; }
  claimW(t: string): number { return Math.max(70, t.length * 8 + 22); }
}
