/** Pan only when the requested centre really moved. Used by MapProviderComponent.ngOnChanges. */
export type LatLng = { lat: number; lng: number };

export function centerMoved(prev: LatLng | null, next: LatLng | null | undefined): boolean {
  if (!next || !Number.isFinite(next.lat) || !Number.isFinite(next.lng)) return false;
  if (!prev) return true;
  return Math.abs(prev.lat - next.lat) > 1e-7 || Math.abs(prev.lng - next.lng) > 1e-7;
}

export function panIfMoved(
  map: { panTo?: (pos: LatLng) => void } | null,
  prev: LatLng | null,
  next: LatLng | null | undefined,
): LatLng | null {
  if (!map || !centerMoved(prev, next)) return prev;
  map.panTo?.({ lat: next!.lat, lng: next!.lng });
  return { lat: next!.lat, lng: next!.lng };
}
