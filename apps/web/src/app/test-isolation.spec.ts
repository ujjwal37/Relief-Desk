// Root-level hook: keep tests independent of a language/theme saved by an earlier spec.
beforeEach(() => {
  try {
    localStorage.removeItem('rd_preferred_lang');
    localStorage.removeItem('rd_theme_mode');
  } catch {
    /* ignore */
  }
});
