import { caseMatches } from './case-search';

describe('caseMatches', () => {
  const row = {
    id: 'INC-005', type: 'medical', ward_id: 'ward_4', place_text: 'Clock Tower',
    summary: 'Oxygen running low for an elderly patient', report_ids: ['RD-2026-0042'],
  };
  const names = { ward_4: ['Aluva', 'आलुवा'] };

  it('finds by INC id, RD id, ward id, ward name and number', () => {
    for (const q of ['inc-005', 'INC-005', 'RD-2026-0042', 'ward_4', 'Aluva', 'आलुवा', 'ward 4']) {
      expect(caseMatches(row, q, names)).withContext(q).toBeTrue();
    }
  });

  it('finds by type and by words in the text', () => {
    expect(caseMatches(row, 'medical', names)).toBeTrue();
    expect(caseMatches(row, 'oxygen elderly', names)).toBeTrue();
    expect(caseMatches(row, 'dawa', names)).toBeTrue();
  });

  it('rejects non-matches and accepts empty', () => {
    expect(caseMatches(row, 'Meppadi', names)).toBeFalse();
    expect(caseMatches(row, 'food', names)).toBeFalse();
    expect(caseMatches(row, '', names)).toBeTrue();
  });
});
