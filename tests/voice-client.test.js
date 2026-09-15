const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const CLIENT_SOURCE = fs.readFileSync(path.join(__dirname, '..', 'current-client.js'), 'utf8');

function makeVoiceRuntime(options = {}) {
  const statuses = [];
  const transcripts = [];
  const errors = [];
  const tracks = [{ stopped: false, stop() { this.stopped = true; } }];
  const sockets = [];
  const processors = [];
  const contexts = [];
  const sources = [];

  class FakeNode {
    constructor() { this.connections = []; }
    connect(node) { this.connections.push(node); return this; }
    disconnect() { this.disconnected = true; }
  }

  class FakeProcessor extends FakeNode {
    constructor() {
      super();
      this.port = {
        onmessage: null,
        sent: [],
        postMessage: message => this.port.sent.push(message),
      };
      processors.push(this);
    }
  }

  class FakeAudioContext {
    constructor() {
      this.audioWorklet = { addModule: async url => {
        this.moduleUrl = url;
        if (options.addModuleError) throw options.addModuleError;
      } };
      this.destination = new FakeNode();
      contexts.push(this);
    }
    async resume() { this.resumed = true; }
    createMediaStreamSource() {
      const source = new FakeNode();
      sources.push(source);
      return source;
    }
    createAnalyser() {
      const analyser = new FakeNode();
      analyser.fftSize = 0;
      analyser.getByteTimeDomainData = () => {};
      return analyser;
    }
    createGain() {
      const gain = new FakeNode();
      gain.gain = { value: 1 };
      return gain;
    }
    close() { this.closed = true; return Promise.resolve(); }
  }

  class FakeWebSocket {
    static OPEN = 1;
    constructor(url) {
      this.url = url;
      this.readyState = 0;
      this.sent = [];
      sockets.push(this);
    }
    send(message) { this.sent.push(message); }
    close() { this.readyState = 3; }
    open() { this.readyState = FakeWebSocket.OPEN; this.onopen(); }
    receive(message) { this.onmessage({ data: JSON.stringify(message) }); }
  }

  const storage = new Map();
  const window = { CURRENT_API_BASE: '/api/v1', AudioContext: FakeAudioContext, AudioWorkletNode: FakeProcessor };
  const sandbox = {
    window,
    document: { baseURI: 'https://current.test/' },
    location: { hostname: 'current.test', port: '', origin: 'https://current.test' },
    navigator: {
      mediaDevices: {
        getUserMedia: async () => ({ getTracks: () => tracks }),
      },
    },
    localStorage: {
      getItem: key => storage.get(key) || null,
      setItem: (key, value) => storage.set(key, value),
    },
    crypto: { randomUUID: () => 'voice-test' },
    fetch: async url => ({
      ok: true,
      json: async () => url.endsWith('/asr/signature')
        ? { url: 'wss://asr.test/session' }
        : {},
    }),
    AudioWorkletNode: FakeProcessor,
    WebSocket: FakeWebSocket,
    URL,
    console,
    setInterval: () => 1,
    clearInterval: () => {},
    setTimeout: () => 2,
    clearTimeout: () => {},
    Uint8Array,
    Date,
    Math,
    Promise,
  };
  vm.createContext(sandbox);
  vm.runInContext(CLIENT_SOURCE, sandbox);

  return {
    current: window.CurrentAI,
    callbacks: {
      onStatus: status => statuses.push(status),
      onPartial: text => transcripts.push(text),
      onText: text => transcripts.push(`final:${text}`),
      onError: error => errors.push(error),
    },
    statuses,
    transcripts,
    errors,
    tracks,
    sockets,
    processors,
    contexts,
    sources,
  };
}

test('voice capture starts after provider code 0 and flushes before end', async () => {
  const runtime = makeVoiceRuntime();
  await runtime.current.toggleVoice(runtime.callbacks);
  const socket = runtime.sockets[0];
  const processor = runtime.processors[0];
  const firstAudio = new ArrayBuffer(640);
  assert.equal(runtime.contexts[0].moduleUrl, 'https://current.test/voice-worklet.mjs');

  socket.open();
  processor.port.onmessage({ data: { type: 'audio', buffer: firstAudio } });
  assert.equal(socket.sent.length, 0, 'an impossible early frame must be dropped');
  assert.equal(runtime.sources[0].connections.includes(processor), false);

  socket.receive({ code: 0, message: 'success' });
  assert.equal(runtime.sources[0].connections.includes(processor), true);
  assert.ok(runtime.statuses.includes('我在听，再按一次结束'));

  processor.port.onmessage({ data: { type: 'audio', buffer: firstAudio } });
  assert.equal(socket.sent[0], firstAudio);

  await runtime.current.toggleVoice(runtime.callbacks);
  assert.equal(processor.port.sent.at(-1).type, 'flush');

  const finalAudio = new ArrayBuffer(160);
  processor.port.onmessage({ data: { type: 'audio', buffer: finalAudio } });
  processor.port.onmessage({ data: { type: 'flushed' } });
  assert.equal(socket.sent.at(-2), finalAudio);
  assert.equal(socket.sent.at(-1), JSON.stringify({ type: 'end' }));
  const sentAtEnd = socket.sent.length;
  processor.port.onmessage({ data: { type: 'audio', buffer: new ArrayBuffer(80) } });
  assert.equal(socket.sent.length, sentAtEnd, 'audio must never be sent after end');

  socket.receive({ code: 0, result: { voice_text_str: '想去安静一点的地方', slice_type: 2 } });
  assert.ok(runtime.transcripts.includes('想去安静一点的地方'));
  assert.equal(runtime.tracks[0].stopped, false, 'a stable sentence is not the end of the stream');
  socket.receive({ code: 0, final: 1 });
  assert.ok(runtime.transcripts.includes('final:想去安静一点的地方'));
  assert.equal(runtime.tracks[0].stopped, true);
  assert.deepEqual(runtime.errors, []);
});

test('voice setup failure releases the microphone and permits retry', async () => {
  const runtime = makeVoiceRuntime({ addModuleError: new Error('worklet failed') });

  await assert.rejects(
    runtime.current.toggleVoice(runtime.callbacks),
    /语音暂时没有启动成功/,
  );
  assert.equal(runtime.tracks[0].stopped, true);
  assert.equal(runtime.contexts[0].closed, true);

  await assert.rejects(
    runtime.current.toggleVoice(runtime.callbacks),
    /语音暂时没有启动成功/,
  );
});
