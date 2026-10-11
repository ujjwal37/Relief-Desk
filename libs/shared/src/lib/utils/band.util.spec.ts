import { bandCounts, needsReview, urgencyBand } from './band.util';

describe('band.util', () => {
  it('maps scores to the same bands used on cards', () => {
    expect(urgencyBand(94)).toBe('critical');
    expect(urgencyBand(75)).toBe('critical');
    expect(urgencyBand(74.9)).toBe('high');
    expect(urgencyBand(70)).toBe('high');
    expect(urgencyBand(55)).toBe('medium');
    expect(urgencyBand(10)).toBe('low');
  });

  it('counts critical/high exactly as the cards band them (no Critical 0 vs HIGH mismatch)', () => {
    const list = [{ urgency_score: 92 }, { urgency_score: 88 }, { urgency_score: 83 }, { urgency_score: 60 }, { urgency_score: 20 }];
    const c = bandCounts(list);
    expect(c.critical).toBe(list.filter((r) => urgencyBand(r.urgency_score) === 'critical').length);
    expect(c.critical).toBe(3);
    expect(c.high).toBe(0);
    expect(c.critical + c.high + c.medium + c.low).toBe(c.total);
  });

  it('flags review cases', () => {
    expect(needsReview({ urgency_score: 50, flags: ['hoax_suspect'] })).toBeTrue();
    expect(needsReview({ urgency_score: 50, translation_confidence: 0.4 })).toBeTrue();
    expect(needsReview({ urgency_score: 50 })).toBeFalse();
  });
});
