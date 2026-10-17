/** People count as words. Unknown stays unknown: never default to 1. */
export function peopleText(n: number | null | undefined, t: (key: string) => string): string {
  if (n == null || Number.isNaN(n) || n < 0) return t('people.notStated');
  if (n === 0) return t('people.none');
  if (n === 1) return t('people.one');
  return t('people.many').replace('{n}', String(n));
}
