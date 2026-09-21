import fs from 'node:fs';
import path from 'node:path';

const root = path.resolve(import.meta.dirname, '..');
const input = JSON.parse(fs.readFileSync(path.join(root, 'backend_app/data/place_overrides.json'), 'utf8'));
const photos = Object.fromEntries(Object.entries(input.places || {})
  .filter(([, place]) => Array.isArray(place.photos) && place.photos.length)
  .map(([id, place]) => [id, place.photos.slice(0, 3)]));
const output = `/* Generated from reviewed place_overrides.json. */\nwindow.CURRENT_PLACE_PHOTOS = ${JSON.stringify(photos, null, 2)};\n`;
fs.writeFileSync(path.join(root, 'place-photos.js'), output);
console.log(`Wrote photos for ${Object.keys(photos).length} reviewed places.`);
