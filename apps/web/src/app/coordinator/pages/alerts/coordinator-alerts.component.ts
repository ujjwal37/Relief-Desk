import { ChangeDetectionStrategy, Component, OnInit, computed, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { AnomalyAlert, ApiClientService, RdTranslatePipe } from '@rd/shared';
import { MapPin, MapProviderComponent } from '../../../core/maps/map-provider.component';

type Kind = 'spike' | 'silent_zone' | 'resource_gap' | 'conflict' | 'stale';
interface Ward { id: string; name: string; lat: number; lng: number; }
interface Pt { x: number; y: number; }
interface Landmark { name: string; lat: number; lng: number; }
interface ResPin { id: string; name: string; lat: number; lng: number; free: boolean; }
export interface MapAlert {
  n: number; alert: AnomalyAlert; kind: Kind; at: Pt | null; ward?: Ward;
  stat?: string; claims?: [string, string]; window?: string; demand?: string;
}

const W = 800;
const H = 560;
const LAT_MAX = 26.874;
const LNG_MIN = 80.92;
const proj = (lat: number, lng: number): Pt => ({ x: (lng - LNG_MIN) * 12500, y: (LAT_MAX - lat) * 11667 });

/** Synthetic Riverbend wards (same seeds as the demo data). */
const WARDS: Ward[] = [
  { id: 'ward_1', name: 'Sangam Vihar', lat: 26.845, lng: 80.932 },
  { id: 'ward_2', name: 'Gandhi Nagar', lat: 26.852, lng: 80.925 },
  { id: 'ward_3', name: 'Riverfront Ghat', lat: 26.839, lng: 80.941 },
  { id: 'ward_4', name: 'Old Bazaar', lat: 26.858, lng: 80.948 },
  { id: 'ward_5', name: 'Shanti Nagar', lat: 26.861, lng: 80.936 },
  { id: 'ward_6', name: 'Civil Lines', lat: 26.849, lng: 80.955 },
  { id: 'ward_7', name: 'Industrial Area', lat: 26.834, lng: 80.962 },
  { id: 'ward_8', name: 'Green Park', lat: 26.866, lng: 80.951 },
  { id: 'ward_9', name: 'Subhash Nagar', lat: 26.842, lng: 80.97 },
  { id: 'ward_10', name: 'Model Town', lat: 26.87, lng: 80.928 },
  { id: 'ward_11', name: 'Transport Nagar', lat: 26.828, lng: 80.98 },
  { id: 'ward_12', name: 'Lake View', lat: 26.869, lng: 80.972 },
];
const LANDMARKS: Landmark[] = [
  { name: 'Civil Hospital', lat: 26.8535, lng: 80.9425 },
  { name: 'Ram Ghat', lat: 26.8392, lng: 80.945 },
  { name: 'Railway station', lat: 26.8465, lng: 80.9625 },
  { name: 'Relief camp (school)', lat: 26.8635, lng: 80.9415 },
];
const FALLBACK_MEDICAL: ResPin[] = [{ id: 'm1', name: 'Medical team', lat: 26.8535, lng: 80.9425, free: true }];

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

const CELLS = WARDS.map((w) => {
  const p = proj(w.lat, w.lng);
  let poly: Pt[] = [{ x: 0, y: 0 }, { x: W, y: 0 }, { x: W, y: H }, { x: 0, y: H }];
  for (const o of WARDS) {
    if (o !== w) poly = clip(poly, p, proj(o.lat, o.lng));
  }
  const lines = w.name.length > 12 ? [w.name.slice(0, w.name.lastIndexOf(' ', 12) > 0 ? w.name.lastIndexOf(' ', 12) : 12), w.name.slice(w.name.lastIndexOf(' ', 12) > 0 ? w.name.lastIndexOf(' ', 12) + 1 : 12)] : [w.name];
  return { ward: w, c: p, d: poly.map((v) => `${v.x.toFixed(1)},${v.y.toFixed(1)}`).join(' '), lines };
});

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

  readonly W = W;
  readonly H = H;
  readonly cells = CELLS;
  readonly landmarks = LANDMARKS.map((l) => ({ ...l, ...proj(l.lat, l.lng) }));
  readonly kinds: Kind[] = ['spike', 'silent_zone', 'resource_gap', 'conflict'];
  readonly alerts = signal<AnomalyAlert[]>([]);
  readonly medical = signal<ResPin[]>([]);
  readonly selectedId = signal<string | null>(null);
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
    return s?.at ? this.latlng(s) : { lat: 26.852, lng: 80.945 };
  });

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
    this.selectedId.set(alert.id);
  }

  acknowledge(alert: AnomalyAlert): void {
    this.api.acknowledgeAlert(alert.id).subscribe({
      next: (updated) => this.alerts.update((rows) => rows.map((row) => (row.id === updated.id ? updated : row))),
    });
  }

  private latlng(i: MapAlert): { lat: number; lng: number } {
    const at = i.at as Pt;
    return { lat: LAT_MAX - at.y / 11667, lng: LNG_MIN + at.x / 12500 };
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
