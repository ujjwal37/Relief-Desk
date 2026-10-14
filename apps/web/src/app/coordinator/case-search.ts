/** Top-bar case search: INC/RD ids, ward id or name, need type, and the report text. */
export interface SearchableCase {
  id: string;
  type?: string | null;
  ward_id?: string | null;
  place_text?: string | null;
  summary?: string | null;
  raw_text?: string | null;
  ai_translation?: string | null;
  translations?: Record<string, string> | null;
  report_ids?: string[] | null;
}

const TYPE_WORDS: Record<string, string[]> = {
  rescue: ['rescue', 'boat', 'trapped', 'stranded', 'बचाव', 'bachao'],
  food: ['food', 'water', 'ration', 'खाना', 'khana'],
  medical: ['medical', 'medicine', 'doctor', 'oxygen', 'insulin', 'दवा', 'dawa', 'dawai'],
  shelter: ['shelter', 'camp', 'आश्रय'],
  info: ['info', 'update'],
  animal_attack: ['animal', 'dog', 'snake'],
};

export function caseMatches(r: SearchableCase, rawQuery: string, wardNames: Record<string, string[]> = {}): boolean {
  const q = (rawQuery || '').toLowerCase().trim();
  if (!q) return true;
  const ward = r.ward_id || '';
  const wardNum = ward.replace('ward_', '');
  const hay: string[] = [
    r.id,
    ...(r.report_ids || []),
    ward,
    `ward ${wardNum}`,
    ...(wardNames[ward] || []),
    r.type || '',
    (r.type || '').replace('_', ' '),
    ...(TYPE_WORDS[r.type || ''] || []),
    r.place_text || '',
    r.summary || '',
    r.raw_text || '',
    r.ai_translation || '',
    ...Object.values(r.translations || {}),
  ];
  const text = hay.join(' \u0001 ').toLowerCase();
  return q.split(/\s+/).every((word) => text.includes(word));
}
