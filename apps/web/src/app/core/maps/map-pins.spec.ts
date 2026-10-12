import {
  buildPinGroup,
  caseTitle,
  clusterMapPins,
  pinZ,
  placeTitle,
  positionIsStale,
  teamIsFree,
  teamTitle,
} from './map-pins';
import { googleMapOptions } from './map-provider.component';

describe('map pins', () => {
  const copy = {
    caseWord: 'Case',
    report: 'report',
    reports: 'reports',
    free: 'Free',
    busy: 'Busy',
    stale: 'Stale',
    sev: { critical: 'critical', high: 'high', medium: 'medium', low: 'low' },
    team: {
      boat: 'Boat team',
      ambulance: 'Ambulance team',
      medic: 'Medic team',
      food: 'Food and water team',
      rescue: 'Rescue team',
    },
    place: { shelter: 'Shelter', hospital: 'Hospital', camp: 'Camp' },
  };

  function xml(spec: Parameters<typeof buildPinGroup>[0]): string {
    return new XMLSerializer().serializeToString(buildPinGroup(spec));
  }

  it('draws a critical case with a queue number, an outer ring, and a merged badge', () => {
    const pin = buildPinGroup({ kind: 'case', severity: 'critical', queue: 1, merged: 2, selected: true });
    expect(pin.getAttribute('data-ring')).toBe('critical');
    expect(pin.getAttribute('data-merged')).toBe('2');
    expect(pin.getAttribute('data-selected')).toBe('1');
    const ring = [...pin.querySelectorAll('circle')].find((node) => node.getAttribute('r') === '16');
    expect(ring?.getAttribute('stroke')).toBe('var(--text)');
    const body = [...pin.querySelectorAll('circle')].find((node) => node.getAttribute('r') === '13');
    expect(body?.getAttribute('fill')).toBe('var(--sev-crit)');
    expect(body?.getAttribute('stroke')).toBe('var(--surface)');
    expect(pin.textContent).toContain('1');
    expect(pin.textContent).toContain('×2');
    expect(xml({ kind: 'case', severity: 'critical', queue: 1, merged: 2 })).not.toMatch(/#[0-9a-fA-F]{3,8}/);
    expect(caseTitle(1, 'critical', 2, copy)).toBe('Case 1, critical, 2 reports');
  });

  it('uses a filled corner dot for a free team and a hollow ring when busy', () => {
    const free = buildPinGroup({ kind: 'team', team: 'boat', free: true });
    const busy = buildPinGroup({ kind: 'team', team: 'medic', free: false });
    expect(free.getAttribute('data-free')).toBe('filled');
    expect(free.querySelector('[data-dot="filled"]')?.getAttribute('fill')).toBe('var(--ok)');
    expect(free.querySelector('rect')?.getAttribute('fill')).toBe('var(--brand)');
    expect(busy.getAttribute('data-free')).toBe('hollow');
    const hollow = busy.querySelector('[data-dot="hollow"]');
    expect(hollow?.getAttribute('fill')).toBe('none');
    expect(hollow?.getAttribute('stroke')).toBe('var(--sev-high)');
    expect(teamTitle('boat', 'Motorized Rescue Boat', true, false, copy)).toBe('Boat team Motorized Rescue Boat, Free');
    expect(teamTitle('boat', 'Motorized Rescue Boat', true, true, copy)).toContain('Stale');
  });

  it('draws a grey labelled diamond for a place', () => {
    const pin = buildPinGroup({ kind: 'place', place: 'hospital', label: 'Little Flower Hospital' });
    const diamond = pin.querySelector('polygon');
    expect(diamond?.getAttribute('data-shape')).toBe('diamond');
    expect(diamond?.getAttribute('fill')).toBe('var(--sev-low)');
    expect(pin.textContent).toContain('Little Flower Hospital');
    expect(placeTitle('hospital', 'Little Flower Hospital', copy)).toBe('Hospital, Little Flower Hospital');
  });

  it('treats a stale or empty team as busy and keeps a depot pin fresh', () => {
    const now = Date.parse('2026-10-12T06:00:00Z');
    expect(positionIsStale('seed', '2026-10-12T00:00:00Z', now)).toBeFalse();
    expect(positionIsStale(undefined, undefined, now)).toBeFalse();
    expect(positionIsStale('gps', '2026-10-12T05:50:00Z', now)).toBeTrue();
    expect(positionIsStale('gps', '2026-10-12T05:59:30Z', now)).toBeFalse();
    expect(teamIsFree('available', 4, false)).toBeTrue();
    expect(teamIsFree('available', 0, false)).toBeFalse();
    expect(teamIsFree('available', 4, true)).toBeFalse();
    expect(teamIsFree('dispatched', 4, false)).toBeFalse();
  });

  it('keeps separate cases until there are more than about 40', () => {
    const few = Array.from({ length: 40 }, (_, i) => ({
      id: `c${i}`, lat: 10 + i * 0.2, lng: 76, title: `Case ${i}`,
      spec: { kind: 'case' as const, severity: 'low' as const, queue: i + 1 },
    }));
    expect(clusterMapPins(few).length).toBe(40);
    const many = [
      ...Array.from({ length: 20 }, (_, i) => ({
        id: `a${i}`, lat: 10.01, lng: 76.01, title: `A ${i}`,
        spec: { kind: 'case' as const, severity: 'high' as const, queue: i + 1 },
      })),
      ...Array.from({ length: 21 }, (_, i) => ({
        id: `b${i}`, lat: 11.2, lng: 76.4, title: `B ${i}`,
        spec: { kind: 'case' as const, severity: i === 0 ? 'critical' as const : 'low' as const, queue: i + 1 },
      })),
    ];
    const clustered = clusterMapPins(many);
    expect(clustered.length).toBe(2);
    expect(clustered.every((pin) => pin.spec?.kind === 'cluster')).toBeTrue();
    expect(clustered.map((pin) => pin.spec?.merged).sort()).toEqual([20, 21]);
    expect(clustered.find((pin) => (pin.spec?.merged ?? 0) === 21)?.spec?.severity).toBe('critical');
  });

  it('stacks the selected pin above a critical case, then teams, then places', () => {
    expect(pinZ({ kind: 'case', selected: true, severity: 'low' })).toBeGreaterThan(pinZ({ kind: 'case', severity: 'critical' }));
    expect(pinZ({ kind: 'case', severity: 'critical' })).toBeGreaterThan(pinZ({ kind: 'case', severity: 'high' }));
    expect(pinZ({ kind: 'case', severity: 'high' })).toBeGreaterThan(pinZ({ kind: 'team', free: true }));
    expect(pinZ({ kind: 'team', free: true })).toBeGreaterThan(pinZ({ kind: 'place', place: 'shelter' }));
  });

  it('builds Google map options from the map id and leaves styles unset', () => {
    const opts = googleMapOptions({ lat: 10.5, lng: 76.3 }, 'DEMO_MAP_ID', 'LIGHT');
    expect(opts['mapId']).toBe('DEMO_MAP_ID');
    expect(opts['colorScheme']).toBe('LIGHT');
    expect(opts['styles']).toBeUndefined();
  });
});
