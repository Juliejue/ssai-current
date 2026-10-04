/* One cloud voice on all devices. No silent fallback to system speech. */
(function () {
  var player = null, controller = null, objectUrl = null, generation = 0;
  var blobs = new Map();
  function stop() {
    generation++;
    if (controller) controller.abort();
    controller = null;
    if (player) { player.pause(); player.src = ''; }
    player = null;
    if (objectUrl) URL.revokeObjectURL(objectUrl);
    objectUrl = null;
  }
  async function speak(text, language, onState) {
    stop();
    var token = generation;
    var chunks = String(text || '').trim().match(/[\s\S]{1,150}/g) || [];
    if (!chunks.length) return;
    // Construct the player inside the tap; subsequent cached playback also
    // supports browsers that require a fresh gesture after audio is fetched.
    player = new Audio();
    var activePlayer = player;
    controller = new AbortController();
    var activeController = controller;
    onState('loading');
    try {
      for (var chunk of chunks) {
        var key = language + ':' + chunk;
        var blob = blobs.get(key);
        if (!blob) {
          var timer = setTimeout(function () { activeController.abort(); }, 22000);
          try {
            var response = await fetch('/api/v1/speech', {
              method: 'POST', headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ text: chunk, lang: language || 'zh' }), signal: activeController.signal
            });
            if (!response.ok) {
              var failure = await response.json().catch(function () { return {}; });
              throw new Error(failure.detail || '自然声音暂不可用，请先使用文字。');
            }
            blob = await response.blob();
          } finally { clearTimeout(timer); }
          if (blobs.size >= 8) blobs.delete(blobs.keys().next().value);
          blobs.set(key, blob);
        }
        if (token !== generation) return;
        objectUrl = URL.createObjectURL(blob);
        activePlayer.src = objectUrl;
        await new Promise(function (resolve, reject) {
          activePlayer.onended = resolve;
          activePlayer.onerror = function () { reject(new Error('音频播放失败，请再试一次。')); };
          activeController.signal.addEventListener('abort', function () { resolve(); }, { once: true });
          activePlayer.play().then(function () { onState('speaking'); }).catch(function () {
            reject(new Error('声音已准备好，请再点一次播放。'));
          });
        });
        if (token !== generation) return;
        URL.revokeObjectURL(objectUrl); objectUrl = null;
      }
      if (token === generation) { stop(); onState('idle'); }
    } catch (error) {
      if (token !== generation) return;
      stop();
      onState('error', error.name === 'AbortError' ? '自然声音等待超时，请再试一次。' : error.message);
    }
  }
  window.XiaozaiVoice = { speak: speak, stop: stop };
  window.addEventListener('pagehide', stop);
})();
