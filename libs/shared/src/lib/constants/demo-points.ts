export interface KuttanadDemoPoint {
  name: string;
  lat: number;
  lng: number;
}

/**
 * Fixed Kuttanad demo points from repo seed / ward / gazetteer data:
 * - Kainakary jetty: LM-02 in kerala_gazetteer.json & seeds.yaml (lat 9.47185, lng 76.39571)
 * - Nedumudi: ward_3 in kerala_gazetteer.json & seeds.yaml (lat 9.43, lng 76.398)
 * - Pulincunnu: RES-SHELTER-03 in resources.yaml (lat 9.46, lng 76.355)
 * - Champakulam: ward_2 in kerala_gazetteer.json & seeds.yaml (lat 9.416, lng 76.411)
 * - Kavalam: RES-BOAT-03 in resources.yaml (lat 9.49, lng 76.37)
 *
 * Points without coordinates in repo data (Gandhi School area, Ramankary, Thakazhi) are omitted.
 */
export const KUTTANAD_DEMO_POINTS: KuttanadDemoPoint[] = [
  { name: 'Kainakary jetty', lat: 9.47185, lng: 76.39571 },
  { name: 'Nedumudi', lat: 9.43, lng: 76.398 },
  { name: 'Pulincunnu', lat: 9.46, lng: 76.355 },
  { name: 'Champakulam', lat: 9.416, lng: 76.411 },
  { name: 'Kavalam', lat: 9.49, lng: 76.37 },
];

let demoPointIndex = 0;

/**
 * Returns one of the fixed Kuttanad demo points round-robin.
 */
export function getNextKuttanadDemoPoint(): KuttanadDemoPoint {
  const pt = KUTTANAD_DEMO_POINTS[demoPointIndex % KUTTANAD_DEMO_POINTS.length];
  demoPointIndex++;
  return pt;
}

/**
 * Resets the round-robin counter (useful for unit tests).
 */
export function resetKuttanadDemoPointIndex(): void {
  demoPointIndex = 0;
}
