/** Test providers are named for what they are and never shown as Gemini. Null for any other provider. */
export function testProviderWord(
  provider: string | null | undefined,
  vendor: string | null | undefined,
  translate: (key: string) => string,
): string | null {
  if (provider === 'openai_compat') return translate('ux.badgeTest').replace('{name}', vendor || 'OpenAI-compatible');
  if (provider === 'antigravity-local') return translate('ux.badgeLocal');
  return null;
}
