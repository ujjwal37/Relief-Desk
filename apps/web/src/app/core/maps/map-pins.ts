/** Shared case, team, and place markers. SVG fallback and Google Advanced Markers both use this. */

export const SVG_NS = 'http://www.w3.org/2000/svg';
export const DEMO_MAP_ID = 'DEMO_MAP_ID';
export const STALE_MS = 120_000;
export const CLUSTER_AFTER = 40;

export type SeverityBand = 'critical' | 'high' | 'medium' | 'low';
export type TeamGlyph = 'boat' | 'ambulance' | 'medic' | 'food' | 'rescue';
export type PlaceKind = 'shelter' | 'hospital' | 'camp';

export interface PinSpec {
  kind: 'case' | 'team' | 'place' | 'cluster';
  severity?: SeverityBand;
  queue?: number;
  merged?: number;
  selected?: boolean;
  free?: boolean;
  team?: TeamGlyph;
  place?: PlaceKind;
  label?: string;
}

export interface DrawnPin extends PinSpec {
  id: string;
  x: number;
  y: number;
  lat: number;
  lng: number;
  title: string;
  dim: boolean;
  z: number;
  selectId?: string;
}

export interface MarkerInput {
  id: string;
  lat: number;
  lng: number;
  title: string;
  spec?: PinSpec;
  dim?: boolean;
  zIndex?: number;
}

export interface PinCopy {
  caseWord: string;
  report: string;
  reports: string;
  free: string;
  busy: string;
  stale: string;
  sev: Record<SeverityBand, string>;
  team: Record<TeamGlyph, string>;
  place: Record<PlaceKind, string>;
}

/** Synthetic places. Jetties are not place types. */
export const RELIEF_PLACES: { id: string; place: PlaceKind; name: string; lat: number; lng: number }[] = [
  { id: 'place-hospital', place: 'hospital', name: 'Little Flower Hospital', lat: 10.108, lng: 76.352 },
  { id: 'place-camp', place: 'camp', name: 'Kainakary Relief Camp', lat: 9.47, lng: 76.39 },
  { id: 'place-shelter', place: 'shelter', name: 'Nedumudi Shelter', lat: 9.445, lng: 76.41 },
];

const SEV_RANK: Record<SeverityBand, number> = { critical: 0, high: 1, medium: 2, low: 3 };

export function sevFill(severity: SeverityBand): string {
  if (severity === 'critical') return 'var(--sev-crit)';
  if (severity === 'high') return 'var(--sev-high)';
  if (severity === 'medium') return 'var(--sev-med)';
  return 'var(--sev-low)';
}

export function asSeverity(value: string | null | undefined): SeverityBand {
  if (value === 'critical' || value === 'high' || value === 'medium' || value === 'low') return value;
  return 'medium';
}

export function teamGlyph(kind: string, name = ''): TeamGlyph {
  if (kind === 'boat') return 'boat';
  if (kind === 'food') return 'food';
  if (kind === 'medical') return /ambulance/i.test(name) ? 'ambulance' : 'medic';
  return 'rescue';
}

/** A depot pin (seed or missing source) stays fresh. A shared fix older than 2 minutes is stale. */
export function positionIsStale(source?: string | null, updatedAt?: string | null, now = Date.now()): boolean {
  if (!source || source === 'seed' || source === 'missing') return false;
  if (!updatedAt) return true;
  const at = Date.parse(updatedAt);
  if (Number.isNaN(at)) return true;
  return now - at > STALE_MS;
}

/** Filled corner dot: free, with seats, and a fresh position. Anything else is the hollow busy ring. */
export function teamIsFree(status: string, capacity: number, stale: boolean): boolean {
  return status === 'available' && capacity > 0 && !stale;
}

/** selected > critical case > case > team > place */
export function pinZ(spec: PinSpec): number {
  if (spec.selected && (spec.kind === 'case' || spec.kind === 'cluster')) return 500;
  if ((spec.kind === 'case' || spec.kind === 'cluster') && spec.severity === 'critical') return 400;
  if (spec.kind === 'case' || spec.kind === 'cluster') return 300;
  if (spec.kind === 'team') return 200;
  return 100;
}

export function pinCopy(translate: (key: string) => string): PinCopy {
  const t = (key: string) => translate(key);
  return {
    caseWord: t('pins.case'),
    report: t('pins.report'),
    reports: t('pins.reports'),
    free: t('pins.free'),
    busy: t('pins.busy'),
    stale: t('pins.stale'),
    sev: {
      critical: t('pins.sev.critical'),
      high: t('pins.sev.high'),
      medium: t('pins.sev.medium'),
      low: t('pins.sev.low'),
    },
    team: {
      boat: t('pins.team.boat'),
      ambulance: t('pins.team.ambulance'),
      medic: t('pins.team.medic'),
      food: t('pins.team.food'),
      rescue: t('pins.team.rescue'),
    },
    place: {
      shelter: t('pins.place.shelter'),
      hospital: t('pins.place.hospital'),
      camp: t('pins.place.camp'),
    },
  };
}

export function caseTitle(queue: number, severity: SeverityBand, merged: number, copy: PinCopy): string {
  const n = Math.max(1, merged || 1);
  const reports = n === 1 ? `1 ${copy.report}` : `${n} ${copy.reports}`;
  return `${copy.caseWord} ${queue}, ${copy.sev[severity]}, ${reports}`;
}

export function teamTitle(glyph: TeamGlyph, name: string, free: boolean, stale: boolean, copy: PinCopy): string {
  const state = stale ? copy.stale : free ? copy.free : copy.busy;
  return `${copy.team[glyph]} ${name}, ${state}`.replace(/\s+/g, ' ').trim();
}

export function placeTitle(kind: PlaceKind, label: string, copy: PinCopy): string {
  return `${copy.place[kind]}, ${label}`;
}

function el<K extends keyof SVGElementTagNameMap>(
  name: K,
  attrs: Record<string, string | number | undefined>,
): SVGElementTagNameMap[K] {
  const node = document.createElementNS(SVG_NS, name);
  for (const [key, value] of Object.entries(attrs)) {
    if (value !== undefined) node.setAttribute(key, String(value));
  }
  return node;
}

function iconPaths(glyph: TeamGlyph): string[] {
  if (glyph === 'boat') return ['M2 10.5 L4.2 13.5 H11.8 L14 10.5', 'M8 2.5 V10'];
  if (glyph === 'ambulance') return ['M2 7 H14 V13 H2 Z', 'M5 7 V4.5 H11 V7', 'M8 8.5 V11.5 M6.4 10 H9.6'];
  if (glyph === 'medic') return ['M8 3 V13', 'M3 8 H13'];
  if (glyph === 'food') return ['M8 2.2 C8 2.2 3.4 7.6 3.4 10.4 a4.6 4.6 0 0 0 9.2 0 C12.6 7.6 8 2.2 8 2.2 Z'];
  return ['M8 3.2 a4.8 4.8 0 1 0 0.1 0', 'M4.6 4.6 L6.4 6.4', 'M11.4 4.6 L9.6 6.4', 'M4.6 11.4 L6.4 9.6', 'M11.4 11.4 L9.6 9.6'];
}

function addTeamIcon(parent: SVGGElement, glyph: TeamGlyph): void {
  const group = el('g', { transform: 'translate(-8,-8)' });
  for (const d of iconPaths(glyph)) {
    group.appendChild(el('path', {
      d,
      fill: 'none',
      stroke: 'var(--on-brand)',
      'stroke-width': 1.75,
      'stroke-linecap': 'round',
      'stroke-linejoin': 'round',
    }));
  }
  parent.appendChild(group);
}

function addBadge(parent: SVGGElement, count: number): void {
  const text = `×${count}`;
  const width = Math.max(22, 8 + text.length * 7);
  const badge = el('g', { transform: 'translate(10,-14)', 'data-badge': String(count) });
  badge.appendChild(el('rect', {
    x: -width / 2,
    y: -8,
    width,
    height: 16,
    rx: 8,
    fill: 'var(--text)',
  }));
  badge.appendChild(el('text', {
    x: 0,
    y: 0,
    dy: '.35em',
    'text-anchor': 'middle',
    'font-size': 10,
    'font-weight': 800,
    fill: 'var(--surface)',
    'font-family': 'var(--rd-font-family)',
  }));
  badge.lastChild!.textContent = text;
  parent.appendChild(badge);
}

/** Shapes centred on 0,0. Colours are theme tokens so light, dark, and greyscale stay in sync. */
export function buildPinGroup(spec: PinSpec): SVGGElement {
  const group = el('g', { 'data-pin': spec.kind, 'aria-hidden': 'true' });
  if (spec.severity) group.setAttribute('data-severity', spec.severity);
  if (spec.selected) group.setAttribute('data-selected', '1');

  if (spec.kind === 'case' || spec.kind === 'cluster') {
    const severity = spec.severity ?? 'medium';
    const fill = sevFill(severity);
    if (spec.selected) {
      group.appendChild(el('circle', {
        cx: 0, cy: 0, r: 20, fill: 'none', stroke: fill, 'stroke-width': 6, opacity: 0.35,
      }));
      group.appendChild(el('circle', {
        cx: 0, cy: 0, r: 18, fill: 'none', stroke: 'var(--text)', 'stroke-width': 2,
      }));
    }
    if (severity === 'critical') {
      group.setAttribute('data-ring', 'critical');
      group.appendChild(el('circle', {
        cx: 0, cy: 0, r: 16, fill: 'none', stroke: 'var(--text)', 'stroke-width': 2, 'data-ring': 'critical',
      }));
    }
    group.appendChild(el('circle', {
      cx: 0, cy: 0, r: 13, fill, stroke: 'var(--surface)', 'stroke-width': 3,
    }));
    if (spec.kind !== 'cluster' && spec.queue != null) {
      const number = el('text', {
        x: 0, y: 0, dy: '.35em', 'text-anchor': 'middle', 'font-size': 13, 'font-weight': 800,
        fill: 'var(--surface)', 'font-family': 'var(--rd-font-family)',
      });
      number.textContent = String(spec.queue);
      group.appendChild(number);
    }
    const count = spec.merged ?? 0;
    if (count > 1) {
      group.setAttribute('data-merged', String(count));
      addBadge(group, count);
    }
    return group;
  }

  if (spec.kind === 'team') {
    group.setAttribute('data-free', spec.free ? 'filled' : 'hollow');
    group.appendChild(el('rect', {
      x: -15, y: -15, width: 30, height: 30, rx: 8, fill: 'var(--brand)',
    }));
    addTeamIcon(group, spec.team ?? 'rescue');
    if (spec.free) {
      group.appendChild(el('circle', {
        cx: 12, cy: -12, r: 5, fill: 'var(--ok)', stroke: 'var(--surface)', 'stroke-width': 1.5, 'data-dot': 'filled',
      }));
    } else {
      group.appendChild(el('circle', {
        cx: 12, cy: -12, r: 5, fill: 'none', stroke: 'var(--sev-high)', 'stroke-width': 2, 'data-dot': 'hollow',
      }));
    }
    return group;
  }

  group.appendChild(el('polygon', {
    points: '0,-6 6,0 0,6 -6,0',
    fill: 'var(--sev-low)',
    stroke: 'var(--surface)',
    'stroke-width': 1.5,
    'data-shape': 'diamond',
  }));
  if (spec.label) {
    const label = el('text', {
      x: 10,
      y: 4,
      'font-size': 12,
      'font-weight': 700,
      fill: 'var(--text)',
      stroke: 'var(--map-bg)',
      'stroke-width': 3,
      'paint-order': 'stroke',
      'stroke-linejoin': 'round',
      'font-family': 'var(--rd-font-family)',
    });
    label.textContent = spec.label;
    group.appendChild(label);
  }
  return group;
}

export function pinMarkerContent(spec: PinSpec, dim: boolean): HTMLElement {
  const wrap = document.createElement('div');
  wrap.className = dim ? 'rd-pin dim' : 'rd-pin';
  if (dim) wrap.style.opacity = '0.45';
  const svg = document.createElementNS(SVG_NS, 'svg');
  svg.setAttribute('viewBox', '-28 -32 64 64');
  svg.setAttribute('width', '48');
  svg.setAttribute('height', '48');
  svg.setAttribute('aria-hidden', 'true');
  svg.style.overflow = 'visible';
  svg.appendChild(buildPinGroup(spec));
  wrap.appendChild(svg);
  return wrap;
}

function worstSeverity(pins: MarkerInput[]): SeverityBand {
  let best: SeverityBand = 'low';
  for (const pin of pins) {
    const severity = pin.spec?.severity ?? 'low';
    if (SEV_RANK[severity] < SEV_RANK[best]) best = severity;
  }
  return best;
}

/** Collapse case pins into ×N circles only past ~40 cases. One case in a cell stays itself. */
export function clusterMapPins(pins: MarkerInput[], limit = CLUSTER_AFTER): MarkerInput[] {
  const cases = pins.filter((pin) => pin.spec?.kind === 'case');
  if (cases.length <= limit) return pins;
  const rest = pins.filter((pin) => pin.spec?.kind !== 'case');
  const buckets = new Map<string, MarkerInput[]>();
  for (const pin of cases) {
    const key = `${Math.round(pin.lat / 0.05)}:${Math.round(pin.lng / 0.05)}`;
    const list = buckets.get(key) ?? [];
    list.push(pin);
    buckets.set(key, list);
  }
  const clustered: MarkerInput[] = [];
  for (const list of buckets.values()) {
    if (list.length === 1) {
      clustered.push(list[0]);
      continue;
    }
    const lat = list.reduce((sum, pin) => sum + pin.lat, 0) / list.length;
    const lng = list.reduce((sum, pin) => sum + pin.lng, 0) / list.length;
    const chosen = list.find((pin) => pin.spec?.selected) ?? list[0];
    const spec: PinSpec = {
      kind: 'cluster',
      severity: worstSeverity(list),
      merged: list.length,
      selected: list.some((pin) => pin.spec?.selected),
    };
    clustered.push({
      id: chosen.id,
      lat,
      lng,
      title: chosen.title,
      spec,
      dim: spec.selected ? false : list.every((pin) => pin.dim),
      zIndex: pinZ(spec),
    });
  }
  return [...rest, ...clustered];
}

export function clusterDrawnPins(pins: DrawnPin[], limit = CLUSTER_AFTER): DrawnPin[] {
  const cases = pins.filter((pin) => pin.kind === 'case');
  if (cases.length <= limit) return [...pins].sort((a, b) => a.z - b.z);
  const rest = pins.filter((pin) => pin.kind !== 'case');
  const buckets = new Map<string, DrawnPin[]>();
  for (const pin of cases) {
    const key = `${Math.round(pin.lat / 0.05)}:${Math.round(pin.lng / 0.05)}`;
    const list = buckets.get(key) ?? [];
    list.push(pin);
    buckets.set(key, list);
  }
  const clustered: DrawnPin[] = [];
  for (const list of buckets.values()) {
    if (list.length === 1) {
      clustered.push(list[0]);
      continue;
    }
    const chosen = list.find((pin) => pin.selected) ?? list[0];
    const severity = list.reduce<SeverityBand>((best, pin) => {
      const next = pin.severity ?? 'low';
      return SEV_RANK[next] < SEV_RANK[best] ? next : best;
    }, 'low');
    const spec: PinSpec = {
      kind: 'cluster',
      severity,
      merged: list.length,
      selected: list.some((pin) => pin.selected),
    };
    clustered.push({
      ...spec,
      id: chosen.id,
      x: list.reduce((sum, pin) => sum + pin.x, 0) / list.length,
      y: list.reduce((sum, pin) => sum + pin.y, 0) / list.length,
      lat: list.reduce((sum, pin) => sum + pin.lat, 0) / list.length,
      lng: list.reduce((sum, pin) => sum + pin.lng, 0) / list.length,
      title: chosen.title,
      dim: spec.selected ? false : list.every((pin) => pin.dim),
      z: pinZ(spec),
      selectId: chosen.selectId ?? chosen.id,
    });
  }
  return [...rest, ...clustered].sort((a, b) => a.z - b.z);
}
