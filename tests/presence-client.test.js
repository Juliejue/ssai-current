const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const CLIENT_SOURCE = fs.readFileSync(path.join(__dirname, '..', 'current-client.js'), 'utf8');

function makePresenceRuntime(search = '') {
  let now = 1_700_000_000_000;
  let watchSuccess;
  let currentPosition = null;
  let getCurrentPositionCalls = 0;
  let clearedWatch = null;
  const documentListeners = new Map();
  const windowListeners = new Map();
  const storage = new Map();

  const document = {
    baseURI: 'https://current.test/current/',
    visibilityState: 'visible',
    addEventListener: (name, callback) => documentListeners.set(name, callback),
    removeEventListener: (name, callback) => {
      if (documentListeners.get(name) === callback) documentListeners.delete(name);
    },
  };
  const window = {
    CURRENT_API_BASE: '/api/v1',
    addEventListener: (name, callback) => windowListeners.set(name, callback),
    removeEventListener: (name, callback) => {
      if (windowListeners.get(name) === callback) windowListeners.delete(name);
    },
  };
  const FakeDate = class extends Date {
    static now() { return now; }
  };

  const sandbox = {
    window,
    document,
    location: { hostname: 'current.test', port: '', origin: 'https://current.test', search },
    navigator: {
      geolocation: {
        watchPosition: success => { watchSuccess = success; return 7; },
        getCurrentPosition: success => {
          getCurrentPositionCalls += 1;
          if (currentPosition) success(currentPosition);
        },
        clearWatch: id => { clearedWatch = id; },
      },
    },
    localStorage: {
      getItem: key => storage.get(key) || null,
      setItem: (key, value) => storage.set(key, value),
    },
    crypto: { randomUUID: () => 'presence-test' },
    fetch: async () => ({ ok: true, json: async () => ({}) }),
    URL,
    URLSearchParams,
    console,
    setInterval: () => 1,
    clearInterval: () => {},
    setTimeout: () => 2,
    clearTimeout: () => {},
    Date: FakeDate,
    Math,
    Promise,
  };
  vm.createContext(sandbox);
  vm.runInContext(CLIENT_SOURCE, sandbox);

  return {
    current: window.CurrentAI,
    position(latitude, longitude, accuracy = 5) {
      return { coords: { latitude, longitude, accuracy } };
    },
    emitWatch(position) { watchSuccess(position); },
    setCurrentPosition(position) { currentPosition = position; },
    advance(milliseconds) { now += milliseconds; },
    documentListeners,
    windowListeners,
    getCurrentPositionCalls: () => getCurrentPositionCalls,
    clearedWatch: () => clearedWatch,
  };
}

test('presence refreshes on page return and detects a sustained departure', () => {
  const runtime = makePresenceRuntime();
  const states = [];
  const departures = [];
  const inside = runtime.position(0.0001, 0.0001);
  const outside = runtime.position(0.01, 0.01);

  runtime.current.watchPresence(
    { latitude: 0, longitude: 0, radius_m: 100 },
    {
      onState: state => states.push(state),
      onLeft: state => departures.push(state),
      onUnavailable: error => assert.fail(error),
    },
  );

  runtime.emitWatch(outside);
  runtime.setCurrentPosition(inside);
  runtime.documentListeners.get('visibilitychange')();
  assert.equal(runtime.getCurrentPositionCalls(), 1);
  assert.equal(states.at(-1).inside, true);

  runtime.advance(6 * 60 * 1000);
  runtime.emitWatch(outside);
  assert.equal(departures.length, 0, 'one outside sample must not end the visit');
  runtime.advance(3 * 60 * 1000 + 1);
  runtime.emitWatch(outside);
  assert.equal(departures.length, 1);
  assert.ok(departures[0].dwellMinutes >= 6);

  runtime.current.stopPresence();
  assert.equal(runtime.clearedWatch(), 7);
  assert.equal(runtime.documentListeners.has('visibilitychange'), false);
  assert.equal(runtime.windowListeners.has('pageshow'), false);
});

test('trip demo uses explicit simulated arrival and departure callbacks', () => {
  const runtime = makePresenceRuntime('?demo=trip');
  const states = [];
  const departures = [];

  runtime.current.useBeijingDemo();
  assert.equal(runtime.current.getLocationMode(), 'trip-demo');
  runtime.current.watchPresence(null, {
    demoMode: true,
    onState: state => states.push(state),
    onLeft: state => departures.push(state),
    onUnavailable: error => assert.fail(error),
  });

  assert.equal(states.at(-1).inside, false);
  assert.equal(runtime.current.demoPresence('arrive'), true);
  assert.equal(states.at(-1).inside, true);
  assert.equal(runtime.current.demoPresence('leave'), true);
  assert.equal(departures.length, 1);
  assert.equal(departures[0].demo, true);
});
