/**
 * Muted Google Maps style that matches the Pine & Sand theme.
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
  { elementType: 'geometry', stylers: [{ color: '#F1EADB' }] },
  { elementType: 'labels.text.fill', stylers: [{ color: '#5E5A50' }] },
  { elementType: 'labels.text.stroke', stylers: [{ color: '#F5EFE3' }] },
  { elementType: 'labels.icon', stylers: [{ visibility: 'off' }] },
  { featureType: 'poi', stylers: [{ visibility: 'off' }] },
  { featureType: 'poi.park', elementType: 'geometry', stylers: [{ visibility: 'on' }, { color: '#DCE6D5' }] },
  { featureType: 'transit', stylers: [{ visibility: 'off' }] },
  { featureType: 'road', elementType: 'geometry', stylers: [{ color: '#FFFDF8' }] },
  { featureType: 'road', elementType: 'geometry.stroke', stylers: [{ color: '#E2D6BC' }] },
  { featureType: 'road.highway', elementType: 'geometry', stylers: [{ color: '#EADFC6' }] },
  { featureType: 'road.highway', elementType: 'labels', stylers: [{ visibility: 'off' }] },
  { featureType: 'administrative', elementType: 'geometry.stroke', stylers: [{ color: '#C9B996' }] },
  { featureType: 'administrative.land_parcel', stylers: [{ visibility: 'off' }] },
  { featureType: 'landscape.natural', elementType: 'geometry', stylers: [{ color: '#E8E4D2' }] },
  { featureType: 'water', elementType: 'geometry', stylers: [{ color: '#BFD6D0' }] },
  { featureType: 'water', elementType: 'labels.text.fill', stylers: [{ color: '#3E6E64' }] },
];