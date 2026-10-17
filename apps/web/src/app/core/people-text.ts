/** People count as words. Unknown stays unknown: never default to 1. */
export function peopleText(n: number | null | undefined, t: (key: string) => string): string {
  if (!n || n < 1) return t('people.notStated');
  if (n === 1) return t('people.one');
  return t('people.many').replace('{n}', String(n));
}
