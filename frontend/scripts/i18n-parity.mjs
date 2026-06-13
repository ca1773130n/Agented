#!/usr/bin/env node
// i18n parity check: every locale catalog must have an identical key set.
// Flattens each locale JSON to dotted key paths, diffs each against the
// reference locale (en), reports MISSING/EXTRA per locale, prints the total
// diff count, and exits non-zero on any diff. (20-EVAL.md P7 algorithm.)

import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const localesDir = path.resolve(__dirname, '..', 'src', 'locales');
const locales = ['en', 'ko', 'ja', 'zh'];

const flatten = (o, prefix = '') =>
  Object.entries(o).flatMap(([k, v]) =>
    typeof v === 'object' && v !== null ? flatten(v, prefix + k + '.') : [prefix + k]
  );

const keys = locales.map((l) => {
  const obj = JSON.parse(fs.readFileSync(path.join(localesDir, l + '.json'), 'utf8'));
  return { locale: l, keys: new Set(flatten(obj)) };
});

let diffs = 0;
const ref = keys[0];
keys.slice(1).forEach(({ locale, keys: ks }) => {
  ref.keys.forEach((k) => {
    if (!ks.has(k)) {
      console.log('MISSING in ' + locale + ': ' + k);
      diffs++;
    }
  });
  ks.forEach((k) => {
    if (!ref.keys.has(k)) {
      console.log('EXTRA in ' + locale + ': ' + k);
      diffs++;
    }
  });
});

console.log('Total diff count:', diffs);
process.exit(diffs > 0 ? 1 : 0);
