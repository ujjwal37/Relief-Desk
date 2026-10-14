/**
 * Muted Google Maps style that matches the app theme (zinc + emerald).
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
  { elementType: 'geometry', stylers: [{ color: '#e8ece9' }] },
  { elementType: 'labels.text.fill', stylers: [{ color: '#4b5563' }] },
  { elementType: 'labels.text.stroke', stylers: [{ color: '#f4f6f5' }] },
  { elementType: 'labels.icon', stylers: [{ visibility: 'off' }] },
  { featureType: 'poi', stylers: [{ visibility: 'off' }] },
  { featureType: 'poi.park', elementType: 'geometry', stylers: [{ visibility: 'on' }, { color: '#d7e6dc' }] },
  { featureType: 'transit', stylers: [{ visibility: 'off' }] },
  { featureType: 'road', elementType: 'geometry', stylers: [{ color: '#ffffff' }] },
  { featureType: 'road', elementType: 'geometry.stroke', stylers: [{ color: '#d5dbd7' }] },
  { featureType: 'road.highway', elementType: 'geometry', stylers: [{ color: '#dfe6e2' }] },
  { featureType: 'road.highway', elementType: 'labels', stylers: [{ visibility: 'off' }] },
  { featureType: 'administrative', elementType: 'geometry.stroke', stylers: [{ color: '#c5cdc8' }] },
  { featureType: 'administrative.land_parcel', stylers: [{ visibility: 'off' }] },
  { featureType: 'landscape.natural', elementType: 'geometry', stylers: [{ color: '#e2e8e4' }] },
  { featureType: 'water', elementType: 'geometry', stylers: [{ color: '#c5d9d2' }] },
  { featureType: 'water', elementType: 'labels.text.fill', stylers: [{ color: '#047857' }] },
];
