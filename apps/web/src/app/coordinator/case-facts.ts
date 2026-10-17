import type { StoredRequest } from '@rd/shared';
import { urgencyBand } from '@rd/shared';

/** One source for the facts that several panels show about a case. */

/** Steps in the strip: Read, Duplicates, Urgency, Team, Explained, You. The drawer uses the same number. */
export const STEP_COUNT = 6;

/** The AI steps every label counts (Read, Duplicates, Urgency, Team). One number on every surface. */
export const AI_STEP_COUNT = 4;

/** The one public ID a coordinator sees for a case (RD-xxxx). Internal ids stay in the audit log. */
export function caseRef(req: Pick<StoredRequest, 'id' | 'public_code'> | null | undefined): string {
  if (!req) return '';
  return req.public_code || req.id;
}

/** Reports joined into this case, from the same field the merged chip counts. */
export function joinedCount(req: Pick<StoredRequest, 'merged_count'> | null | undefined): number {
  return Math.max(1, Number(req?.merged_count || 1));
}

/** Urgency as shown on the card: a whole number. */
export function urgencyNumber(req: Pick<StoredRequest, 'urgency_score'> | null | undefined): number {
  return Math.round(Number(req?.urgency_score || 0));
}

/** Band label key for a score, from the shared band thresholds. */
export function bandKey(score: number): string {
  const band = urgencyBand(score);
  if (band === 'critical') return 'band.critical';
  if (band === 'high') return 'band.urgent';
  return 'band.other';
}
