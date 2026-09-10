(function () {
  'use strict';

  var localApi = (location.hostname === 'localhost' || location.hostname === '127.0.0.1') && location.port === '8000'
    ? 'http://127.0.0.1:8001/api/v1'
    : '/api/v1';
  var API_BASE = (window.CURRENT_API_BASE || localApi).replace(/\/$/, '');
  var SESSION_KEY = 'current.session.v1';
  var activeVoice = null;
  var activeLocation = null;
  var activeLocationMode = null;
  // 公开的演示起点，不代表评委当前位置。坐标采用高德使用的 GCJ-02。
  var BEIJING_DEMO_ORIGIN = { latitude: 39.9244, longitude: 116.4173 };

  // 第三方服务的错误原文可能很长，甚至夹带控制台和付费链接。
  // 第一屏只告诉用户下一步能做什么，不把供应商后台文案直接甩给人。
  function voiceErrorMessage(message) {
    var code = Number(message && message.code);
    if (code === 6001) return '当前网络像是经过了境外代理。关闭 VPN 后再试，或者直接打字。';
    if (code === 4003) return '语音功能还没有开通，请先直接打字。';
    if (code === 4004 || code === 4005) return '语音额度暂时不可用，请先直接打字。';
    if (code === 4006) return '现在说话的人有点多，请稍后再试或直接打字。';
    if (code === 4007) return '这段声音没有识别出来，可以再说一次或直接打字。';
    if (code === 5000 || code === 5001 || code === 5002) return '语音连接刚刚抖了一下，可以再试一次或直接打字。';
    return '语音暂时没有接住，请再试一次或直接打字。';
  }

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

  // Re-rank without re-interpreting: used by the correction chips and by the
  // single clarifying answer, so a fix costs one request instead of two.
  function recommendFor(needState, rejected) {
    return api('/recommendations', {
      method: 'POST',
      body: JSON.stringify({
        state: needState,
        location: activeLocation,
        rejected_place_ids: rejected || [],
        limit: 3
      })
    });
  }

  // FR-12：删除是个承诺，不能只在本地抹掉、服务端还留着。
  function deleteOutcome(recommendationId) {
    return api('/outcomes/delete', {
      method: 'POST',
      body: JSON.stringify({ session_id: sessionId(), recommendation_id: recommendationId })
    });
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
        return recommendFor(interpretation.state).then(function (recommendations) {
          return { interpretation: interpretation, recommendations: recommendations };
        });
      });
  }

  function requestLocation() {
    if (activeLocation && activeLocationMode === 'real') return Promise.resolve(activeLocation);
    if (!navigator.geolocation) return Promise.reject(new Error('当前浏览器不支持定位'));
    return new Promise(function (resolve, reject) {
      navigator.geolocation.getCurrentPosition(function (position) {
        var latitude = position.coords.latitude;
        var longitude = position.coords.longitude;
        // 北京是当前唯一开放的真实地点库。跨城步行没有意义，也不能把上海或
        // 深圳的位置伪装成北京起点；异地用户应显式选择体验模式。
        var inBeijingPilot = latitude >= 39.4 && latitude <= 41.1 && longitude >= 115.4 && longitude <= 117.6;
        if (!inBeijingPilot) {
          activeLocation = null;
          activeLocationMode = null;
          reject(new Error('你现在不在北京。可以选择「体验北京」，路线会从北京东四开始算。'));
          return;
        }
        // Kept only in page memory. The backend uses it for this route request and
        // deliberately excludes it from logs and persistence.
        // 浏览器给 WGS-84，高德路线接口收 GCJ-02，所以只在内存中转换一次。
        activeLocation = wgs2gcj(latitude, longitude);
        activeLocationMode = 'real';
        resolve(activeLocation);
      }, function () {
        reject(new Error('没有获得位置权限，仍可以按原型距离推荐'));
      }, { enableHighAccuracy: false, timeout: 8000, maximumAge: 300000 });
    });
  }

  function useBeijingDemo() {
    stopPresence();
    activeLocation = { latitude: BEIJING_DEMO_ORIGIN.latitude, longitude: BEIJING_DEMO_ORIGIN.longitude };
    activeLocationMode = 'demo';
    return activeLocation;
  }

  // ---- 在场证明 L1（FR-08）----------------------------------------------
  // 围栏判定整个在这里完成。用户的经纬度只进这个闭包，既不上传，也不写进
  // 任何事件属性——上传的只有「进没进围栏」和「待了多久」。
  var activePresence = null;

  function metersBetween(a, b) {
    var R = 6371000;
    var toRad = function (d) { return d * Math.PI / 180; };
    var dLat = toRad(b.latitude - a.latitude);
    var dLon = toRad(b.longitude - a.longitude);
    var lat1 = toRad(a.latitude), lat2 = toRad(b.latitude);
    var h = Math.sin(dLat / 2) * Math.sin(dLat / 2) +
            Math.cos(lat1) * Math.cos(lat2) * Math.sin(dLon / 2) * Math.sin(dLon / 2);
    return 2 * R * Math.asin(Math.min(1, Math.sqrt(h)));
  }

  // 高德坐标是 GCJ-02，浏览器定位是 WGS-84。中国境内两者能差几百米，
  // 直接比会让围栏判定系统性偏移，所以先把 WGS-84 转成 GCJ-02 再比。
  var GCJ_A = 6378245.0, GCJ_EE = 0.00669342162296594323;
  function outOfChina(lat, lon) {
    return lon < 72.004 || lon > 137.8347 || lat < 0.8293 || lat > 55.8271;
  }
  function transformLat(x, y) {
    var ret = -100 + 2 * x + 3 * y + 0.2 * y * y + 0.1 * x * y + 0.2 * Math.sqrt(Math.abs(x));
    ret += (20 * Math.sin(6 * x * Math.PI) + 20 * Math.sin(2 * x * Math.PI)) * 2 / 3;
    ret += (20 * Math.sin(y * Math.PI) + 40 * Math.sin(y / 3 * Math.PI)) * 2 / 3;
    ret += (160 * Math.sin(y / 12 * Math.PI) + 320 * Math.sin(y * Math.PI / 30)) * 2 / 3;
    return ret;
  }
  function transformLon(x, y) {
    var ret = 300 + x + 2 * y + 0.1 * x * x + 0.1 * x * y + 0.1 * Math.sqrt(Math.abs(x));
    ret += (20 * Math.sin(6 * x * Math.PI) + 20 * Math.sin(2 * x * Math.PI)) * 2 / 3;
    ret += (20 * Math.sin(x * Math.PI) + 40 * Math.sin(x / 3 * Math.PI)) * 2 / 3;
    ret += (150 * Math.sin(x / 12 * Math.PI) + 300 * Math.sin(x / 30 * Math.PI)) * 2 / 3;
    return ret;
  }
  function wgs2gcj(lat, lon) {
    if (outOfChina(lat, lon)) return { latitude: lat, longitude: lon };
    var dLat = transformLat(lon - 105, lat - 35);
    var dLon = transformLon(lon - 105, lat - 35);
    var radLat = lat / 180 * Math.PI;
    var magic = 1 - GCJ_EE * Math.sin(radLat) * Math.sin(radLat);
    var sqrtMagic = Math.sqrt(magic);
    dLat = (dLat * 180) / ((GCJ_A * (1 - GCJ_EE)) / (magic * sqrtMagic) * Math.PI);
    dLon = (dLon * 180) / (GCJ_A / sqrtMagic * Math.cos(radLat) * Math.PI);
    return { latitude: lat + dLat, longitude: lon + dLon };
  }

  // fence: {latitude, longitude, radius_m}（高德 GCJ-02）。
  // callbacks.onState({inside, dwellMinutes, level, accuracyM})
  function watchPresence(fence, callbacks) {
    stopPresence();
    if (activeLocationMode === 'demo') {
      callbacks.onUnavailable('北京体验模式不启用到访验证');
      return null;
    }
    if (!fence || !navigator.geolocation) return null;

    var insideSince = null;
    var lastLevel = 'self_reported';

    function emit(inside, accuracy) {
      var dwellMinutes = insideSince ? Math.floor((Date.now() - insideSince) / 60000) : 0;
      lastLevel = inside && dwellMinutes >= 5 ? 'geofence_dwell' : lastLevel;
      callbacks.onState({ inside: inside, dwellMinutes: dwellMinutes, level: lastLevel, accuracyM: Math.round(accuracy || 0) });
    }

    var id = navigator.geolocation.watchPosition(function (position) {
      var here = wgs2gcj(position.coords.latitude, position.coords.longitude);
      var distance = metersBetween(here, fence);
      // 定位误差算进围栏，否则室内定位会把真到了的人判成没到。
      var inside = distance <= fence.radius_m + Math.min(position.coords.accuracy || 0, 200);
      if (inside && !insideSince) insideSince = Date.now();
      if (!inside) insideSince = null;
      emit(inside, position.coords.accuracy);
    }, function () {
      callbacks.onUnavailable('没有位置权限，到了按一下就行');
    }, { enableHighAccuracy: true, timeout: 15000, maximumAge: 30000 });

    var ticker = setInterval(function () { if (insideSince) emit(true, 0); }, 30000);
    activePresence = { id: id, ticker: ticker };
    return activePresence;
  }

  function stopPresence() {
    if (!activePresence) return;
    try { navigator.geolocation.clearWatch(activePresence.id); } catch (_) {}
    clearInterval(activePresence.ticker);
    activePresence = null;
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
        if (message.code !== undefined && message.code !== 0) return fail(voiceErrorMessage(message));
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
    recommendFor: recommendFor,
    deleteOutcome: deleteOutcome,
    hasLocation: function () { return Boolean(activeLocation); },
    getLocationMode: function () { return activeLocationMode; },
    useBeijingDemo: useBeijingDemo,
    requestLocation: requestLocation,
    watchPresence: watchPresence,
    stopPresence: stopPresence,
    toggleVoice: toggleVoice
  };
})();
