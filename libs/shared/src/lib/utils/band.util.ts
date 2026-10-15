/** Single source of truth for urgency bands. Queue cards, filter chips, KPI tiles and the briefing all use these. */
export type UrgencyBandKey = 'critical' | 'high' | 'medium' | 'low';

/** Triage bands: Immediate cases are floored at 80, Urgent at 60. */
export const BAND_NOW = 80;
export const BAND_SOON = 60;
export const BAND_MEDIUM = 40;

export function urgencyBand(score: number): UrgencyBandKey {
  if (score >= BAND_NOW) return 'critical';
  if (score >= BAND_SOON) return 'high';
  if (score >= BAND_MEDIUM) return 'medium';
  return 'low';
}

export interface BandInput {
  urgency_score: number;
  flags?: string[];
  status?: string;
  translation_confidence?: number;
}

/** A case needs human review when it has any flag (hoax, low translation, duplicate conflict) or a re-check status. */
export function needsReview(r: BandInput): boolean {
  return (
    (r.flags?.length ?? 0) > 0 ||
    r.status === 'needs_recheck' ||
    (r.translation_confidence !== undefined && r.translation_confidence < 0.7)
  );
}

export interface BandCounts {
  critical: number;
  high: number;
  medium: number;
  low: number;
  review: number;
  total: number;
}

export function bandCounts(list: BandInput[]): BandCounts {
  const c: BandCounts = { critical: 0, high: 0, medium: 0, low: 0, review: 0, total: list.length };
  for (const r of list) {
    c[urgencyBand(r.urgency_score)]++;
    if (needsReview(r)) c.review++;
  }
  return c;
}
