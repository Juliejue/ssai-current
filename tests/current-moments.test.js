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
  assert.ok(Moments.select(seeds, {city:"深圳", mood:"low", now:start + 4 * 3600000}).length);
  assert.equal(Moments.select(seeds, {city:"深圳", mood:"low", now:start + 25 * 3600000}).length, 0);
});

test("a contribution is always anonymous and stays a local draft", () => {
  const input = {place:"楼下", reason:"桂花开了", mood:"low", city:"深圳", visibility:"named", nickname:"小叶", kind:"timed_beauty"};
  const item = Moments.contribution(input, 1, "x");
  assert.equal(item.visibility, "anonymous");
  assert.equal(Object.hasOwn(item, "nickname"), false);
  assert.equal(item.published, false);
  assert.equal(item.source, "local_draft");
  assert.equal(item.kind, "timed_beauty");
  assert.equal(item.expiresAt, 60 * 60000 + 1);
});

test("moments cover a nationwide set of cities and carry licensed images", () => {
  const seeds = Moments.demoMoments(1);
  const cities = new Set(seeds.map(item => item.city));
  assert.ok(cities.size >= 12);
  for (const city of ["北京", "上海", "广州", "深圳", "香港", "成都", "杭州", "南京"]) assert.ok(cities.has(city));
  assert.ok(seeds.every(item => item.image.startsWith("/assets/moments/") && item.image.endsWith(".jpg")));
  assert.ok(seeds.every(item => item.imageLicenseUrl === "https://unsplash.com/license"));
});

test("daily moments are deterministic and use five different cities", () => {
  const start = Date.UTC(2026, 8, 21, 10);
  const seeds = Moments.demoMoments(start);
  const options = {mood:"quiet", now:start + 1000, limit:5};
  const first = Moments.daily(seeds, options);
  const second = Moments.daily(seeds, options);
  assert.deepEqual(first.map(item => item.id), second.map(item => item.id));
  assert.equal(first.length, 5);
  assert.equal(new Set(first.map(item => item.city)).size, 5);
  assert.equal(new Set(first.map(item => item.image)).size, 5);
});

test("a new daily scenario replaces yesterday's expired set", () => {
  const store = memory();
  const first = Date.UTC(2026, 8, 21, 10);
  assert.equal(Moments.scenario(store, first), first);
  assert.equal(Moments.scenario(store, first + 2 * 3600000), first);
  const next = first + 25 * 3600000;
  assert.equal(Moments.scenario(store, next), next);
});

test("contribution types have intentional expiry windows", () => {
  const base = {place:"一处", reason:"有一束光", mood:"okay", city:"上海", visibility:"anonymous"};
  assert.equal(Moments.contribution({...base, kind:"lasting_place"}, 100, "a").expiresAt, null);
  assert.equal(Moments.contribution({...base, kind:"sensory"}, 100, "b").expiresAt, 100 + 180 * 60000);
  assert.equal(Moments.contribution({...base, kind:"seasonal"}, 100, "c").expiresAt, 100 + 10080 * 60000);
});

test("a real city outside the four demo cities is preserved", () => {
  const item = Moments.contribution({
    place:"河边", reason:"风很轻", mood:"quiet", city:"成都", kind:"lasting_place"
  }, 100, "chengdu");
  assert.equal(item.city, "成都");
});

test("local storage never persists identity or matching state", () => {
  const store = memory();
  Moments.write(store, {contributions:[], cards:[], match:{mine:true}, nickname:"小叶"});
  assert.deepEqual(Moments.read(store), {contributions:[], cards:[]});
});

test("cloud state reflects a shadow, while user self-report wins", () => {
  assert.equal(Moments.cloudTone("low"), "heavy");
  assert.equal(Moments.cloudTone("low", {valence:"pleasant"}), "rainbow");
  assert.equal(Moments.cloudTone("okay", {valence:"mixed"}), "calm");
});
