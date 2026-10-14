import { RecentReport } from '@rd/shared';
import { arrivalPlace, arrivalType, minutesAgo, visibleReports, wardText } from './just-reported';

function row(partial: Partial<RecentReport> & Pick<RecentReport, 'id' | 'created_at'>): RecentReport {
  return {
    case_id: 'INC-1',
    type: 'rescue',
    summary: 'Water rising',
    ward_id: 'ward_1',
    place_text: 'Kainakary Ferry',
    joined_existing: false,
    ...partial,
  };
}

describe('visibleReports', () => {
  const now = Date.parse('2026-10-13T06:00:00Z');

  it('keeps the last 15 minutes, newest first', () => {
    const rows = visibleReports([
      row({ id: 'old', created_at: '2026-10-13T05:40:00Z' }),
      row({ id: 'mid', created_at: '2026-10-13T05:50:00Z' }),
      row({ id: 'new', created_at: '2026-10-13T05:59:00Z', type: 'medical', joined_existing: true }),
    ], now);
    expect(rows.map((item) => item.id)).toEqual(['new', 'mid']);
    expect(rows[0].joined_existing).toBeTrue();
    expect(rows[0].type).toBe('medical');
  });

  it('names the ward and the toast place', () => {
    const item = row({ id: 'a', created_at: '2026-10-13T05:59:00Z' });
    expect(wardText('ward_1', 'en')).toBe('Kainakary');
    expect(wardText('ward_1', 'hi')).toBe('काइनकरी');
    expect(arrivalPlace(item, 'en')).toBe('Kainakary');
    expect(arrivalType(item, 'en', (key) => key)).toBe('rescue');
    expect(arrivalType({ ...item, type: 'animal_attack' }, 'hi', (key) => (key.endsWith('animal_attack') ? 'जानवर का हमला' : key))).toBe('जानवर का हमला');
    expect(minutesAgo('2026-10-13T05:58:00Z', now)).toBe(2);
    expect(minutesAgo('2026-10-13T05:59:40Z', now)).toBe(0);
  });
});
