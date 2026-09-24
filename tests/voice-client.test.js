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
  const recognitions = [];
  const fetchUrls = [];
  const timers = [];

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

  class FakeSpeechRecognition {
    constructor() { recognitions.push(this); }
    start() {
      if (options.recognitionStartError) throw options.recognitionStartError;
      this.started = true;
      if (!options.suppressRecognitionStart && this.onstart) this.onstart();
    }
    stop() { this.stopped = true; }
    abort() { this.aborted = true; }
    result(entries) {
      const results = entries.map(entry => {
        const result = [{ transcript: entry.text }];
        result.isFinal = Boolean(entry.final);
        return result;
      });
      this.onresult({ results });
    }
    error(code) { this.onerror({ error: code }); }
    end() { if (this.onend) this.onend(); }
  }

  const storage = new Map();
  const window = { CURRENT_API_BASE: '/api/v1', AudioContext: FakeAudioContext, AudioWorkletNode: FakeProcessor };
  if (options.browserSpeech) window.webkitSpeechRecognition = FakeSpeechRecognition;
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
    fetch: async url => {
      fetchUrls.push(url);
      if (url.endsWith('/asr/capabilities') && options.capabilityError) {
        throw options.capabilityError;
      }
      return {
        ok: true,
        json: async () => {
          if (url.endsWith('/asr/capabilities')) {
            const capabilities = {};
            if (typeof options.tencentConfigured === 'boolean') {
              capabilities.tencent_realtime = options.tencentConfigured;
            }
            if (options.preferredProvider) {
              capabilities.preferred_provider = options.preferredProvider;
            }
            return capabilities;
          }
          return url.endsWith('/asr/signature')
            ? { url: 'wss://asr.test/session' }
            : {};
        },
      };
    },
    AudioWorkletNode: FakeProcessor,
    WebSocket: FakeWebSocket,
    URL,
    console,
    setInterval: () => 1,
    clearInterval: () => {},
    setTimeout: callback => { timers.push(callback); return timers.length; },
    clearTimeout: id => { if (id) timers[id - 1] = null; },
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
    recognitions,
    fetchUrls,
    settleCapabilities: () => new Promise(resolve => setImmediate(resolve)),
    runTimers: () => timers.splice(0).forEach(callback => { if (callback) callback(); }),
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
  assert.ok(runtime.transcripts.includes('想去安静一点的地方。'));
  assert.equal(runtime.tracks[0].stopped, false, 'a stable sentence is not the end of the stream');
  socket.receive({ code: 0, final: 1 });
  assert.ok(runtime.transcripts.includes('final:想去安静一点的地方。'));
  assert.equal(runtime.tracks[0].stopped, true);
  assert.deepEqual(runtime.errors, []);
});

test('Tencent keeps and punctuates every finalized sentence slice', async () => {
  const runtime = makeVoiceRuntime();
  await runtime.current.toggleVoice(runtime.callbacks);
  const socket = runtime.sockets[0];
  socket.open();
  socket.receive({ code: 0, message: 'success' });
  socket.receive({ code: 0, result: { index: 0, voice_text_str: '今天开完会很累', slice_type: 2 } });
  socket.receive({ code: 0, result: { index: 1, voice_text_str: '想找个人少的地方', slice_type: 2 } });
  await runtime.current.toggleVoice(runtime.callbacks);
  socket.receive({ code: 0, final: 1 });

  assert.ok(runtime.transcripts.includes('今天开完会很累，想找个人少的地方。'));
  assert.ok(runtime.transcripts.includes('final:今天开完会很累，想找个人少的地方。'));
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

test('browser dictation is a real first-tap fallback when Tencent is not configured', async () => {
  const runtime = makeVoiceRuntime({ browserSpeech: true, tencentConfigured: false });
  await runtime.settleCapabilities();

  await runtime.current.toggleVoice(runtime.callbacks);
  const recognition = runtime.recognitions[0];
  assert.equal(recognition.started, true);
  assert.equal(recognition.lang, 'zh-CN');
  assert.equal(recognition.continuous, true);
  assert.equal(recognition.interimResults, true);
  assert.equal(recognition.maxAlternatives, 1);
  assert.ok(runtime.statuses.includes('我在听，再按一次结束'));
  assert.equal(runtime.fetchUrls.some(url => url.endsWith('/asr/signature')), false);
  assert.equal(runtime.sockets.length, 0);

  recognition.result([{ text: '想去安静一点的地方', final: false }]);
  assert.ok(runtime.transcripts.includes('想去安静一点的地方'));
  recognition.result([{ text: '想去安静一点的地方', final: true }]);
  assert.ok(runtime.transcripts.includes('想去安静一点的地方。'));
  assert.equal(recognition.stopped, undefined, 'a stable phrase is not permission to stop');
  assert.equal(runtime.transcripts.some(text => text.startsWith('final:')), false);
  await runtime.current.toggleVoice(runtime.callbacks);
  assert.equal(recognition.stopped, true);
  recognition.end();

  assert.equal(runtime.transcripts.filter(text => text === 'final:想去安静一点的地方。').length, 1);
  assert.deepEqual(runtime.errors, []);
});

test('browser dictation punctuates stable phrases without changing recognized words', async () => {
  const runtime = makeVoiceRuntime({ browserSpeech: true, tencentConfigured: false });
  await runtime.settleCapabilities();

  await runtime.current.toggleVoice(runtime.callbacks);
  const recognition = runtime.recognitions[0];
  recognition.result([
    { text: '今天开完会很累', final: true },
    { text: '想找个人少的地方', final: true },
  ]);
  await runtime.current.toggleVoice(runtime.callbacks);
  recognition.end();

  assert.ok(runtime.transcripts.includes('今天开完会很累，想找个人少的地方。'));
  assert.ok(runtime.transcripts.includes('final:今天开完会很累，想找个人少的地方。'));
});

test('browser dictation uses a question mark for an explicit Chinese question', async () => {
  const runtime = makeVoiceRuntime({ browserSpeech: true, tencentConfigured: false });
  await runtime.settleCapabilities();

  await runtime.current.toggleVoice(runtime.callbacks);
  const recognition = runtime.recognitions[0];
  recognition.result([{ text: '附近有可以打羽毛球的地方吗', final: true }]);
  await runtime.current.toggleVoice(runtime.callbacks);
  recognition.end();

  assert.ok(runtime.transcripts.includes('final:附近有可以打羽毛球的地方吗？'));
});

test('browser dictation errors clean up and allow a fresh retry', async () => {
  const runtime = makeVoiceRuntime({ browserSpeech: true, tencentConfigured: false });
  await runtime.settleCapabilities();

  await runtime.current.toggleVoice(runtime.callbacks);
  runtime.recognitions[0].error('not-allowed');
  assert.match(runtime.errors[0], /没有获得语音或麦克风权限/);

  await runtime.current.toggleVoice(runtime.callbacks);
  assert.equal(runtime.recognitions.length, 2);
  assert.equal(runtime.recognitions[1].started, true);
});

test('a browser recognizer that never starts times out and permits retry', async () => {
  const runtime = makeVoiceRuntime({
    browserSpeech: true,
    tencentConfigured: false,
    suppressRecognitionStart: true,
  });
  await runtime.settleCapabilities();

  await runtime.current.toggleVoice(runtime.callbacks);
  runtime.runTimers();

  assert.equal(runtime.recognitions[0].aborted, true);
  assert.match(runtime.errors[0], /语音没有启动/);
  await runtime.current.toggleVoice(runtime.callbacks);
  assert.equal(runtime.recognitions.length, 2);
});

test('Tencent is tried when the capability endpoint is offline', async () => {
  const runtime = makeVoiceRuntime({
    browserSpeech: true,
    capabilityError: new Error('backend offline'),
  });
  await runtime.settleCapabilities();

  await runtime.current.toggleVoice(runtime.callbacks);

  assert.equal(runtime.recognitions.length, 0);
  assert.equal(runtime.fetchUrls.some(url => url.endsWith('/asr/signature')), true);
  assert.equal(runtime.sockets.length, 1);
});

test('a fast first tap does not mistake an unresolved capability probe for Tencent being unavailable', async () => {
  const runtime = makeVoiceRuntime({ browserSpeech: true, tencentConfigured: true });

  await runtime.current.toggleVoice(runtime.callbacks);

  assert.equal(runtime.recognitions.length, 0);
  assert.equal(runtime.fetchUrls.some(url => url.endsWith('/asr/signature')), true);
  assert.equal(runtime.sockets.length, 1);
});

test('Tencent remains primary when configured and a failed session offers browser retry', async () => {
  const runtime = makeVoiceRuntime({ browserSpeech: true, tencentConfigured: true });
  await runtime.settleCapabilities();

  await runtime.current.toggleVoice(runtime.callbacks);
  assert.equal(runtime.recognitions.length, 0);
  const socket = runtime.sockets[0];
  socket.open();
  socket.receive({ code: 6001 });
  assert.match(runtime.errors[0], /再点一次麦克风可以重试/);

  await runtime.current.toggleVoice(runtime.callbacks);
  assert.equal(runtime.recognitions.length, 1);
  assert.equal(runtime.recognitions[0].started, true);
});

test('the regional capability can start browser dictation on the first tap', async () => {
  const runtime = makeVoiceRuntime({
    browserSpeech: true,
    tencentConfigured: true,
    preferredProvider: 'browser',
  });
  await runtime.settleCapabilities();

  await runtime.current.toggleVoice(runtime.callbacks);

  assert.equal(runtime.recognitions.length, 1);
  assert.equal(runtime.recognitions[0].started, true);
  assert.equal(runtime.fetchUrls.some(url => url.endsWith('/asr/signature')), false);
  assert.equal(runtime.sockets.length, 0);
});

test('embedded browsers without Web Speech still try the configured realtime microphone', async () => {
  const runtime = makeVoiceRuntime({
    tencentConfigured: true,
    preferredProvider: 'browser',
  });
  await runtime.settleCapabilities();

  await runtime.current.toggleVoice(runtime.callbacks);

  assert.equal(runtime.fetchUrls.some(url => url.endsWith('/asr/signature')), true);
  assert.equal(runtime.sockets.length, 1);
});
