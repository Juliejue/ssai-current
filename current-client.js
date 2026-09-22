(function () {
  'use strict';

  var localApi = (location.hostname === 'localhost' || location.hostname === '127.0.0.1') && location.port === '8000'
    ? 'http://127.0.0.1:8001/api/v1'
    : '/api/v1';
  var API_BASE = (window.CURRENT_API_BASE || localApi).replace(/\/$/, '');
  var SESSION_KEY = 'current.session.v1';
  var RELAY_KEY = 'current.relay.v1';
  var RELAY_ROLE_KEY = 'current.role.v1';
  var relayPollTimer = null;
  var activeVoice = null;
  var tencentVoiceConfigured = null;
  var preferredVoiceProvider = null;
  var preferBrowserVoice = false;
  var activeLocation = null;
  var activeLocationMode = null;
  var activeLocationCity = null;
  var PILOT_BOUNDS = [
    {name:'北京', minLat:39.4, maxLat:41.1, minLng:115.4, maxLng:117.6},
    {name:'上海', minLat:30.7, maxLat:31.9, minLng:120.8, maxLng:122.2},
    {name:'广州', minLat:22.85, maxLat:23.9, minLng:112.7, maxLng:114.2},
    {name:'深圳', minLat:22.3, maxLat:22.85, minLng:113.7, maxLng:114.7}
  ];
  // 公开的演示起点，不代表评委当前位置。坐标采用高德使用的 GCJ-02。
  var BEIJING_DEMO_ORIGIN = { latitude: 39.9244, longitude: 116.4173 };
  var tripDemoEnabled = false;
  try { tripDemoEnabled = new URLSearchParams(location.search || '').get('demo') === 'trip'; } catch (_) {}

  if ('serviceWorker' in navigator && window.addEventListener) {
    window.addEventListener('load', function () {
      navigator.serviceWorker.register('/sw.js').catch(function () {});
    });
  }

  // This request carries no session id or user data. It lets a microphone tap
  // choose a provider synchronously, which matters on browsers that require
  // speech recognition to start inside the original user gesture.
  if (typeof fetch === 'function') {
    try {
      fetch(API_BASE + '/asr/capabilities', { credentials: 'omit', cache: 'no-store' })
        .then(function (response) {
          if (!response.ok) throw new Error('voice capabilities unavailable');
          return response.json();
        })
        .then(function (capabilities) {
          if (typeof capabilities.tencent_realtime === 'boolean') {
            tencentVoiceConfigured = capabilities.tencent_realtime;
          }
          if (capabilities.preferred_provider === 'browser' || capabilities.preferred_provider === 'tencent') {
            preferredVoiceProvider = capabilities.preferred_provider;
          }
        })
        .catch(function () {});
    } catch (_) {}
  }

  function voiceCopy(zh, en) {
    return lang() === 'en' ? en : zh;
  }

  function browserSpeechClass() {
    return window.SpeechRecognition || window.webkitSpeechRecognition || null;
  }

  function normalizeSpeechText(text) {
    return String(text || '')
      .replace(/[\t\r\n ]+/g, ' ')
      .replace(/\s+([，。！？；：、])/g, '$1')
      .replace(/([，。！？；：、])\s+/g, '$1')
      .trim();
  }

  function speechHasCjk(text) {
    return /[\u3400-\u9fff]/.test(text);
  }

  function speechEndsWithMark(text) {
    return /[。！？.!?…]$/.test(text);
  }

  function speechLooksLikeQuestion(text) {
    var clean = text.replace(/[，,；;：:、\s]+$/g, '');
    if (speechHasCjk(clean)) {
      return /(?:吗|么|呢|嘛)[啊呀呢嘛]?$/.test(clean) ||
        /(?:是不是|能不能|可不可以|要不要|有没有|好不好|行不行)[啊呀呢嘛]?$/.test(clean) ||
        /^(?:为什么|怎么|哪里|哪儿|谁|什么|几|多少|什么时候|几点)/.test(clean);
    }
    return /^(?:who|what|when|where|why|how|is|are|am|was|were|do|does|did|can|could|would|will|should|have|has)\b/i.test(clean);
  }

  // Speech providers disagree about punctuation. Keep every recognized word
  // untouched, but make the editable hand-off read like a complete sentence.
  function formatSpeechTranscript(text) {
    var formatted = normalizeSpeechText(text);
    if (!formatted || speechEndsWithMark(formatted)) return formatted;
    formatted = formatted.replace(/[，,；;：:、]+$/g, '');
    if (!formatted) return '';
    if (speechHasCjk(formatted)) return formatted + (speechLooksLikeQuestion(formatted) ? '？' : '。');
    return formatted + (speechLooksLikeQuestion(formatted) ? '?' : '.');
  }

  function joinSpeechParts(parts) {
    var output = '';
    var previousFinal = false;
    (parts || []).forEach(function (part) {
      var text = normalizeSpeechText(part && part.text);
      if (!text) return;
      if (output) {
        if (previousFinal && !/[，。！？；：、,.!?;:…]$/.test(output)) {
          output += speechHasCjk(output + text) ? '，' : ' ';
        } else if (!speechHasCjk(output + text) && !/\s$/.test(output)) {
          output += ' ';
        }
      }
      output += text;
      previousFinal = Boolean(part && part.final);
    });
    return output.trim();
  }

  function speechPreview(parts) {
    var joined = joinSpeechParts(parts);
    var last = (parts || []).filter(function (part) {
      return normalizeSpeechText(part && part.text);
    }).pop();
    // A provider's "final" flag means this phrase is stable. Show punctuation
    // immediately instead of making the user wait until the whole microphone
    // session ends. If they keep speaking, the next update rebuilds the line.
    return last && last.final ? formatSpeechTranscript(joined) : joined;
  }

  // 第三方服务的错误原文可能很长，甚至夹带控制台和付费链接。
  // 第一屏只告诉用户下一步能做什么，不把供应商后台文案直接甩给人。
  function voiceErrorMessage(message) {
    var code = Number(message && message.code);
    // 6001 是腾讯判定这条连接「跨境」。原因可能是用户挂了 VPN，也可能是
    // 账号没开跨境流量——我们分不清是哪种，所以别一口咬定是用户的错。
    if (code === 6001) return voiceCopy('语音服务没有连上。', 'Voice input could not connect.');
    if (code === 4003 || code === 4004 || code === 4005 || code === 4006) {
      return voiceCopy('语音暂时不可用，可以直接打字。', 'Voice input is unavailable. You can type instead.');
    }
    if (code === 4007) return voiceCopy('这段声音没有识别出来。', 'That speech could not be recognized.');
    if (code === 4000 || code === 4008 || code === 4009) return voiceCopy('语音连接刚刚中断。', 'The speech connection was interrupted.');
    if (code === 4001 || code === 4002 || code === 4010) return voiceCopy('语音暂时不可用，可以直接打字。', 'Voice input is unavailable. You can type instead.');
    if (code === 5000 || code === 5001 || code === 5002) return voiceCopy('语音连接刚刚抖了一下。', 'The speech connection dropped for a moment.');
    return voiceCopy('语音暂时没有接住。', 'Speech recognition did not catch that.');
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

  function deviceRole() {
    try {
      var requested = new URLSearchParams(location.search || '').get('role');
      if (requested === 'phone' || requested === 'desk') return requested;
    } catch (_) {}
    try {
      var forced = localStorage.getItem(RELAY_ROLE_KEY);
      if (forced === 'phone' || forced === 'desk') return forced;
    } catch (_) {}
    var touch = Boolean((navigator && navigator.maxTouchPoints > 0) || ('ontouchstart' in window));
    var narrow = typeof window.innerWidth === 'number' ? window.innerWidth <= 820 : false;
    return touch && narrow ? 'phone' : 'desk';
  }

  function setDeviceRole(role) {
    if (role !== 'phone' && role !== 'desk') return deviceRole();
    try { localStorage.setItem(RELAY_ROLE_KEY, role); } catch (_) {}
    return role;
  }

  function loadRelay() {
    try {
      var saved = JSON.parse(localStorage.getItem(RELAY_KEY) || 'null');
      if (!saved || !/^[2-9A-HJ-NP-Z]{6}$/.test(saved.code || '')) return null;
      if (saved.expiresAt && Date.parse(saved.expiresAt) <= Date.now()) {
        localStorage.removeItem(RELAY_KEY);
        return null;
      }
      return { code: saved.code, expiresAt: saved.expiresAt || null,
        lastSequence: Math.max(0, Number(saved.lastSequence) || 0), durable: Boolean(saved.durable) };
    } catch (_) { return null; }
  }

  function saveRelay(relay) {
    try {
      if (relay) localStorage.setItem(RELAY_KEY, JSON.stringify(relay));
      else localStorage.removeItem(RELAY_KEY);
    } catch (_) {}
    return relay;
  }

  function relayCode(value) {
    return String(value || '').toUpperCase().replace(/[^A-Z0-9]/g, '').slice(0, 6);
  }

  function relayPendingCode() {
    try { return relayCode(new URLSearchParams(location.search || '').get('relay')); }
    catch (_) { return ''; }
  }

  function dispatchRelayEvent(event) {
    if (!window.dispatchEvent || typeof window.CustomEvent !== 'function') return;
    window.dispatchEvent(new window.CustomEvent('current-relay-event', { detail: event }));
  }

  async function readRelay(relay) {
    var result = await api('/relay/' + encodeURIComponent(relay.code) + '?after=' + relay.lastSequence);
    var events = Array.isArray(result.events) ? result.events : [];
    events.forEach(function (event) {
      relay.lastSequence = Math.max(relay.lastSequence, Number(event.sequence) || 0);
      dispatchRelayEvent(event);
    });
    relay.expiresAt = result.expires_at || relay.expiresAt;
    relay.durable = Boolean(result.durable);
    saveRelay(relay);
    return events;
  }

  function scheduleRelayPoll(delay) {
    if (relayPollTimer !== null) clearTimeout(relayPollTimer);
    relayPollTimer = setTimeout(function poll() {
      var relay = loadRelay();
      if (!relay) { relayPollTimer = null; return; }
      readRelay(relay).catch(function (error) {
        if (/不存在|结束/.test(error && error.message || '')) saveRelay(null);
      }).finally(function () {
        if (loadRelay()) scheduleRelayPoll(2500);
      });
    }, typeof delay === 'number' ? delay : 2500);
  }

  async function createRelaySession() {
    var result = await api('/relay/sessions', { method: 'POST', body: '{}' });
    var relay = saveRelay({ code: relayCode(result.code), expiresAt: result.expires_at,
      lastSequence: 0, durable: Boolean(result.durable) });
    scheduleRelayPoll(0);
    return relay;
  }

  async function joinRelaySession(code) {
    var clean = relayCode(code);
    if (clean.length !== 6) throw new Error(voiceCopy('请输入 6 位会话码。', 'Enter the 6-character code.'));
    var result = await api('/relay/' + encodeURIComponent(clean) + '?after=0');
    var events = Array.isArray(result.events) ? result.events : [];
    var relay = saveRelay({ code: clean, expiresAt: result.expires_at,
      lastSequence: events.reduce(function (latest, event) { return Math.max(latest, Number(event.sequence) || 0); }, 0),
      durable: Boolean(result.durable) });
    events.forEach(dispatchRelayEvent);
    scheduleRelayPoll(2500);
    return relay;
  }

  function leaveRelaySession() {
    if (relayPollTimer !== null) clearTimeout(relayPollTimer);
    relayPollTimer = null;
    saveRelay(null);
  }

  async function publishRelay(eventType, payload) {
    var relay = loadRelay();
    if (!relay) return { accepted: false, disconnected: true };
    return api('/relay/' + encodeURIComponent(relay.code) + '/events', {
      method: 'POST', body: JSON.stringify({ event_type: eventType, payload: payload || {} })
    });
  }

  function relayShareUrl() {
    var relay = loadRelay();
    if (!relay) return '';
    return location.origin + location.pathname + '?relay=' + encodeURIComponent(relay.code) + '#/connect';
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

  /* 用户读到的内容大半是服务端生成的（状态、理由、为什么是这里、代价），
     所以语言必须跟着请求一起送过去，光在前端翻界面是不够的。 */
  function lang() {
    try { return localStorage.getItem('current.lang.v1') === 'en' ? 'en' : 'zh'; }
    catch (e) { return 'zh'; }
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
        limit: 3,
        lang: lang()
      })
    });
  }

  /* 离开之后说的那一句话 → 这次到访的结构化反馈。
     原话不入库，只把结果存下来（守则 6）。 */
  function reflectOn(text, context) {
    return api('/reflect', {
      method: 'POST',
      body: JSON.stringify({
        text: text,
        place_name: context.placeName || '',
        pre_mood: context.preMood || '',
        options: context.options || [],
        lang: lang()
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
    // 把位置一起送过去：模型读这句话要几秒，服务端可以在同一段时间里
    // 先把周边搜好，等用户点到推荐那一步就不用再等。
    return api('/interpret', { method: 'POST', body: JSON.stringify({
        text: text, lang: lang(), location: activeLocation }) })
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
    if (!navigator.geolocation) return Promise.reject(new Error(voiceCopy('当前浏览器不支持定位', 'Location is unavailable in this browser.')));
    return new Promise(function (resolve, reject) {
      navigator.geolocation.getCurrentPosition(function (position) {
        var latitude = position.coords.latitude;
        var longitude = position.coords.longitude;
        var city = PILOT_BOUNDS.find(function (item) {
          return latitude >= item.minLat && latitude <= item.maxLat &&
            longitude >= item.minLng && longitude <= item.maxLng;
        });
        if (!city) {
          activeLocation = null;
          activeLocationMode = null;
          activeLocationCity = null;
          reject(new Error(voiceCopy('当前位置暂未开放；目前支持北京、上海、广州和深圳。',
            'Your city is not open yet. Beijing, Shanghai, Guangzhou and Shenzhen are supported.')));
          return;
        }
        // Kept only in page memory. The backend uses it for this route request and
        // deliberately excludes it from logs and persistence.
        // 浏览器给 WGS-84，高德路线接口收 GCJ-02，所以只在内存中转换一次。
        activeLocation = wgs2gcj(latitude, longitude);
        activeLocationMode = 'real';
        activeLocationCity = city.name;
        resolve(activeLocation);
      }, function () {
        reject(new Error(voiceCopy('没有获得位置权限，仍可以继续推荐。', 'Location is off. Recommendations still work.')));
      }, { enableHighAccuracy: false, timeout: 8000, maximumAge: 300000 });
    });
  }

  function useBeijingDemo() {
    stopPresence();
    activeLocation = { latitude: BEIJING_DEMO_ORIGIN.latitude, longitude: BEIJING_DEMO_ORIGIN.longitude };
    activeLocationMode = tripDemoEnabled ? 'trip-demo' : 'demo';
    activeLocationCity = '北京';
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
    if (activeLocationMode === 'trip-demo' || callbacks.demoMode) {
      callbacks.onState({ inside: false, dwellMinutes: 0, level: 'self_reported', accuracyM: 0, demo: true });
      activePresence = { demo: true, callbacks: callbacks, inside: false };
      return activePresence;
    }
    if (!fence) {
      callbacks.onUnavailable('这个地点还没有可用的围栏，到了按一下就行');
      return null;
    }
    if (!navigator.geolocation) {
      callbacks.onUnavailable('当前浏览器不支持定位，到了按一下就行');
      return null;
    }

    var initialDwell = Math.max(0, Number(callbacks.initialDwellMinutes) || 0);
    var wasInside = Boolean(callbacks.initialInside);
    var currentlyInside = wasInside;
    var insideSince = wasInside ? Date.now() - initialDwell * 60000 : null;
    var lastLevel = callbacks.initialLevel || 'self_reported';
    var bestDwell = initialDwell;
    // 出围栏就立刻判「走了」会误判：在室内定位飘一下、绕到建筑背面，
    // 都会短暂掉出去。要连续在外面这么久，才算真的离开。
    var LEAVE_GRACE_MS = 3 * 60 * 1000;
    var outsideSince = null;
    var stopped = false;

    function emit(inside, accuracy) {
      var dwellMinutes = insideSince ? Math.floor((Date.now() - insideSince) / 60000) : 0;
      if (dwellMinutes > bestDwell) bestDwell = dwellMinutes;
      lastLevel = inside && dwellMinutes >= 5 ? 'geofence_dwell' : lastLevel;
      callbacks.onState({ inside: inside, dwellMinutes: dwellMinutes, level: lastLevel, accuracyM: Math.round(accuracy || 0) });
    }

    function processPosition(position) {
      if (stopped) return;
      var here = wgs2gcj(position.coords.latitude, position.coords.longitude);
      var distance = metersBetween(here, fence);
      var accuracy = Math.min(position.coords.accuracy || 0, 150);
      // 进入和离开使用不同半径。已经进过围栏后多给 50 米余量，避免室内
      // GPS 漂移让状态在「到了 / 没到」之间来回跳。
      var radius = fence.radius_m + accuracy + (wasInside ? 50 : 0);
      var inside = distance <= radius;
      currentlyInside = inside;
      if (inside) {
        if (!insideSince) insideSince = Date.now();
        outsideSince = null;
        wasInside = true;
      } else {
        if (wasInside) {
          if (!outsideSince) outsideSince = Date.now();
          // 连续在围栏外达到缓冲时间就提示离开。是否停够 5 分钟只影响
          // 证明等级，不应该阻止产品识别一趟很短的真实到访。
          if (Date.now() - outsideSince >= LEAVE_GRACE_MS) {
            wasInside = false;
            outsideSince = null;
            insideSince = null;
            if (callbacks.onLeft) callbacks.onLeft({ dwellMinutes: bestDwell, level: lastLevel });
            return;
          }
        }
      }
      emit(inside, position.coords.accuracy);
    }

    function locationUnavailable() {
      callbacks.onUnavailable('没有位置权限，到了按一下就行');
    }

    var locationOptions = { enableHighAccuracy: true, timeout: 15000, maximumAge: 30000 };
    var id;
    try {
      id = navigator.geolocation.watchPosition(processPosition, locationUnavailable, locationOptions);
    } catch (_) {
      locationUnavailable();
      return null;
    }

    // watchPosition 在页面隐藏时不会可靠交付更新。用户从地图 App 回来时
    // 立即补取一次当前位置，让抵达/离开状态不必等下一次自然更新。
    function refreshOnReturn() {
      if (document.visibilityState && document.visibilityState !== 'visible') return;
      navigator.geolocation.getCurrentPosition(processPosition, locationUnavailable, locationOptions);
    }
    function onVisibilityChange() { if (document.visibilityState === 'visible') refreshOnReturn(); }
    document.addEventListener('visibilitychange', onVisibilityChange);
    window.addEventListener('pageshow', refreshOnReturn);

    var ticker = setInterval(function () { if (insideSince) emit(currentlyInside, 0); }, 30000);
    activePresence = {
      id: id,
      ticker: ticker,
      stop: function () {
        stopped = true;
        document.removeEventListener('visibilitychange', onVisibilityChange);
        window.removeEventListener('pageshow', refreshOnReturn);
      }
    };
    return activePresence;
  }

  function demoPresence(action) {
    if (!activePresence || !activePresence.demo) return false;
    if (action === 'arrive') {
      activePresence.inside = true;
      activePresence.callbacks.onState({ inside: true, dwellMinutes: 0, level: 'self_reported', accuracyM: 0, demo: true });
      return true;
    }
    if (action === 'leave' && activePresence.inside) {
      activePresence.inside = false;
      activePresence.callbacks.onLeft({ dwellMinutes: 6, level: 'self_reported', demo: true });
      return true;
    }
    return false;
  }

  function stopPresence() {
    if (!activePresence) return;
    if (activePresence.stop) activePresence.stop();
    if (activePresence.id !== undefined) {
      try { navigator.geolocation.clearWatch(activePresence.id); } catch (_) {}
    }
    if (activePresence.ticker) clearInterval(activePresence.ticker);
    activePresence = null;
  }

  function voiceSetupError(error) {
    var name = error && error.name;
    var message = String(error && error.message || '');
    if (name === 'NotAllowedError' || name === 'SecurityError') {
      return voiceCopy(
        '没有麦克风权限。允许访问后可以再试，或者直接打字。',
        'Microphone access is blocked. Allow it and try again, or type instead.'
      );
    }
    if (name === 'NotFoundError') {
      return voiceCopy('没有找到可用的麦克风，请直接打字。', 'No microphone was found. Please type instead.');
    }
    if (name === 'NotReadableError' || name === 'AbortError') {
      return voiceCopy(
        '麦克风正被其他应用占用，请关掉占用它的应用后再试。',
        'Another app may be using the microphone. Close it and try again.'
      );
    }
    if (message.indexOf('ASR is not configured') >= 0) {
      return voiceCopy('语音暂时不可用，请直接打字。', 'Voice input is unavailable. Please type instead.');
    }
    return voiceCopy('语音暂时没有启动成功。', 'Voice input could not start.');
  }

  function browserSpeechErrorMessage(event) {
    var code = event && event.error;
    if (code === 'not-allowed' || code === 'service-not-allowed') {
      return voiceCopy(
        '没有获得语音或麦克风权限。允许访问后可以再试，或者直接打字。',
        'Speech or microphone access is blocked. Allow it and try again, or type instead.'
      );
    }
    if (code === 'audio-capture') {
      return voiceCopy('没有找到可用的麦克风，请直接打字。', 'No microphone was found. Please type instead.');
    }
    if (code === 'no-speech') {
      return voiceCopy('没有听到声音，可以再说一次或直接打字。', 'I did not hear any speech. Try again, or type instead.');
    }
    if (code === 'network') {
      return voiceCopy('语音服务没有连上，可以再试一次或直接打字。', 'Voice input could not connect. Try again, or type instead.');
    }
    if (code === 'language-not-supported') {
      return voiceCopy('当前语言暂不支持语音输入，请直接打字。', 'Voice input does not support this language. Please type instead.');
    }
    if (code === 'aborted') {
      return voiceCopy('听写刚刚被中断，可以再试一次或直接打字。', 'Dictation was interrupted. Try again, or type instead.');
    }
    return voiceCopy('语音暂时没有接住，可以再试一次或直接打字。', 'Voice input did not catch that. Try again, or type instead.');
  }

  function offerBrowserRetry(message) {
    if (!browserSpeechClass()) return message + voiceCopy(' 请再试一次或直接打字。', ' Try again, or type instead.');
    preferBrowserVoice = true;
    return message + voiceCopy(
      ' 再点一次麦克风可以重试，也可以直接打字。',
      ' Tap the microphone again to retry, or type instead.'
    );
  }

  function beginBrowserVoice(callbacks) {
    if (activeVoice) throw new Error(voiceCopy('录音已经开始', 'Recording has already started'));
    var SpeechRecognitionClass = browserSpeechClass();
    if (!SpeechRecognitionClass) {
      throw new Error(voiceCopy('当前浏览器不支持听写，请改用文字。', 'This browser does not support dictation. Please type instead.'));
    }

    var recognition;
    try { recognition = new SpeechRecognitionClass(); }
    catch (error) { throw new Error(voiceSetupError(error)); }

    var latestText = '';
    var finished = false;
    var stopRequested = false;
    var started = false;
    var startTimer = null;
    var controller = null;

    function cleanup() {
      if (startTimer) clearTimeout(startTimer);
      recognition.onstart = null;
      recognition.onresult = null;
      recognition.onerror = null;
      recognition.onnomatch = null;
      recognition.onend = null;
      if (activeVoice === controller) activeVoice = null;
    }

    function finish(message) {
      if (finished) return;
      finished = true;
      cleanup();
      if (message) callbacks.onError(message);
      else if (latestText.trim()) callbacks.onText(formatSpeechTranscript(latestText));
      else callbacks.onError(voiceCopy('没有听清，可以再说一次或改用文字。', 'I did not catch that. Try again, or type instead.'));
    }

    function stop() {
      if (finished || stopRequested) return;
      stopRequested = true;
      callbacks.onStatus(voiceCopy('正在整理你刚才说的…', 'Finishing what you just said…'));
      try { recognition.stop(); }
      catch (_) { finish(); }
    }

    controller = { provider: 'browser', stop: stop };
    activeVoice = controller;
    recognition.lang = lang() === 'en' ? 'en-US' : 'zh-CN';
    // A short pause is not consent to send. Keep listening until the user taps
    // the microphone again; some iOS browsers otherwise finalize one phrase
    // and end the session at the first natural pause.
    recognition.continuous = true;
    recognition.interimResults = true;
    recognition.maxAlternatives = 1;
    recognition.onstart = function () {
      started = true;
      if (startTimer) clearTimeout(startTimer);
      callbacks.onStatus(stopRequested
        ? voiceCopy('正在整理你刚才说的…', 'Finishing what you just said…')
        : voiceCopy('我在听，再按一次结束', 'Listening · tap again to stop'));
    };
    recognition.onresult = function (event) {
      var parts = [];
      var hasFinal = false;
      for (var i = 0; i < event.results.length; i++) {
        var result = event.results[i];
        if (result && result[0] && result[0].transcript) {
          parts.push({ text: result[0].transcript, final: Boolean(result.isFinal) });
        }
        if (result && result.isFinal) hasFinal = true;
      }
      latestText = joinSpeechParts(parts);
      if (latestText) callbacks.onPartial(speechPreview(parts));
      // `isFinal` means this phrase is stable, not that the user has finished
      // speaking. Only the explicit second tap may end the capture.
      if (hasFinal && !stopRequested) {
        callbacks.onStatus(voiceCopy('我还在听，再按一次结束', 'Still listening · tap again to stop'));
      }
    };
    recognition.onerror = function (event) { finish(browserSpeechErrorMessage(event)); };
    recognition.onnomatch = function () {
      finish(voiceCopy('没有听清，可以再说一次或改用文字。', 'I did not catch that. Try again, or type instead.'));
    };
    recognition.onend = function () { finish(); };

    callbacks.onStatus(voiceCopy('正在启动语音…', 'Starting voice input…'));
    track('natural_language_started', { method: 'voice_browser' });
    try { recognition.start(); }
    catch (error) {
      cleanup();
      throw new Error(voiceSetupError(error));
    }
    if (!started && !finished) {
      startTimer = setTimeout(function () {
        if (started || finished) return;
        try {
          if (typeof recognition.abort === 'function') recognition.abort();
          else recognition.stop();
        } catch (_) {}
        finish(voiceCopy(
          '语音没有启动，再点一次可以重试，也可以直接打字。',
          'Voice input did not start. Tap again to retry, or type instead.'
        ));
      }, 5000);
    }
    return Promise.resolve();
  }

  async function beginTencentVoice(callbacks) {
    if (activeVoice) throw new Error(voiceCopy('录音已经开始', 'Recording has already started'));
    var AudioContextClass = window.AudioContext || window.webkitAudioContext;
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia || !window.AudioWorkletNode || !AudioContextClass) {
      throw new Error(voiceCopy('当前浏览器无法使用语音输入，请改用文字。', 'This browser cannot use voice input. Please type instead.'));
    }

    // Prevent a fast double-tap from opening two microphones while permissions
    // and the ASR signature are still being requested.
    var stopDuringSetup = false;
    activeVoice = { stop: function () { stopDuringSetup = true; } };
    callbacks.onStatus(voiceCopy('正在请求麦克风…', 'Requesting microphone access…'));
    track('natural_language_started', { method: 'voice_tencent' });
    var stream = null;
    var context = null;
    var source = null;
    var processor = null;
    var sink = null;
    var socket = null;

    function cleanupSetup() {
      try { if (processor) processor.disconnect(); } catch (_) {}
      try { if (sink) sink.disconnect(); } catch (_) {}
      try { if (source) source.disconnect(); } catch (_) {}
      if (stream) stream.getTracks().forEach(function (track) { track.stop(); });
      if (context) context.close().catch(function () {});
      try { if (socket) socket.close(); } catch (_) {}
      activeVoice = null;
    }

    try {
      var signature = await api('/asr/signature');
      stream = await navigator.mediaDevices.getUserMedia({
        audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true, autoGainControl: true }
      });
      context = new AudioContextClass();
      if (!context.audioWorklet) throw new Error('AudioWorklet is unavailable');
      await context.resume();
      // The prototype is reachable at both /current and /current/. Keep the
      // worklet rooted so the trailing slash cannot turn this into
      // /current/voice-worklet.mjs.
      await context.audioWorklet.addModule(new URL('/voice-worklet.mjs', location.origin).href);

      source = context.createMediaStreamSource(stream);
      processor = new AudioWorkletNode(context, 'current-pcm', {
        numberOfInputs: 1,
        numberOfOutputs: 1,
        channelCount: 1
      });
      // Keep the worklet in the active audio graph without playing microphone
      // audio back to the user.
      sink = context.createGain();
      sink.gain.value = 0;
      processor.connect(sink);
      sink.connect(context.destination);

      socket = new WebSocket(signature.url);
      socket.binaryType = 'arraybuffer';
    } catch (error) {
      cleanupSetup();
      var friendly = voiceSetupError(error);
      var blocked = error && (error.name === 'NotAllowedError' || error.name === 'SecurityError' || error.name === 'NotFoundError');
      throw new Error(blocked ? friendly : offerBrowserRetry(friendly));
    }

    var latestText = '';
    var transcriptSlices = {};
    var finished = false;
    var stopRequested = false;
    var providerReady = false;
    var workletFlushed = false;
    var endSent = false;
    var finishTimer = null;
    var connectTimer = null;

    function cleanup() {
      if (finishTimer) clearTimeout(finishTimer);
      if (connectTimer) clearTimeout(connectTimer);
      try { processor.port.onmessage = null; processor.disconnect(); } catch (_) {}
      try { sink.disconnect(); } catch (_) {}
      try { source.disconnect(); } catch (_) {}
      stream.getTracks().forEach(function (track) { track.stop(); });
      context.close().catch(function () {});
      socket.onopen = socket.onmessage = socket.onerror = socket.onclose = null;
      try { socket.close(); } catch (_) {}
      activeVoice = null;
    }

    function fail(message) {
      if (finished) return;
      finished = true;
      try { socket.close(); } catch (_) {}
      cleanup();
      callbacks.onError(offerBrowserRetry(message));
    }

    function finish() {
      if (finished) return;
      finished = true;
      cleanup();
      if (latestText.trim()) callbacks.onText(formatSpeechTranscript(latestText));
      else callbacks.onError(voiceCopy('没有听清，可以再说一次或改用文字。', 'I did not catch that. Try again, or type instead.'));
    }

    function sendAudio(buffer) {
      if (finished || endSent || !buffer) return;
      // The microphone processor is connected only after Tencent's code=0
      // handshake. Drop any impossible early frame instead of buffering and
      // bursting stale audio faster than real time after the handshake.
      if (!providerReady || socket.readyState !== WebSocket.OPEN) return;
      try { socket.send(buffer); }
      catch (_) { fail(voiceCopy('语音连接中断。', 'The voice connection was interrupted.')); }
    }

    function sendEndWhenReady() {
      if (!stopRequested || !workletFlushed || !providerReady || endSent || finished) return;
      if (socket.readyState !== WebSocket.OPEN) return;
      try {
        socket.send(JSON.stringify({ type: 'end' }));
        endSent = true;
      } catch (_) {
        fail(voiceCopy('语音连接中断。', 'The voice connection was interrupted.'));
      }
    }

    function stop() {
      if (finished || stopRequested) return;
      stopRequested = true;
      callbacks.onStatus(voiceCopy('正在整理你刚才说的…', 'Finishing what you just said…'));
      // Stop feeding new samples before flushing the resampler. Message order
      // on this port then guarantees that every audio frame precedes `end`.
      try { source.disconnect(processor); } catch (_) {}
      processor.port.postMessage({ type: 'flush' });
      finishTimer = setTimeout(finish, 8000);
    }

    activeVoice = { stop: stop };
    processor.port.onmessage = function (event) {
      var data = event.data || {};
      if (data.type === 'audio') sendAudio(data.buffer);
      if (data.type === 'flushed') {
        workletFlushed = true;
        sendEndWhenReady();
      }
    };
    socket.onopen = function () {
      callbacks.onStatus(voiceCopy('正在连接语音…', 'Connecting voice input…'));
    };
    socket.onmessage = function (event) {
      if (typeof event.data !== 'string') return;
      try {
        var message = JSON.parse(event.data);
        if (message.code !== undefined && message.code !== 0) return fail(voiceErrorMessage(message));
        if (!providerReady && Number(message.code) === 0) {
          providerReady = true;
          if (connectTimer) clearTimeout(connectTimer);
          if (!stopRequested) {
            source.connect(processor);
          }
          callbacks.onStatus(stopRequested
            ? voiceCopy('正在整理你刚才说的…', 'Finishing what you just said…')
            : voiceCopy('我在听，再按一次结束', 'Listening · tap again to stop'));
          sendEndWhenReady();
        }
        var result = message.result || {};
        var text = result.voice_text_str || message.text || '';
        if (text) {
          var index = Number(result.index);
          var partialParts = [];
          if (Number.isFinite(index)) {
            transcriptSlices[index] = { text: text, final: Number(result.slice_type) === 2 };
            partialParts = Object.keys(transcriptSlices).map(Number).sort(function (a, b) { return a - b; })
              .map(function (key) { return transcriptSlices[key]; });
            latestText = joinSpeechParts(partialParts);
          } else {
            latestText = normalizeSpeechText(text);
            partialParts = [{ text: latestText, final: Number(result.slice_type) === 2 }];
          }
          callbacks.onPartial(speechPreview(partialParts));
        }
        // slice_type=2 only stabilizes one sentence. The stream is complete
        // exclusively when Tencent returns final=1 after our end message.
        if (message.final === 1) finish();
      } catch (_) {}
    };
    socket.onerror = function () {
      fail(voiceCopy('语音连接失败。', 'The voice connection failed.'));
    };
    socket.onclose = function () {
      if (finished) return;
      if (stopRequested || latestText) finish();
      else fail(voiceCopy('语音连接中断。', 'The voice connection was interrupted.'));
    };
    connectTimer = setTimeout(function () {
      if (!providerReady) fail(voiceCopy('语音连接超时。', 'The voice connection timed out.'));
    }, 8000);

    if (stopDuringSetup) stop();

  }

  function toggleVoice(callbacks) {
    if (activeVoice) {
      activeVoice.stop();
      return Promise.resolve('stopping');
    }
    if (browserSpeechClass() && (preferBrowserVoice || preferredVoiceProvider === 'browser')) {
      // Do not put this behind an awaited request: Safari and some Chromium
      // builds require start() to remain in the microphone tap's call stack.
      return beginBrowserVoice(callbacks).then(function () { return 'recording'; });
    }
    if (tencentVoiceConfigured === false) {
      if (browserSpeechClass()) {
        return beginBrowserVoice(callbacks).then(function () { return 'recording'; });
      }
      return Promise.reject(new Error(voiceCopy(
        '这台设备暂时无法使用语音输入，请先直接打字。',
        'Voice input is unavailable on this device. Please type instead.'
      )));
    }
    // `null` only means the capability probe has not returned (or was blocked),
    // not that Tencent is unavailable. Trying the signed Tencent route first
    // keeps mainland users off browser speech services that may be unreachable.
    return beginTencentVoice(callbacks).then(function () { return 'recording'; });
  }

  function mapLaunchTarget(method, links, userAgent) {
    links = links || {};
    if (method !== 'amap') return { url: links[method] || '', fallback: '' };

    var fallback = links.amap || '';
    var ua = String(userAgent || (navigator && navigator.userAgent) || '');
    if (/iPad|iPhone|iPod/i.test(ua) && links.amap_ios) {
      return { url: links.amap_ios, fallback: fallback };
    }
    if (/Android/i.test(ua) && links.amap_android) {
      return { url: links.amap_android, fallback: fallback };
    }
    return { url: fallback, fallback: '' };
  }

  /* Open Amap from the original tap so Safari may hand the request to the
     installed app. In-app browsers can block custom schemes; if the document
     stays visible, continue to Amap's universal web route instead of leaving
     the user on a dead button. */
  function launchMap(method, links) {
    var target = mapLaunchTarget(method, links, navigator.userAgent || '');
    if (!target.url) return false;

    var timer = null;
    function cleanup() {
      if (timer !== null) clearTimeout(timer);
      timer = null;
      if (window.removeEventListener) window.removeEventListener('pagehide', cleanup);
      if (document.removeEventListener) document.removeEventListener('visibilitychange', onVisibility);
    }
    function onVisibility() {
      if (document.hidden) cleanup();
    }
    function openFallback() {
      cleanup();
      if (!document.hidden && target.fallback) location.href = target.fallback;
    }

    if (target.fallback) {
      timer = setTimeout(openFallback, 1500);
      if (window.addEventListener) window.addEventListener('pagehide', cleanup, { once: true });
      if (document.addEventListener) document.addEventListener('visibilitychange', onVisibility);
    }
    try {
      location.href = target.url;
    } catch (_) {
      openFallback();
    }
    return true;
  }

  /* 地图图片的地址。key 在服务端，这里只拼我们自己的路径。
     只传地点坐标——地点坐标是公开信息，用户自己的位置不往这儿送。 */
  function staticMapUrl(latitude, longitude, width, height) {
    if (typeof latitude !== 'number' || typeof longitude !== 'number') return null;
    // API_BASE 本身就以 /api/v1 结尾，这里再拼一次会变成 /api/v1/api/v1/…
    return API_BASE + '/map/static?lat=' + latitude.toFixed(6) +
           '&lng=' + longitude.toFixed(6) + '&w=' + (width || 640) + '&h=' + (height || 260);
  }

  window.CurrentAI = {
    api: api,
    staticMapUrl: staticMapUrl,
    sessionId: sessionId,
    track: track,
    interpretAndRecommend: interpretAndRecommend,
    recommendFor: recommendFor,
    reflectOn: reflectOn,
    deleteOutcome: deleteOutcome,
    hasLocation: function () { return Boolean(activeLocation); },
    getLocationMode: function () { return activeLocationMode; },
    getLocationCity: function () { return activeLocationCity; },
    useBeijingDemo: useBeijingDemo,
    requestLocation: requestLocation,
    watchPresence: watchPresence,
    demoPresence: demoPresence,
    stopPresence: stopPresence,
    toggleVoice: toggleVoice,
    mapLaunchTarget: mapLaunchTarget,
    launchMap: launchMap,
    deviceRole: deviceRole,
    setDeviceRole: setDeviceRole,
    relayState: loadRelay,
    relayPendingCode: relayPendingCode,
    createRelaySession: createRelaySession,
    joinRelaySession: joinRelaySession,
    leaveRelaySession: leaveRelaySession,
    publishRelay: publishRelay,
    relayShareUrl: relayShareUrl
  };
  if (loadRelay()) scheduleRelayPoll(0);
})();
