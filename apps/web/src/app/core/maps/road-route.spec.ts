import { decodePolyline, formatDrive } from './road-route';

describe('decodePolyline', () => {
  it('decodes a short encoded path', () => {
    // Encoded from (38.5, -120.2) -> (40.7, -120.95) -> (43.252, -126.453)
    const path = decodePolyline('_p~iF~ps|U_ulLnnqC_mqNvxq`@');
    expect(path.length).toBe(3);
    expect(path[0].lat).toBeCloseTo(38.5, 3);
    expect(path[0].lng).toBeCloseTo(-120.2, 3);
    expect(path[2].lat).toBeCloseTo(43.252, 3);
  });

  it('formats drive distance and minutes', () => {
    expect(formatDrive(1850, 240).km).toContain('1.9');
    expect(formatDrive(1850, 240).mins).toContain('4');
  });
});
