const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { spawnSync } = require('node:child_process');

const ROOT = path.join(__dirname, '..');

test('generated place catalog matches the marked prototype data block', () => {
  const result = spawnSync(
    process.execPath,
    [path.join(ROOT, 'scripts', 'extract_place_data.mjs'), '--check'],
    { cwd: ROOT, encoding: 'utf8' },
  );

  assert.equal(result.status, 0, result.stderr || result.stdout);
  assert.match(result.stdout, /地点数据一致：26 个地点/);
});

test('generated catalog excludes unreviewed coordinates and reviewed overrides', () => {
  const catalog = JSON.parse(fs.readFileSync(path.join(ROOT, 'backend_app', 'data', 'places.json'), 'utf8'));
  const forbidden = ['lat', 'lng', 'amap', 'hours', 'photos'];

  assert.equal(catalog.PLACES.length, 26);
  for (const place of catalog.PLACES) {
    for (const key of forbidden) {
      assert.equal(Object.hasOwn(place, key), false, `${place.placeId} leaked ${key} into the base catalog`);
    }
  }
});
