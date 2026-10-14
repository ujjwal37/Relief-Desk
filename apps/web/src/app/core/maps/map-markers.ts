/** Vehicle pins and the same distance phrase the case card and the reporter use. */

export type VehicleKind = 'boat' | 'medical' | 'food' | 'shelter';
export type PinTone = 'free' | 'busy' | 'stale' | 'critical' | 'high' | 'medium' | 'low';

/** Free is green, busy and not-updated are grey. Case tones match the urgency chips. */
export const TONE_COLOR: Record<PinTone, string> = {
  free: '#047857',
  busy: '#6b7280',
  stale: '#6b7280',
  critical: '#dc2626',
  high: '#d97706',
  medium: '#2563eb',
  low: '#64748b',
};

/** 24×24 glyphs, drawn in white on the coloured pin. */
export const VEHICLE_PATHS: Record<VehicleKind, string> = {
  boat: 'M2 14.5h20l-1.6 3.2c-.8 1.6-2.4 2.6-4.2 2.6H7.8c-1.8 0-3.4-1-4.2-2.6L2 14.5zm10-1.2V5l6 4.2-6 4.1z',
  medical: 'M10 3h4v7h7v4h-7v7h-4v-7H3v-4h7V3z',
  food: 'M2 8h12V6h4l4 4v6h-2.2a2.2 2.2 0 0 1-4.1 0H8.3a2.2 2.2 0 0 1-4.1 0H2V8zm3.2 8.2a1.3 1.3 0 1 0 .1-2.6 1.3 1.3 0 0 0-.1 2.6zm11.6 0a1.3 1.3 0 1 0 .1-2.6 1.3 1.3 0 0 0-.1 2.6z',
  shelter: 'M12 3 3 11h3v9h5v-6h2v6h5v-9h3L12 3z',
};

const ON_CASE = new Set(['busy', 'dispatched', 'en_route', 'on_scene']);
/** A check-in older than this is "Not updated". */
export const CHECKIN_LATE_MIN = 120;

export function teamTone(
  team: { assigned_request_id?: string | null; status?: string; capacity_remaining?: number; location_updated_at?: string | null },
  now = Date.now(),
): 'free' | 'busy' | 'stale' {
  if (team.assigned_request_id || team.status === 'depleted' || (team.capacity_remaining != null && team.capacity_remaining <= 0) || (team.status != null && ON_CASE.has(team.status))) return 'busy';
  const stamp = team.location_updated_at || '';
  if (!stamp) return 'stale';
  const minutes = Math.round((now - new Date(stamp).getTime()) / 60000);
  if (!Number.isFinite(minutes) || minutes > CHECKIN_LATE_MIN) return 'stale';
  return 'free';
}

/** 20 km/h, at least one minute. Same rule as the API `eta_for_distance`. */
export function etaMinutes(km: number): number {
  return Math.max(1, Math.round((km / 20) * 60));
}

export interface TravelQuote {
  km: number;
  minutes?: number | null;
  noNearby?: boolean;
  teamAvailable?: boolean;
}

/** "about N min", or "No nearby team" past 30 km / 90 min. A free team within 15 km still gets a time. */
export function etaPhrase(quote: TravelQuote, translate: (key: string) => string): string {
  const km = quote.km ?? 0;
  const minutes = quote.minutes ?? etaMinutes(km);
  if (quote.teamAvailable && km <= 15 && minutes <= 90) {
    return translate('coord.etaMin').replace('{n}', String(minutes));
  }
  if (quote.noNearby || km > 30 || minutes > 90) return translate('coord.noNearbyTeam');
  return translate('coord.etaMin').replace('{n}', String(minutes));
}

/** The midpoint label: "X km · Y min", using the same words as the case card. */
export function legTitle(quote: TravelQuote, translate: (key: string) => string): string {
  return `${quote.km} km · ${etaPhrase(quote, translate)}`;
}

export function quoteFromProposal(
  prop: { breakdown?: { distance_km?: number }; eta_minutes?: number | null; no_nearby?: boolean },
  teamAvailable: boolean,
): TravelQuote {
  return {
    km: prop.breakdown?.distance_km ?? 0,
    minutes: prop.eta_minutes,
    noNearby: !!prop.no_nearby,
    teamAvailable,
  };
}

/** Great-circle kilometres, rounded like the case-card distance. */
export function haversineKm(lat1: number, lng1: number, lat2: number, lng2: number): number {
  const radius = 6371;
  const p1 = (lat1 * Math.PI) / 180;
  const p2 = (lat2 * Math.PI) / 180;
  const dPhi = ((lat2 - lat1) * Math.PI) / 180;
  const dLambda = ((lng2 - lng1) * Math.PI) / 180;
  const a = Math.sin(dPhi / 2) ** 2 + Math.cos(p1) * Math.cos(p2) * Math.sin(dLambda / 2) ** 2;
  const raw = radius * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
  return Math.round(raw * 100) / 100;
}

/** Data-URI icon for a Google marker. Empty when the pin has no role, so older callers keep the default pin. */
export function markerDataUrl(pin: { marker?: string; vehicle?: string; tone?: string }): string | null {
  if (!pin.marker && !pin.vehicle && !pin.tone) return null;
  const tone = (pin.tone || 'free') as PinTone;
  const fill = TONE_COLOR[tone] || '#0f1720';
  const opacity = tone === 'stale' ? 0.4 : 1;
  const path = pin.vehicle ? VEHICLE_PATHS[pin.vehicle as VehicleKind] : '';
  const glyph = path ? `<path d="${path}" fill="#ffffff" transform="translate(4 4)"/>` : '';
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="32" height="32" viewBox="0 0 32 32"><circle cx="16" cy="16" r="13" fill="${fill}" fill-opacity="${opacity}" stroke="#ffffff" stroke-width="2"/>${glyph}</svg>`;
  return `data:image/svg+xml;charset=UTF-8,${encodeURIComponent(svg)}`;
}

export function vehiclePath(kind: string | undefined): string {
  if (!kind) return '';
  return VEHICLE_PATHS[kind as VehicleKind] || '';
}
