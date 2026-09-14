import fs from 'node:fs';
import path from 'node:path';
import vm from 'node:vm';

const root = path.resolve(import.meta.dirname, '..');
const sourcePath = path.join(root, '此在-current-原型.html');
const outputPath = path.join(root, 'backend_app', 'data', 'places.json');
const overridesPath = path.join(root, 'backend_app', 'data', 'place_overrides.json');
const source = fs.readFileSync(sourcePath, 'utf8');

const start = source.indexOf('const TAGS =');
const endMarker = 'const placeById =';
const end = source.indexOf(endMarker, start);

if (start < 0 || end < 0) {
  throw new Error('无法在原型中找到地点数据区块');
}

const dataBlock = source.slice(start, end)
  .replaceAll(/^const /gm, 'var ')
  .replaceAll(/^function /gm, 'function ');

const context = {};
vm.createContext(context);
vm.runInContext(`${dataBlock}\nthis.__export = { TAGS, FACTORS, MOOD_TARGET, NEEDS, ROUTES, PLACES };`, context);

// Human-reviewed map identities live outside the generated prototype block.
// Re-extracting the catalog must never erase those verified records.
if (fs.existsSync(overridesPath)) {
  const overrides = JSON.parse(fs.readFileSync(overridesPath, 'utf8')).places || {};
  context.__export.PLACES.forEach((place) => Object.assign(place, overrides[place.placeId] || {}));
}

fs.mkdirSync(path.dirname(outputPath), { recursive: true });
fs.writeFileSync(outputPath, `${JSON.stringify(context.__export, null, 2)}\n`);
console.log(`已写入 ${context.__export.PLACES.length} 个地点：${outputPath}`);
