import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
const approved = JSON.parse(readFileSync(new URL('../scripts/approved-direction-a.json', import.meta.url)));
for (const [key, svg] of Object.entries(approved)) {
  test(`${key} preserves the owner-approved direction A SVG art`, () => {
    const actual = readFileSync(new URL(`../site-icons/${key}/icon.svg`, import.meta.url), 'utf8');
    // Only accessibility metadata may be added to the immutable design source.
    assert.equal(actual.replace(/ role="img" aria-label="[^"]+"/, '').trim(), svg);
  });
}

// A missing original must fail the build instead of silently reintroducing a variant.
import { mkdtempSync, mkdirSync, copyFileSync, writeFileSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { spawnSync } from 'node:child_process';
test('build refuses an incomplete approved-original inventory', () => {
  const temp = mkdtempSync(path.join(tmpdir(), 'approved-icons-'));
  try {
    mkdirSync(path.join(temp, 'scripts'));
    for (const file of ['build-site-icons.mjs', 'site-icons-spec.mjs']) {
      copyFileSync(new URL(`../scripts/${file}`, import.meta.url), path.join(temp, 'scripts', file));
    }
    writeFileSync(path.join(temp, 'scripts', 'approved-direction-a.json'), '{}');
    const result = spawnSync(process.execPath, ['scripts/build-site-icons.mjs'], {cwd: temp, encoding: 'utf8'});
    assert.notEqual(result.status, 0, 'incomplete originals must block generation');
    assert.match(result.stderr, /Missing approved Direction A original/);
  } finally { rmSync(temp, {recursive: true, force: true}); }
});
