/**
 * Schematic Kuttanad base for the offline map: lake, rivers and panchayat outlines (approximate,
 * lat/lng). Drawn under the pins when Google tiles are unavailable, so the map is never an empty box.
 */
export type LatLng = [number, number];

export const KUTTANAD_WATER: LatLng[][] = [
  // Southern Vembanad lake
  [[9.62, 76.31], [9.62, 76.39], [9.56, 76.40], [9.51, 76.385], [9.48, 76.36], [9.47, 76.33], [9.52, 76.30]],
];

export const KUTTANAD_RIVERS: LatLng[][] = [
  // Pamba
  [[9.30, 76.56], [9.33, 76.51], [9.36, 76.47], [9.39, 76.44], [9.42, 76.415], [9.445, 76.39], [9.48, 76.365]],
  // Alappuzha - Changanassery canal
  [[9.495, 76.335], [9.47, 76.37], [9.455, 76.41], [9.445, 76.46], [9.44, 76.53]],
  // Champakulam branch
  [[9.36, 76.40], [9.40, 76.405], [9.43, 76.41]],
];

export const KUTTANAD_WARDS: { id: string; name: string; ring: LatLng[] }[] = [
  { id: 'kainakary', name: 'Kainakary', ring: [[9.45, 76.365], [9.50, 76.375], [9.49, 76.41], [9.455, 76.41]] },
  { id: 'nedumudi', name: 'Nedumudi', ring: [[9.41, 76.37], [9.45, 76.37], [9.455, 76.405], [9.415, 76.405]] },
  { id: 'champakulam', name: 'Champakulam', ring: [[9.385, 76.395], [9.415, 76.40], [9.425, 76.44], [9.39, 76.44]] },
  { id: 'pulincunnu', name: 'Pulincunnu', ring: [[9.425, 76.41], [9.455, 76.41], [9.46, 76.46], [9.43, 76.46]] },
  { id: 'kavalam', name: 'Kavalam', ring: [[9.46, 76.41], [9.50, 76.41], [9.505, 76.46], [9.465, 76.46]] },
];

export const KUTTANAD_BOX = { minLa: 9.36, maxLa: 9.56, minLo: 76.33, maxLo: 76.50 };

export function inKuttanad(lat?: number | null, lng?: number | null): boolean {
  return lat != null && lng != null && lat > 9.25 && lat < 9.65 && lng > 76.25 && lng < 76.60;
}

export interface BaseShapes { water: string[]; rivers: string[]; wards: { id: string; name: string; points: string; lx: number; ly: number }[] }

export function projectBase(project: (lat: number, lng: number) => { x: number; y: number }): BaseShapes {
  const pts = (ring: LatLng[]) => ring.map(([a, b]) => project(a, b));
  const str = (p: { x: number; y: number }[]) => p.map((q) => `${q.x.toFixed(1)},${q.y.toFixed(1)}`).join(' ');
  return {
    water: KUTTANAD_WATER.map((r) => str(pts(r))),
    rivers: KUTTANAD_RIVERS.map((r) => str(pts(r))),
    wards: KUTTANAD_WARDS.map((w) => {
      const p = pts(w.ring);
      return { id: w.id, name: w.name, points: str(p), lx: p.reduce((s, q) => s + q.x, 0) / p.length, ly: p.reduce((s, q) => s + q.y, 0) / p.length };
    }),
  };
}
