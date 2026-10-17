import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const I18N_DIR = path.resolve(__dirname, '../libs/shared/src/lib/i18n');
const LANGUAGES = ['en', 'hi', 'hinglish', 'ml'];

function flatten(obj, prefix = '') {
  const out = {};
  for (const [k, v] of Object.entries(obj)) {
    const fullKey = prefix ? `${prefix}.${k}` : k;
    if (typeof v === 'object' && v !== null && !Array.isArray(v)) {
      Object.assign(out, flatten(v, fullKey));
    } else {
      out[fullKey] = v;
    }
  }
  return out;
}

function flattenKeys(obj, prefix = '') {
  return Object.keys(flatten(obj, prefix));
}

// Proper names, an example address, and a numeric scale may match English.
const HI_SAME_AS_EN = new Set(['landing.cup', 'auth.emailPlaceholder', 'ux.scale']);

// Hinglish keeps English loanwords and proper nouns (Gemini, Password, team names); any new key must be translated.
const HINGLISH_SAME_AS_EN = new Set(JSON.parse(fs.readFileSync(path.join(__dirname, 'hinglish-same-as-en.json'), 'utf-8')));
// Malayalam is no longer a UI language: only key parity is checked (reports in Malayalam still use these strings).

let hasError = false;

// Load base (English) keys
const enFile = path.join(I18N_DIR, 'en.json');
if (!fs.existsSync(enFile)) {
  console.error(`Error: Base file ${enFile} not found.`);
  process.exit(1);
}

const enData = JSON.parse(fs.readFileSync(enFile, 'utf-8'));
const enFlat = flatten(enData);
const enKeys = new Set(Object.keys(enFlat));

console.log(`Base English keys count: ${enKeys.size}`);

for (const lang of LANGUAGES) {
  const filePath = path.join(I18N_DIR, `${lang}.json`);
  if (!fs.existsSync(filePath)) {
    console.error(`Missing translation file: ${filePath}`);
    hasError = true;
    continue;
  }

  const data = JSON.parse(fs.readFileSync(filePath, 'utf-8'));
  const flat = flatten(data);
  const keys = new Set(Object.keys(flat));
  if (lang === 'hi' || lang === 'hinglish') {
    const allowed = lang === 'hi' ? HI_SAME_AS_EN : HINGLISH_SAME_AS_EN;
    const fallback = [];
    for (const key of enKeys) {
      const value = flat[key];
      if (typeof value !== 'string') continue;
      if (value === key) fallback.push(`${key} is the key itself`);
      else if (value === enFlat[key] && !allowed.has(key)) fallback.push(`${key} still matches English`);
    }
    if (fallback.length > 0) {
      console.error(`\n[FAIL] ${lang}.json has ${fallback.length} untranslated strings:`);
      fallback.forEach((row) => console.error(`  - ${row}`));
      hasError = true;
    } else {
      console.log(`[PASS] ${lang}.json values are translated (no fallback keys).`);
    }
  }

  const missing = [...enKeys].filter((k) => !keys.has(k));
  if (missing.length > 0) {
    console.error(`\n[FAIL] ${lang}.json is missing ${missing.length} keys:`);
    missing.forEach((k) => console.error(`  - ${k}`));
    hasError = true;
  } else {
    console.log(`[PASS] ${lang}.json has all ${enKeys.size} required keys.`);
  }
}

if (hasError) {
  console.error('\nCI check-i18n FAILED: Key parity check failed.');
  process.exit(1);
} else {
  console.log('\nCI check-i18n PASSED: All languages have complete key parity!');
  const { spawnSync } = await import('child_process');
  const lint = spawnSync(process.execPath, [path.join(__dirname, 'lint-templates-i18n.mjs')], { stdio: 'inherit' });
  process.exit(lint.status ?? 1);
}

