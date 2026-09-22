const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const CLIENT_SOURCE = fs.readFileSync(path.join(__dirname, '..', 'current-client.js'), 'utf8');

function runtime(options = {}) {
  const storage = new Map();
  const requests = [];
  const dispatched = [];
  const window = {
    CURRENT_API_BASE: '/api/v1',
    innerWidth: options.width || 390,
    ontouchstart: options.touch === false ? undefined : () => {},
    addEventListener() {},
    removeEventListener() {},
    dispatchEvent(event) { dispatched.push(event.detail); },
    CustomEvent: class { constructor(_name, init) { this.detail = init.detail; } },
  };
  const sandbox = {
    window,
    document: { addEventListener() {}, removeEventListener() {}, hidden: false },
    location: { hostname:'current.test', port:'', origin:'https://current.test', pathname:'/current/', search:options.search || '' },
    navigator: { maxTouchPoints: options.touch === false ? 0 : 1, userAgent:'' },
    localStorage: {
      getItem:key => storage.has(key) ? storage.get(key) : null,
      setItem:(key,value) => storage.set(key,value),
      removeItem:key => storage.delete(key),
    },
    crypto: { randomUUID: () => 'relay-client' },
    fetch: async (url, init = {}) => {
      requests.push({url, init});
      if (url.endsWith('/asr/capabilities')) return response({tencent_realtime:false, preferred_provider:'browser'});
      if (url.endsWith('/relay/sessions')) return response({code:'7K9MNP', expires_at:'2099-01-01T00:00:00Z', durable:true});
      if (url.includes('/relay/7K9MNP/events')) return response({accepted:true, sequence:2, durable:true});
      if (url.includes('/relay/7K9MNP?after=0')) return response({
        code:'7K9MNP', expires_at:'2099-01-01T00:00:00Z', durable:true,
        events:[{sequence:1,event_type:'recommended',payload:{place_name:'亮马河'}}],
      });
      return response({events:[], expires_at:'2099-01-01T00:00:00Z', durable:true});
    },
    URL,
    URLSearchParams,
    console,
    setTimeout: () => 1,
    clearTimeout() {},
    setInterval: () => 2,
    clearInterval() {},
    Date,
    Math,
    Promise,
  };
  vm.createContext(sandbox);
  vm.runInContext(CLIENT_SOURCE, sandbox);
  return {current:window.CurrentAI, requests, dispatched, storage};
}

function response(body, ok = true) {
  return {ok, json:async () => body};
}

test('phone creates a short-lived relay and publishes only through the relay API', async () => {
  const app = runtime();
  assert.equal(app.current.deviceRole(), 'phone');
  const relay = await app.current.createRelaySession();
  assert.equal(relay.code, '7K9MNP');
  assert.equal(app.current.relayShareUrl(), 'https://current.test/current/?relay=7K9MNP#/connect');

  await app.current.publishRelay('departed', {place_id:'liangmahe', place_name:'亮马河'});
  const request = app.requests.find(item => item.url.includes('/relay/7K9MNP/events'));
  assert.deepEqual(JSON.parse(request.init.body), {
    event_type:'departed', payload:{place_id:'liangmahe', place_name:'亮马河'},
  });
});

test('desktop joins by code and receives existing structured events', async () => {
  const app = runtime({touch:false, width:1200, search:'?relay=7k9mnp'});
  assert.equal(app.current.deviceRole(), 'desk');
  assert.equal(app.current.relayPendingCode(), '7K9MNP');
  await app.current.joinRelaySession('7k9mnp');
  assert.equal(app.current.relayState().lastSequence, 1);
  assert.equal(app.dispatched[0].event_type, 'recommended');
  app.current.leaveRelaySession();
  assert.equal(app.current.relayState(), null);
});

test('an explicit role in the demo URL wins over device heuristics', () => {
  const app = runtime({touch:false, width:1200, search:'?role=phone'});
  assert.equal(app.current.deviceRole(), 'phone');
});
