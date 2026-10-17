import { etaPhrase, haversineKm, legTitle, markerDataUrl, teamTone } from './map-markers';

const en = (key: string) => ({ 'coord.etaMin': 'about {n} min', 'coord.noNearbyTeam': 'No nearby team' }[key] || key);

describe('map markers', () => {
  it('paints a free boat green and a missed check-in faded', () => {
    const fresh = new Date().toISOString();
    expect(teamTone({ status: 'available', location_updated_at: fresh })).toBe('free');
    expect(teamTone({ status: 'dispatched', location_updated_at: fresh })).toBe('busy');
    expect(teamTone({ status: 'available', assigned_request_id: 'INC-1', location_updated_at: '' })).toBe('busy');
    expect(teamTone({ status: 'available', location_updated_at: '' })).toBe('stale');
    const free = markerDataUrl({ marker: 'team', vehicle: 'boat', tone: 'free' }) || '';
    expect(decodeURIComponent(free)).toContain('#166534');
    expect(decodeURIComponent(free)).toContain('M2 14.5');
    const faded = markerDataUrl({ marker: 'team', vehicle: 'medical', tone: 'stale' }) || '';
    expect(decodeURIComponent(faded)).toContain('fill-opacity="0.4"');
    expect(decodeURIComponent(faded)).toContain('#6b7280');
    const urgent = markerDataUrl({ marker: 'case', tone: 'critical' }) || '';
    expect(decodeURIComponent(urgent)).toContain('#b91c1c');
  });

  it('uses the same kilometre and minute phrase as the case card', () => {
    expect(legTitle({ km: 1.2, minutes: 4, teamAvailable: true }, en)).toBe('1.2 km · about 4 min');
    expect(etaPhrase({ km: 12, noNearby: true, teamAvailable: true }, en)).toBe('about 36 min');
    expect(etaPhrase({ km: 1998, minutes: 5995, noNearby: true }, en)).toBe('No nearby team');
    expect(haversineKm(10.31, 76.2, 10.3, 76.2)).toBe(1.11);
  });
});
