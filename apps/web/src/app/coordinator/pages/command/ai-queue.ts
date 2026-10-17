import { StoredRequest } from '@rd/shared';

/** The four AI steps. Explained and You stay on the case panel. */
export const AI_STEPS = ['read', 'duplicates', 'urgency', 'team'] as const;

export function isLifeThreat(req: Pick<StoredRequest, 'ai_queue'>): boolean {
  return !!req.ai_queue?.flags?.includes('lifeThreat');
}

export function stepsDone(req: Pick<StoredRequest, 'ai_queue'>): boolean {
  if (!req.ai_queue) return true;
  const steps = req.ai_queue.steps || {};
  return AI_STEPS.every((step) => steps[step] === 'done');
}

/** Approve stays locked until the four steps finish or the 45s rules cap lands. */
export function aiNotFinished(req: Pick<StoredRequest, 'ai_queue' | 'analysis_status'>): boolean {
  if (!req.ai_queue) return false;
  if (req.ai_queue.flags?.includes('timedOut') || stepsDone(req)) return false;
  return req.analysis_status === 'analysing' || req.ai_queue.status === 'queued' || req.ai_queue.status === 'processing';
}

/**
 * A timed-out row stays in the strip for 1.2s, then leaves. It must not pile up.
 * Life-threat cases are never in the strip.
 */
export function inWorkingStrip(req: Pick<StoredRequest, 'ai_queue'>, now: number, timeoutSeenAt?: number): boolean {
  const queue = req.ai_queue;
  if (!queue || isLifeThreat(req)) return false;
  if (queue.flags?.includes('timedOut')) {
    if (timeoutSeenAt == null) return true;
    return now - timeoutSeenAt < 1200;
  }
  return queue.status === 'queued' || queue.status === 'processing';
}

/** One backend field, the same word at every width. */
export function engineKey(engine?: string | null): string | null {
  if (engine === 'gemini') return 'aiq.engineGemini';
  if (engine === 'gemini_rechecked') return 'aiq.engineRechecked';
  if (engine === 'rules') return 'aiq.engineRules';
  return null;
}

export function stepLabelKey(step?: string | null): string {
  if (step === 'duplicates') return 'aiq.stepDuplicates';
  if (step === 'urgency') return 'aiq.stepUrgency';
  if (step === 'team') return 'aiq.stepTeam';
  return 'aiq.stepRead';
}

export function stepNumber(step?: string | null): number {
  const index = AI_STEPS.indexOf((step || 'read') as (typeof AI_STEPS)[number]);
  return index < 0 ? 1 : index + 1;
}

export function ordinalKey(pos: number): string {
  if (pos === 1) return 'aiq.ordinal1';
  if (pos === 2) return 'aiq.ordinal2';
  if (pos === 3) return 'aiq.ordinal3';
  return 'aiq.ordinalN';
}

export function clockText(seconds: number): string {
  const n = Math.max(0, Math.floor(seconds || 0));
  const minutes = Math.floor(n / 60);
  const rest = n % 60;
  return `${minutes}:${rest.toString().padStart(2, '0')}`;
}

type ReadyRow = {
  urgency_score: number;
  created_at?: string | null;
  ai_queue?: { flags?: string[] } | null;
};

/** Life-threat first, then urgency descending, then newest. "Just ready" is not a sort key. */
export function sortReady<T extends ReadyRow>(rows: T[]): T[] {
  return [...rows].sort((a, b) => {
    const lifeA = a.ai_queue?.flags?.includes('lifeThreat') ? 1 : 0;
    const lifeB = b.ai_queue?.flags?.includes('lifeThreat') ? 1 : 0;
    if (lifeA !== lifeB) return lifeB - lifeA;
    if (a.urgency_score !== b.urgency_score) return b.urgency_score - a.urgency_score;
    const timeA = Date.parse(a.created_at || '') || 0;
    const timeB = Date.parse(b.created_at || '') || 0;
    return timeB - timeA;
  });
}
