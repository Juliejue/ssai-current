import fs from 'node:fs';
import path from 'node:path';

const root = path.resolve(import.meta.dirname, '..');
const { places } = JSON.parse(fs.readFileSync(path.join(root, 'backend_app/data/hong_kong_photos.json'), 'utf8'));
const escape = value => String(value).replace(/[&<>"']/g, ch => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));
fs.writeFileSync(path.join(root, 'hong-kong-place-photos.js'), `/* Generated from the reviewed Hong Kong photo catalog. */\nwindow.CURRENT_HK_PHOTOS = ${JSON.stringify(places, null, 2)};\n`);
const entries = places.map(place => `<section id="${escape(place.id)}"><h2>${escape(place.aliases[0])}</h2><div class="photos">${place.photos.map(photo => `<figure><img src="${escape(photo.url)}" alt="${escape(place.aliases[0])}" loading="lazy"><figcaption>照片：${escape(photo.author)} · <a href="${escape(photo.license_url)}">${escape(photo.license)}</a> · <a href="${escape(photo.source_url)}">原始照片</a><p>已缩放、压缩为网页格式。图片继续遵循原许可。</p></figcaption></figure>`).join('')}</div></section>`).join('\n');
fs.writeFileSync(path.join(root, 'photo-credits.html'), `<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>地点照片 · 此在 Current</title><style>body{margin:0;background:#f0f3f2;color:#163034;font:16px/1.7 system-ui,sans-serif}main{max-width:1050px;margin:40px auto;padding:0 22px}a{color:#397569}h1{font-size:26px}h2{font-size:20px}section{scroll-margin-top:20px;margin:40px 0}.photos{display:flex;gap:18px;flex-wrap:wrap}figure{flex:1 1 280px;margin:0;max-width:480px}img{width:100%;aspect-ratio:4/3;object-fit:cover;border-radius:14px}figcaption{font-size:13px;margin:8px 0}figcaption p{color:#657b77;margin:4px 0}</style></head><body><main><a href="/#/talk">← 回到此在</a><h1>香港地点照片</h1><p>真实地点的照片，以及摄影师和授权来源。</p>${entries}</main></body></html>\n`);
console.log(`Built ${places.length} Hong Kong place photo entries and their attributions.`);
