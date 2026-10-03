const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const html = fs.readFileSync(path.join(__dirname, '..', '此在-current-原型.html'), 'utf8');
const tripSource = html.slice(html.indexOf('const TRIP_KEY ='), html.indexOf('state.trip = loadTrip();'));

function memoryStorage() {
  const values = new Map();
  return {
    getItem: key => values.has(key) ? values.get(key) : null,
    setItem: (key, value) => values.set(key, String(value)),
    removeItem: key => values.delete(key)
  };
}

function tripContext() {
  const localStorage = memoryStorage();
  const sessionStorage = memoryStorage();
  const state = { trip: null, offerDeparted: false };
  const context = {
    localStorage, sessionStorage, state,
    PLACES: [{ placeId: 'fruityshop', placeName: '水果店' }],
    placeById: () => ({ placeName: '水果店', action: '逛一逛' }),
    CurrentAI: {
      getLocationMode: () => 'real',
      track: () => {},
      publishRelay: () => Promise.resolve()
    },
    saveReach: () => {}
  };
  vm.createContext(context);
  vm.runInContext(tripSource + '\nglobalThis.tripApi = { loadTrip, saveTrip, startTrip, tripPlaceName };', context);
  return context;
}

test('a map-discovered trip keeps its real place name after the recommendation cache disappears', () => {
  const ctx = tripContext();
  ctx.tripApi.startTrip('amap:river123', {
    place_id: 'amap:river123', place_name: '天水围河', action: '沿河跑步', recommendation_id: 'rec_1'
  });
  const restored = ctx.tripApi.loadTrip();
  assert.equal(restored.placeName, '天水围河');
  assert.equal(ctx.tripApi.tripPlaceName(restored), '天水围河');
  assert.notEqual(ctx.tripApi.tripPlaceName(restored), '水果店');
});

test('an old unknown trip cannot be relabelled as the first curated place', () => {
  const ctx = tripContext();
  const startedAt = new Date().toISOString();
  ctx.localStorage.setItem('current.trip.v2', JSON.stringify({
    placeId: 'amap:missing', startedAt, status: 'departed'
  }));
  ctx.sessionStorage.setItem('current.trip.tab.v2', startedAt);
  assert.equal(ctx.tripApi.loadTrip(), null);
});

test('an old curated trip can still recover its known name', () => {
  const ctx = tripContext();
  const startedAt = new Date().toISOString();
  ctx.localStorage.setItem('current.trip.v2', JSON.stringify({
    placeId: 'fruityshop', startedAt, status: 'departed'
  }));
  ctx.sessionStorage.setItem('current.trip.tab.v2', startedAt);
  assert.equal(ctx.tripApi.tripPlaceName(ctx.tripApi.loadTrip()), '水果店');
});
