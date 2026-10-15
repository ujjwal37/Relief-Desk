/** Road geometry from the Routes API. Straight-line fallback stays in the map component. */

export interface RoadRoute {
  path: { lat: number; lng: number }[];
  km: string;
  mins: string;
  meters: number;
  seconds: number;
}

type LatLng = { lat: number; lng: number };

/** Google encoded polyline (1e5) used by Routes API REST. */
export function decodePolyline(encoded: string): LatLng[] {
  const path: LatLng[] = [];
  let index = 0;
  let lat = 0;
  let lng = 0;
  while (index < encoded.length) {
    let result = 0;
    let shift = 0;
    let b = 0;
    do {
      b = encoded.charCodeAt(index++) - 63;
      result |= (b & 0x1f) << shift;
      shift += 5;
    } while (b >= 0x20);
    lat += (result & 1) ? ~(result >> 1) : (result >> 1);
    result = 0;
    shift = 0;
    do {
      b = encoded.charCodeAt(index++) - 63;
      result |= (b & 0x1f) << shift;
      shift += 5;
    } while (b >= 0x20);
    lng += (result & 1) ? ~(result >> 1) : (result >> 1);
    path.push({ lat: lat / 1e5, lng: lng / 1e5 });
  }
  return path;
}

export function formatDrive(meters: number, seconds: number): { km: string; mins: string } {
  const km = meters >= 1000
    ? `${(meters / 1000).toFixed(meters >= 10000 ? 0 : 1)} km`
    : `${Math.round(meters)} m`;
  const mins = seconds >= 60 ? `${Math.max(1, Math.round(seconds / 60))} mins` : `${Math.max(1, Math.round(seconds))} sec`;
  return { km, mins };
}

export class RoutingDeniedError extends Error {
  override name = 'RoutingDeniedError';
}

interface GoogleRoutesNs {
  maps?: {
    importLibrary?: (name: string) => Promise<{ Route?: { computeRoutes: (req: unknown) => Promise<unknown> } }>;
    routes?: { Route?: { computeRoutes: (req: unknown) => Promise<unknown> } };
  };
}

function latLngOf(value: unknown): LatLng | null {
  if (!value || typeof value !== 'object') return null;
  const row = value as { lat?: unknown; lng?: unknown; latitude?: unknown; longitude?: unknown };
  const lat = typeof row.lat === 'function' ? Number(row.lat()) : Number(row.lat ?? row.latitude);
  const lng = typeof row.lng === 'function' ? Number(row.lng()) : Number(row.lng ?? row.longitude);
  if (!Number.isFinite(lat) || !Number.isFinite(lng)) return null;
  return { lat, lng };
}

function pathFromUnknown(value: unknown): LatLng[] {
  if (!Array.isArray(value)) return [];
  return value.map(latLngOf).filter((point): point is LatLng => !!point);
}

function secondsOf(value: unknown): number {
  if (typeof value === 'number' && Number.isFinite(value)) return value;
  if (typeof value === 'string') {
    const match = value.match(/([\d.]+)/);
    return match ? Number(match[1]) : 0;
  }
  if (value && typeof value === 'object' && 'seconds' in (value as object)) {
    return Number((value as { seconds: unknown }).seconds) || 0;
  }
  return 0;
}

function fromJsRoute(route: Record<string, unknown>): RoadRoute | null {
  const encoded = (route['polyline'] as { encodedPolyline?: string } | undefined)?.encodedPolyline
    || (route['polyline'] as { encodedPath?: string } | undefined)?.encodedPath;
  let path = pathFromUnknown(route['path'] || route['overview_path']);
  if (!path.length && encoded) path = decodePolyline(encoded);
  const meters = Number(route['distanceMeters'] ?? route['distance_meters'] ?? 0);
  let seconds = secondsOf(route['durationMillis'] ?? route['duration']);
  if (route['durationMillis'] != null && seconds > 1000) seconds = seconds / 1000;
  if (!path.length) return null;
  const label = formatDrive(meters || 0, seconds || 0);
  return { path, km: label.km, mins: label.mins, meters: meters || 0, seconds: seconds || 0 };
}

async function computeViaJs(origin: LatLng, destination: LatLng): Promise<RoadRoute | null> {
  const g = (typeof window === 'undefined' ? null : window) as unknown as GoogleRoutesNs | null;
  const maps = g?.maps;
  if (!maps) return null;
  let Route = maps.routes?.Route;
  if (!Route && maps.importLibrary) {
    try {
      const lib = await maps.importLibrary('routes');
      Route = lib?.Route || maps.routes?.Route;
    } catch {
      return null;
    }
  }
  if (!Route?.computeRoutes) return null;
  try {
    const result = await Route.computeRoutes({
      origin,
      destination,
      travelMode: 'DRIVE',
      fields: ['path', 'distanceMeters', 'durationMillis', 'polyline'],
    });
    const routes = (result as { routes?: Record<string, unknown>[] })?.routes || [];
    return routes[0] ? fromJsRoute(routes[0]) : null;
  } catch (err) {
    const message = String(err || '');
    if (/REQUEST_DENIED|not enabled|PERMISSION_DENIED/i.test(message)) {
      throw new RoutingDeniedError(message);
    }
    return null;
  }
}

async function computeViaRest(origin: LatLng, destination: LatLng, apiKey: string): Promise<RoadRoute | null> {
  const res = await fetch('https://routes.googleapis.com/directions/v2:computeRoutes', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-Goog-Api-Key': apiKey,
      'X-Goog-FieldMask': 'routes.duration,routes.distanceMeters,routes.polyline.encodedPolyline',
    },
    body: JSON.stringify({
      origin: { location: { latLng: { latitude: origin.lat, longitude: origin.lng } } },
      destination: { location: { latLng: { latitude: destination.lat, longitude: destination.lng } } },
      travelMode: 'DRIVE',
      routingPreference: 'TRAFFIC_UNAWARE',
    }),
  });
  if (res.status === 403 || res.status === 401) {
    throw new RoutingDeniedError(`Routes API HTTP ${res.status}`);
  }
  if (!res.ok) return null;
  const body = await res.json() as {
    error?: { status?: string; message?: string };
    routes?: { duration?: unknown; distanceMeters?: number; polyline?: { encodedPolyline?: string } }[];
  };
  const status = body.error?.status || '';
  if (/REQUEST_DENIED|PERMISSION_DENIED/i.test(status) || /not enabled/i.test(body.error?.message || '')) {
    throw new RoutingDeniedError(body.error?.message || status);
  }
  const route = body.routes?.[0];
  const encoded = route?.polyline?.encodedPolyline;
  if (!route || !encoded) return null;
  const path = decodePolyline(encoded);
  if (!path.length) return null;
  const meters = Number(route.distanceMeters || 0);
  const seconds = secondsOf(route.duration);
  const label = formatDrive(meters, seconds);
  return { path, km: label.km, mins: label.mins, meters, seconds };
}

/** Prefer Maps JS `Route.computeRoutes`; REST computeRoutes is the fallback. */
export async function computeRoadRoute(
  origin: LatLng,
  destination: LatLng,
  apiKey: string | null,
): Promise<RoadRoute | null> {
  const viaJs = await computeViaJs(origin, destination);
  if (viaJs) return viaJs;
  if (apiKey) return computeViaRest(origin, destination, apiKey);
  return null;
}
