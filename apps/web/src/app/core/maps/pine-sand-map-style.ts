/**
 * Muted Google Maps style that matches the app theme (palette A light: grey-green land, blue water).
 *
 * Works with classic markers (no mapId). When a mapId is set (AdvancedMarkerElement),
 * Google ignores this array, so the same colours must live in the cloud map style.
 */
export interface MapStyleRule {
  featureType?: string;
  elementType?: string;
  stylers: Record<string, string | number>[];
}

export const PINE_SAND_MAP_STYLE: MapStyleRule[] = [
  { elementType: 'geometry', stylers: [{ color: '#eef0ec' }] },
  { elementType: 'labels.text.fill', stylers: [{ color: '#5b6b78' }] },
  { elementType: 'labels.text.stroke', stylers: [{ color: '#ffffff' }] },
  { elementType: 'labels.icon', stylers: [{ visibility: 'off' }] },
  { featureType: 'poi', stylers: [{ visibility: 'off' }] },
  { featureType: 'poi.park', elementType: 'geometry', stylers: [{ visibility: 'on' }, { color: '#e3e9df' }] },
  { featureType: 'transit', stylers: [{ visibility: 'off' }] },
  { featureType: 'road', elementType: 'geometry', stylers: [{ color: '#ffffff' }] },
  { featureType: 'road', elementType: 'geometry.stroke', stylers: [{ color: '#ddd1c8' }] },
  { featureType: 'road.highway', elementType: 'geometry', stylers: [{ color: '#f1ebe6' }] },
  { featureType: 'road.highway', elementType: 'labels', stylers: [{ visibility: 'off' }] },
  { featureType: 'administrative', elementType: 'geometry.stroke', stylers: [{ color: '#c9d0d6' }] },
  { featureType: 'administrative.land_parcel', stylers: [{ visibility: 'off' }] },
  { featureType: 'landscape.natural', elementType: 'geometry', stylers: [{ color: '#eef0ec' }] },
  { featureType: 'water', elementType: 'geometry', stylers: [{ color: '#bcd3e2' }] },
  { featureType: 'water', elementType: 'labels.text.fill', stylers: [{ color: '#234c6a' }] },
];
