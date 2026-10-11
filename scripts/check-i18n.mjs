import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const I18N_DIR = path.resolve(__dirname, '../libs/shared/src/lib/i18n');
const LANGUAGES = ['en', 'hi', 'hinglish', 'ta'];

function flattenKeys(obj, prefix = '') {
  let keys = [];
  for (const [k, v] of Object.entries(obj)) {
    const fullKey = prefix ? `${prefix}.${k}` : k;
    if (typeof v === 'object' && v !== null && !Array.isArray(v)) {
      keys = keys.concat(flattenKeys(v, fullKey));
    } else {
      keys.push(fullKey);
    }
  }
  return keys;
}

let hasError = false;

// Load base (English) keys
const enFile = path.join(I18N_DIR, 'en.json');
if (!fs.existsSync(enFile)) {
  console.error(`Error: Base file ${enFile} not found.`);
  process.exit(1);
}

const enData = JSON.parse(fs.readFileSync(enFile, 'utf-8'));
const enKeys = new Set(flattenKeys(enData));

console.log(`Base English keys count: ${enKeys.size}`);

for (const lang of LANGUAGES) {
  const filePath = path.join(I18N_DIR, `${lang}.json`);
  if (!fs.existsSync(filePath)) {
    console.error(`Missing translation file: ${filePath}`);
    hasError = true;
    continue;
  }

  const data = JSON.parse(fs.readFileSync(filePath, 'utf-8'));
  const keys = new Set(flattenKeys(data));

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

