const test = require("node:test");
const assert = require("node:assert/strict");
const Moments = require("../current-moments.js");

function memory() {
  const data = new Map();
  return {
    getItem: key => data.has(key) ? data.get(key) : null,
    setItem: (key, value) => data.set(key, value),
  };
}

test("demo moments are visibly synthetic and expire", () => {
  const start = Date.UTC(2026, 8, 21, 10);
  const seeds = Moments.demoMoments(start);
  assert.ok(seeds.length >= 8);
  assert.ok(seeds.every(item => item.isDemo && item.source === "demo_seed"));
  assert.ok(Moments.select(seeds, {city:"深圳", mood:"low", now:start + 1000}).length);
  assert.equal(Moments.select(seeds, {city:"深圳", mood:"low", now:start + 4 * 3600000}).length, 0);
});

test("a named contribution requires a nickname and stays a local draft", () => {
  const input = {place:"楼下", reason:"桂花开了", mood:"low", city:"深圳", visibility:"named"};
  assert.equal(Moments.contribution(input, 1, "x"), null);
  const item = Moments.contribution({...input, nickname:"小叶"}, 1, "x");
  assert.equal(item.nickname, "小叶");
  assert.equal(item.published, false);
  assert.equal(item.source, "local_draft");
});

test("consent is mutual, temporary, and never persisted", () => {
  const now = Date.now();
  const match = {isDemo:true, intent:"meet", mine:true, theirs:false, blocked:false, expiresAt:now + 1000};
  assert.equal(Moments.canReveal(match, now), false);
  match.theirs = true;
  assert.equal(Moments.canReveal(match, now), true);
  assert.equal(Moments.canReveal(match, now + 1001), false);

  const store = memory();
  Moments.write(store, {contributions:[], cards:[], match});
  assert.equal(Moments.read(store).match, null);
});

test("cloud state reflects a shadow, while user self-report wins", () => {
  assert.equal(Moments.cloudTone("low"), "heavy");
  assert.equal(Moments.cloudTone("low", {valence:"pleasant"}), "rainbow");
  assert.equal(Moments.cloudTone("okay", {valence:"mixed"}), "calm");
});
