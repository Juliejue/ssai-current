import fs from 'node:fs';
import path from 'node:path';
import vm from 'node:vm';

const root = path.resolve(import.meta.dirname, '..');
const sourcePath = path.join(root, '此在-current-原型.html');
const outputPath = path.join(root, 'backend_app', 'data', 'places.json');
const source = fs.readFileSync(sourcePath, 'utf8');

const startMarker = '/* CURRENT_PLACE_DATA_START */';
const endMarker = '/* CURRENT_PLACE_DATA_END */';
const start = source.indexOf(startMarker);
const end = source.indexOf(endMarker, start + startMarker.length);

if (start < 0 || end < 0) {
  throw new Error('无法在原型中找到完整的地点数据区块标记');
}

const dataBlock = source.slice(start + startMarker.length, end)
  .replaceAll(/^const /gm, 'var ');

const context = {};
vm.createContext(context);
vm.runInContext(`${dataBlock}\nthis.__export = { TAGS, FACTORS, MOOD_TARGET, NEEDS, ROUTES, PLACES };`, context);

const places = context.__export.PLACES;
if (!Array.isArray(places) || places.length === 0) {
  throw new Error('原型地点数据为空，拒绝覆盖 places.json');
}

const ids = new Set();
for (const place of places) {
  if (!place.placeId || ids.has(place.placeId)) {
    throw new Error(`地点 placeId 缺失或重复：${place.placeId || '(empty)'}`);
  }
  ids.add(place.placeId);

  // These coordinates are rough prototype layout data, not reviewed map
  // identities. Navigation/geofencing may only use the separately reviewed
  // `place_overrides.json`, which `load_catalog()` merges at runtime.
  delete place.lat;
  delete place.lng;
}

const output = `${JSON.stringify(context.__export, null, 2)}\n`;
if (process.argv.includes('--check')) {
  const existing = fs.existsSync(outputPath) ? fs.readFileSync(outputPath, 'utf8') : '';
  if (existing !== output) {
    throw new Error('places.json 与原型不一致；请运行 node scripts/extract_place_data.mjs 后提交变更');
  }
  console.log(`地点数据一致：${places.length} 个地点`);
  process.exit(0);
}

fs.mkdirSync(path.dirname(outputPath), { recursive: true });
fs.writeFileSync(outputPath, output);
console.log(`已写入 ${places.length} 个地点：${outputPath}`);
