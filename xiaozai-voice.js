/* Device speech for the demo; no cloud synthesis calls. */
(function () {
  var generation = 0;
  function stop() { generation++; if (window.speechSynthesis) window.speechSynthesis.cancel(); }
  function speak(text, language, onState) {
    stop(); onState = onState || function () {};
    if (!window.speechSynthesis) { onState('error', '此设备暂不支持朗读。'); return; }
    var token = generation, utterance = new SpeechSynthesisUtterance(String(text || ''));
    utterance.lang = language === 'en' ? 'en-US' : 'zh-CN';
    utterance.rate = 0.9;
    var voices = speechSynthesis.getVoices();
    var voice = voices.find(function (v) { return v.lang === utterance.lang; });
    if (voice) utterance.voice = voice;
    utterance.onstart = function () { if (token === generation) onState('speaking'); };
    utterance.onend = function () { if (token === generation) onState('idle'); };
    utterance.onerror = function (event) { if (token === generation && event.error !== 'canceled' && event.error !== 'interrupted') onState('error', '请点播放再试一次。'); };
    speechSynthesis.speak(utterance);
  }
  window.XiaozaiVoice = {speak:speak, stop:stop};
  window.addEventListener('pagehide', stop);
})();
