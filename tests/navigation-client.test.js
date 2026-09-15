const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const CLIENT_SOURCE = fs.readFileSync(path.join(__dirname, '..', 'current-client.js'), 'utf8');

function runtime(userAgent) {
  const timers = [];
  const windowListeners = new Map();
  const documentListeners = new Map();
  const location = {
    hostname: 'current.test', port: '', origin: 'https://current.test', search: '', href: 'https://current.test/',
  };
  const document = {
    hidden: false,
    baseURI: 'https://current.test/',
    addEventListener(name, fn) { documentListeners.set(name, fn); },
    removeEventListener(name) { documentListeners.delete(name); },
  };
  const window = {
    CURRENT_API_BASE: '/api/v1',
    addEventListener(name, fn) { windowListeners.set(name, fn); },
    removeEventListener(name) { windowListeners.delete(name); },
  };
  const sandbox = {
    window,
    document,
    location,
    navigator: { userAgent },
    localStorage: { getItem: () => null, setItem: () => {} },
    crypto: { randomUUID: () => 'navigation-test' },
    fetch: async () => ({ ok: true, json: async () => ({}) }),
    URL,
    URLSearchParams,
    console,
    setTimeout(fn) { timers.push({ fn, cleared: false }); return timers.length - 1; },
    clearTimeout(id) { if (timers[id]) timers[id].cleared = true; },
    Date,
    Math,
    Promise,
  };
  vm.createContext(sandbox);
  vm.runInContext(CLIENT_SOURCE, sandbox);
  return { current: window.CurrentAI, location, document, timers, windowListeners, documentListeners };
}

const links = {
  amap: 'https://uri.amap.com/navigation?callnative=1',
  amap_ios: 'iosamap://path?dlat=39.9&dlon=116.4&t=2',
  amap_android: 'amapuri://route/plan/?dlat=39.9&dlon=116.4&t=2',
};

test('iPhone launches Amap directly and falls back to the web if the page stays visible', () => {
  const app = runtime('Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X)');
  assert.equal(app.current.launchMap('amap', links), true);
  assert.equal(app.location.href, links.amap_ios);
  assert.equal(app.timers.length, 1);

  app.timers[0].fn();
  assert.equal(app.location.href, links.amap);
});

test('leaving for the installed iPhone app cancels the web fallback', () => {
  const app = runtime('Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X)');
  app.current.launchMap('amap', links);
  app.document.hidden = true;
  app.documentListeners.get('visibilitychange')();
  assert.equal(app.timers[0].cleared, true);
});

test('Android gets its native route while desktop uses the universal web URL', () => {
  const android = runtime('Mozilla/5.0 (Linux; Android 15)');
  android.current.launchMap('amap', links);
  assert.equal(android.location.href, links.amap_android);

  const desktop = runtime('Mozilla/5.0 (Macintosh; Intel Mac OS X)');
  desktop.current.launchMap('amap', links);
  assert.equal(desktop.location.href, links.amap);
  assert.equal(desktop.timers.length, 0);
});
