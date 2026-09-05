(function () {
  'use strict';

  var localApi = (location.hostname === 'localhost' || location.hostname === '127.0.0.1') && location.port === '8000'
    ? 'http://127.0.0.1:8001/api/v1'
    : '/api/v1';
  var API_BASE = (window.CURRENT_API_BASE || localApi).replace(/\/$/, '');
  var SESSION_KEY = 'current.session.v1';
  var activeVoice = null;
  var activeLocation = null;

  function sessionId() {
    try {
      var existing = localStorage.getItem(SESSION_KEY);
      if (existing) return existing;
      var value = 'ses_' + (crypto.randomUUID ? crypto.randomUUID() : Date.now() + '_' + Math.random().toString(16).slice(2));
      localStorage.setItem(SESSION_KEY, value);
      return value;
    } catch (_) {
      return 'ses_' + Date.now() + '_private';
    }
  }

  async function api(path, options) {
    var response = await fetch(API_BASE + path, Object.assign({
      headers: { 'Content-Type': 'application/json', 'X-Session-Id': sessionId() }
    }, options || {}));
    if (!response.ok) {
      var detail = '';
      try { detail = (await response.json()).detail || ''; } catch (_) {}
      throw new Error(detail || '请求失败，请稍后再试');
    }
    return response.json();
  }

  function track(name, properties) {
    var safe = properties || {};
    if (typeof window.va === 'function') window.va('event', { name: name, data: safe });
    api('/events', {
      method: 'POST',
      body: JSON.stringify({
        name: name,
        session_id: sessionId(),
        recommendation_id: safe.recommendation_id || null,
        place_id: safe.place_id || null,
        properties: safe
      })
    }).catch(function () {});
  }

  function interpretAndRecommend(text) {
    return api('/interpret', { method: 'POST', body: JSON.stringify({ text: text }) })
      .then(function (interpretation) {
        track('natural_language_interpreted', {
          source: interpretation.source,
          mood_id: interpretation.state.mood_id,
          need_count: interpretation.state.need_keys.length,
          risk_level: interpretation.state.risk_level
        });
        return api('/recommendations', {
          method: 'POST',
          body: JSON.stringify({ state: interpretation.state, location: activeLocation, limit: 3 })
        }).then(function (recommendations) {
          return { interpretation: interpretation, recommendations: recommendations };
        });
      });
  }

  function requestLocation() {
    if (activeLocation) return Promise.resolve(activeLocation);
    if (!navigator.geolocation) return Promise.reject(new Error('当前浏览器不支持定位'));
    return new Promise(function (resolve, reject) {
      navigator.geolocation.getCurrentPosition(function (position) {
        // Kept only in page memory. The backend uses it for this route request and
        // deliberately excludes it from logs and persistence.
        activeLocation = {
          latitude: position.coords.latitude,
          longitude: position.coords.longitude
        };
        resolve(activeLocation);
      }, function () {
        reject(new Error('没有获得位置权限，仍可以按原型距离推荐'));
      }, { enableHighAccuracy: false, timeout: 8000, maximumAge: 300000 });
    });
  }

  var WORKLET_SOURCE = `
    class CurrentPcmProcessor extends AudioWorkletProcessor {
      process(inputs) {
        const channel = inputs[0] && inputs[0][0];
        if (!channel) return true;
        const count = Math.max(1, Math.round(channel.length * 16000 / sampleRate));
        const out = new Int16Array(count);
        for (let i = 0; i < count; i++) {
          const sourceIndex = Math.min(channel.length - 1, Math.floor(i * sampleRate / 16000));
          const sample = Math.max(-1, Math.min(1, channel[sourceIndex]));
          out[i] = sample < 0 ? sample * 0x8000 : sample * 0x7fff;
        }
        this.port.postMessage(out.buffer, [out.buffer]);
        return true;
      }
    }
    registerProcessor('current-pcm', CurrentPcmProcessor);
  `;

  async function beginVoice(callbacks) {
    if (activeVoice) throw new Error('录音已经开始');
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia || !window.AudioWorkletNode) {
      throw new Error('当前浏览器不支持语音录入，请改用文字');
    }

    callbacks.onStatus('正在请求麦克风…');
    track('natural_language_started', { method: 'voice' });
    var signature = await api('/asr/signature');
    var stream = await navigator.mediaDevices.getUserMedia({ audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true } });
    var context = new (window.AudioContext || window.webkitAudioContext)();
    var source = context.createMediaStreamSource(stream);
    var analyser = context.createAnalyser();
    analyser.fftSize = 512;
    source.connect(analyser);

    var blobUrl = URL.createObjectURL(new Blob([WORKLET_SOURCE], { type: 'application/javascript' }));
    await context.audioWorklet.addModule(blobUrl);
    URL.revokeObjectURL(blobUrl);
    var processor = new AudioWorkletNode(context, 'current-pcm', { numberOfInputs: 1, numberOfOutputs: 1, channelCount: 1 });
    source.connect(processor);
    processor.connect(context.destination);

    var socket = new WebSocket(signature.url);
    var latestText = '';
    var finished = false;
    var stopRequested = false;
    var quietSince = 0;
    var timer = null;
    var finishTimer = null;

    function cleanup() {
      if (timer) clearInterval(timer);
      if (finishTimer) clearTimeout(finishTimer);
      try { processor.port.onmessage = null; processor.disconnect(); } catch (_) {}
      try { source.disconnect(); analyser.disconnect(); } catch (_) {}
      stream.getTracks().forEach(function (track) { track.stop(); });
      context.close().catch(function () {});
      activeVoice = null;
    }

    function fail(message) {
      if (finished) return;
      finished = true;
      try { socket.close(); } catch (_) {}
      cleanup();
      callbacks.onError(message);
    }

    function finish() {
      if (finished) return;
      finished = true;
      cleanup();
      if (latestText.trim()) callbacks.onText(latestText.trim());
      else callbacks.onError('没有听清，可以再说一次或改用文字');
    }

    function stop() {
      if (finished || stopRequested) return;
      stopRequested = true;
      callbacks.onStatus('正在整理你刚才说的…');
      if (socket.readyState === WebSocket.OPEN) socket.send(JSON.stringify({ type: 'end' }));
      finishTimer = setTimeout(finish, 5000);
    }

    activeVoice = { stop: stop };
    processor.port.onmessage = function (event) {
      if (!finished && socket.readyState === WebSocket.OPEN) socket.send(event.data);
    };
    socket.onopen = function () { callbacks.onStatus('我在听，再按一次结束'); };
    socket.onmessage = function (event) {
      if (typeof event.data !== 'string') return;
      try {
        var message = JSON.parse(event.data);
        if (message.code !== undefined && message.code !== 0) return fail(message.message || '语音识别失败');
        var result = message.result || {};
        var text = result.voice_text_str || message.text || '';
        if (text) { latestText = text; callbacks.onPartial(text); }
        if (message.final === 1 || (result.slice_type === 2 && latestText)) finish();
      } catch (_) {}
    };
    socket.onerror = function () { fail('语音连接失败，请改用文字'); };
    socket.onclose = function () { if (!finished) finish(); };

    var samples = new Uint8Array(analyser.fftSize);
    timer = setInterval(function () {
      analyser.getByteTimeDomainData(samples);
      var energy = 0;
      for (var i = 0; i < samples.length; i++) {
        var normalized = (samples[i] - 128) / 128;
        energy += normalized * normalized;
      }
      var rms = Math.sqrt(energy / samples.length);
      if (rms < 0.035) {
        if (!quietSince) quietSince = Date.now();
        if (Date.now() - quietSince > 5000) stop();
      } else quietSince = 0;
    }, 200);
  }

  function toggleVoice(callbacks) {
    if (activeVoice) {
      activeVoice.stop();
      return Promise.resolve('stopping');
    }
    return beginVoice(callbacks).then(function () { return 'recording'; });
  }

  window.CurrentAI = {
    api: api,
    sessionId: sessionId,
    track: track,
    interpretAndRecommend: interpretAndRecommend,
    requestLocation: requestLocation,
    toggleVoice: toggleVoice
  };
})();
