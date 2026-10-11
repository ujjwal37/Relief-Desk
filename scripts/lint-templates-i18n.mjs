// Hard-coded visible text lint for Angular templates (html files and inline `template:` strings).
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const DIRS = ['apps/web/src/app', 'libs/shared/src/lib'];
const ALLOW_TEXT = new Set(['Relief Desk', '112', 'EN', 'HI', 'SMS', 'AI', 'ID', 'OK']);
const SKIP_FILES = ['shared.ts', 'map-provider.component.ts']; // scaffold / map provider owned by another worker, tracked in TASKS.md
const ATTRS = ['aria-label', 'placeholder', 'title', 'alt'];
function walk(d, out = []) {
  for (const e of fs.readdirSync(d, { withFileTypes: true })) {
    const p = path.join(d, e.name);
    if (e.isDirectory()) { if (e.name !== 'node_modules') walk(p, out); }
    else if (/\.(html|ts)$/.test(e.name) && !SKIP_FILES.includes(e.name) && !/\.spec\.ts$/.test(e.name)) out.push(p);
  }
  return out;
}
function templatesOf(file, src) {
  if (file.endsWith('.html')) return [src];
  const out = [];
  const re = /template:\s*`([\s\S]*?)`/g; let m;
  while ((m = re.exec(src))) out.push(m[1]);
  return out;
}
const hits = [];
for (const dir of DIRS) for (const f of walk(path.join(root, dir))) {
  const src = fs.readFileSync(f, 'utf8');
  for (const tpl of templatesOf(f, src)) {
    let t = tpl.replace(/<!--[\s\S]*?-->/g, '').replace(/<(script|style)[\s\S]*?<\/\1>/g, '').replace(/\{\{[\s\S]*?\}\}/g, ' ').replace(/\b(km|min|h)\b/g, ' ').replace(/@(if|else if|for|switch|case)\s*\([^)]*\)/g, ' ');
    // text nodes
    for (const m of t.matchAll(/>([^<>{}@]+)</g)) {
      const s = m[1].replace(/&\w+;/g, ' ').trim();
      if (/[A-Za-z\u0900-\u097F\u0B80-\u0BFF]{2,}/.test(s) && !ALLOW_TEXT.has(s)) hits.push(`${path.relative(root, f)}: text "${s.slice(0, 50)}"`);
    }
    for (const a of ATTRS) for (const m of t.matchAll(new RegExp(`\\s${a}="([^"]+)"`, 'g'))) {
      const s = m[1].trim();
      if (/[A-Za-z]{3,}/.test(s) && !ALLOW_TEXT.has(s)) hits.push(`${path.relative(root, f)}: ${a}="${s.slice(0, 50)}"`);
    }
  }
}
if (hits.length) {
  console.error(`\n[FAIL] ${hits.length} hard-coded visible strings in templates (use the rdTranslate pipe):`);
  [...new Set(hits)].forEach((h) => console.error('  - ' + h));
  process.exit(1);
}
console.log('[PASS] no hard-coded visible text in templates');

