import { RecentReport } from '@rd/shared';

const WINDOW_MS = 15 * 60 * 1000;

/** Ward names the desk already uses, so the toast can say "Kainakary". */
const WARD_PLACE: Record<string, { en: string; hi: string }> = {
  ward_1: { en: 'Kainakary', hi: 'काइनकरी' },
  ward_2: { en: 'Champakulam', hi: 'चम्पाकुलाम' },
  ward_3: { en: 'Nedumudi', hi: 'नेदुमुडी' },
  ward_4: { en: 'Aluva', hi: 'आलुवा' },
  ward_5: { en: 'Varapuzha', hi: 'वरप्पुषा' },
  ward_6: { en: 'Kothamangalam', hi: 'कोथमंगलम' },
  ward_7: { en: 'Chalakudy', hi: 'चालाकुडी' },
  ward_8: { en: 'Mala', hi: 'माला' },
  ward_9: { en: 'Anthikad', hi: 'अंतिक्काड' },
  ward_10: { en: 'Meppadi', hi: 'मेप्पाडी' },
  ward_11: { en: 'Vythiri', hi: 'वित्तूरि' },
  ward_12: { en: 'Kalpetta', hi: 'कल्पेट्टा' },
};

/** Last 15 minutes, newest first. */
export function visibleReports(rows: RecentReport[], now = Date.now()): RecentReport[] {
  return rows
    .filter((row) => {
      const at = new Date(row.created_at).getTime();
      return Number.isFinite(at) && now - at <= WINDOW_MS && now - at >= -60_000;
    })
    .sort((a, b) => (a.created_at < b.created_at ? 1 : a.created_at > b.created_at ? -1 : 0));
}

export function minutesAgo(iso: string, now = Date.now()): number {
  const at = new Date(iso).getTime();
  if (Number.isNaN(at)) return 0;
  return Math.max(0, Math.round((now - at) / 60000));
}

export function wardText(wardId: string | null | undefined, lang: string): string {
  if (!wardId) return '';
  const named = WARD_PLACE[wardId];
  if (named) return lang === 'hi' ? named.hi : named.en;
  return wardId.replace(/_/g, ' ').replace(/\b\w/g, (ch) => ch.toUpperCase());
}

/** Place in the toast: the ward name when we know it, otherwise the report's place. */
export function arrivalPlace(row: RecentReport, lang: string): string {
  const named = row.ward_id ? WARD_PLACE[row.ward_id] : undefined;
  if (named) return lang === 'hi' ? named.hi : named.en;
  const place = (row.place_text || '').trim();
  if (place) return place.length > 42 ? `${place.slice(0, 42).trim()}` : place;
  return wardText(row.ward_id, lang);
}

/** English keeps the short type word ("rescue"). Hindi and Malayalam use the translated label. */
export function arrivalType(row: RecentReport, lang: string, translate: (key: string) => string): string {
  if (lang === 'hi' || lang === 'ml') return translate(`incidentType.${row.type}`);
  return (row.type || 'other').replace(/_/g, ' ');
}
