import { engineKey, inWorkingStrip, sortReady } from './ai-queue';

describe('AI queue order', () => {
  it('sorts Ready by urgency descending and pins a life-threat case first', () => {
    const rows = [
      { id: 'low', urgency_score: 92, created_at: '2026-10-17T10:00:00Z', ai_queue: { flags: [] as string[] } },
      { id: 'high', urgency_score: 93, created_at: '2026-10-17T09:00:00Z', ai_queue: { flags: [] as string[] } },
      { id: 'life', urgency_score: 10, created_at: '2026-10-17T08:00:00Z', ai_queue: { flags: ['lifeThreat'] } },
    ];
    expect(sortReady(rows).map((row) => row.id)).toEqual(['life', 'high', 'low']);
  });

  it('breaks urgency ties by newest first and ignores a just-ready tag', () => {
    const rows = [
      { id: 'older', urgency_score: 80, created_at: '2026-10-17T09:00:00Z', justReady: true },
      { id: 'newer', urgency_score: 80, created_at: '2026-10-17T11:00:00Z', justReady: false },
    ];
    expect(sortReady(rows).map((row) => row.id)).toEqual(['newer', 'older']);
  });

  it('reads Gemini, Rules, and Gemini rechecked from the one engine field', () => {
    expect(engineKey('gemini')).toBe('aiq.engineGemini');
    expect(engineKey('rules')).toBe('aiq.engineRules');
    expect(engineKey('gemini_rechecked')).toBe('aiq.engineRechecked');
    expect(engineKey(undefined)).toBeNull();
  });

  it('drops a timed-out row from the strip after 1.2s', () => {
    const req = { ai_queue: { status: 'ready', flags: ['timedOut'], engine: 'rules' } };
    expect(inWorkingStrip(req, 5_000, 4_000)).toBeTrue();
    expect(inWorkingStrip(req, 5_300, 4_000)).toBeFalse();
  });
});
