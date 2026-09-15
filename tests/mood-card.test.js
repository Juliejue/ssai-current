const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const CARD_SOURCE = fs.readFileSync(path.join(__dirname, '..', 'mood-card.js'), 'utf8');

function loadCardModule() {
  const window = {};
  const sandbox = { window, Blob, Uint8Array, Date, Math, Promise };
  vm.createContext(sandbox);
  vm.runInContext(CARD_SOURCE, sandbox);
  return window.CurrentMoodCard;
}

function fakeDrawingDocument() {
  const drawnText = [];
  let downloads = 0;
  const context = {
    fillRect() {}, save() {}, restore() {}, beginPath() {}, arc() {}, stroke() {},
    moveTo() {}, arcTo() {}, closePath() {}, fill() {}, bezierCurveTo() {},
    fillText(value) { drawnText.push(String(value)); },
    measureText(value) { return { width: String(value).length * 24 }; },
  };
  const canvas = {
    width: 0,
    height: 0,
    getContext: () => context,
    toDataURL: () => 'data:image/png;base64,AA==',
  };
  const document = {
    body: { appendChild() {} },
    createElement(tag) {
      if (tag === 'canvas') return canvas;
      if (tag === 'a') {
        return { click() { downloads += 1; }, remove() {} };
      }
      throw new Error(`unexpected element: ${tag}`);
    },
  };
  return { document, canvas, drawnText, downloads: () => downloads };
}

function exportOptions(drawing, extra = {}) {
  return Object.assign({
    document: drawing.document,
    atob: value => Buffer.from(value, 'base64').toString('binary'),
    URL: { createObjectURL: () => 'blob:test', revokeObjectURL() {} },
    setTimeout: callback => callback(),
  }, extra);
}

const record = {
  id: 'r-test',
  placeName: '三联韬奋书店',
  placeCategory: '书店 · 室内',
  preMood: '累但静不下来',
  changeScore: -1,
  factors: ['太挤', '声音舒服', '坐得住', '第四项不会出现'],
  dwellMinutes: 36,
  visitStartedAt: '2026-09-15T12:00:00',
  note: 'PRIVATE SECRET THAT MUST NEVER BE EXPORTED',
};

test('builds a 4:5 non-judgemental model without the private note', () => {
  const card = loadCardModule();
  const model = card.buildModel(record, { placeName: 'Sanlian Taofen Bookstore', category: 'bookstore · indoors' }, 'en');

  assert.equal(card.dimensions.width, 1080);
  assert.equal(card.dimensions.height, 1350);
  assert.equal(model.place, 'Sanlian Taofen Bookstore');
  assert.equal(model.preMood, 'tired but wired');
  assert.deepEqual(Array.from(model.factors), ['too crowded', 'comfortable sound', 'easy to stay']);
  assert.equal(model.score, -1);
  assert.doesNotMatch(model.headline, /fail|失败/i);
  assert.doesNotMatch(JSON.stringify(model), /PRIVATE SECRET/);
  assert.equal(card.cardFileName(model), 'current-mood-2026-09-15.png');
});

test('draws only structured fields and keeps the canvas at 1080 by 1350', () => {
  const card = loadCardModule();
  const drawing = fakeDrawingDocument();
  const artifact = card.createArtifact(record, {}, exportOptions(drawing, { lang: 'zh' }));

  assert.equal(artifact.canvas.width, 1080);
  assert.equal(artifact.canvas.height, 1350);
  assert.match(drawing.drawnText.join(' '), /三联韬奋书店/);
  assert.doesNotMatch(drawing.drawnText.join(' '), /PRIVATE SECRET/);
  assert.equal(artifact.blob.type, 'image/png');
});

test('shares a PNG file through the native share sheet when file sharing is supported', async () => {
  const card = loadCardModule();
  const drawing = fakeDrawingDocument();
  let payload;
  class FakeFile {
    constructor(parts, name, options) {
      this.parts = parts;
      this.name = name;
      this.type = options.type;
    }
  }
  const navigator = {
    canShare: value => value.files.length === 1,
    share: async value => { payload = value; },
  };

  const result = await card.share(record, {}, exportOptions(drawing, { navigator, File: FakeFile, lang: 'zh' }));

  assert.equal(result.method, 'share');
  assert.equal(payload.files[0].type, 'image/png');
  assert.match(payload.files[0].name, /^current-mood-2026-09-15\.png$/);
  assert.equal(drawing.downloads(), 0);
});

test('downloads the PNG when native file sharing is unavailable', async () => {
  const card = loadCardModule();
  const drawing = fakeDrawingDocument();
  const navigator = { canShare: () => false, share: async () => assert.fail('share should not run') };

  const result = await card.share(record, {}, exportOptions(drawing, { navigator, lang: 'zh' }));

  assert.equal(result.method, 'download');
  assert.equal(drawing.downloads(), 1);
});

test('a synchronous share failure still falls back to a download', async () => {
  const card = loadCardModule();
  const drawing = fakeDrawingDocument();
  class FakeFile {}
  const navigator = {
    canShare: () => true,
    share: () => { throw new Error('native bridge failed'); },
  };

  const result = await card.share(record, {}, exportOptions(drawing, { navigator, File: FakeFile, lang: 'zh' }));

  assert.equal(result.method, 'download');
  assert.equal(drawing.downloads(), 1);
});
