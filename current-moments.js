/* Pure state for the local, explicitly labelled moments/community demo. */
(function (root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  else root.CurrentMoments = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  "use strict";
  const KEY = "current.moments.v1";
  const SCENARIO_KEY = "current.moments.scenario.v1";
  const MOODS = ["low", "quiet", "noisy", "spark", "tired", "empty", "tight", "heated", "near", "fresh", "bright", "okay"];
  const SEEDS = [
    ["bj-light", "北京", "liangmahe", "亮马河", "Liangma River", "light", "水面上，一小片粉色", "A pink reflection on the water", ["low", "tight", "bright"], 25],
    ["bj-leaf", "北京", "tiantan", "天坛公园", "Temple of Heaven", "leaf", "一片叶子，慢慢落下来", "A leaf taking its time", ["tired", "quiet", "noisy"], 40],
    ["bj-sky", "北京", "shichahai", "什刹海", "Shichahai", "cloud", "有人也正在抬头看云", "Someone else looking up", ["near", "empty", "okay"], 30],
    ["bj-dew", "北京", "beihai", "北海公园", "Beihai Park", "dew", "叶尖上，还留着一滴露珠", "A drop still on the leaf", ["low", "quiet", "fresh"], 20],
    ["sz-sunset", "深圳", null, "深圳湾公园", "Shenzhen Bay Park", "light", "海边，天色慢慢变粉", "The sky turning pink by the bay", ["bright", "low", "tight"], 25],
    ["sz-leaf", "深圳", null, "莲花山公园", "Lianhuashan Park", "leaf", "树影在长椅旁晃了晃", "A shadow beside a bench", ["tired", "quiet", "heated"], 45],
    ["sz-sky", "深圳", null, "中心公园", "Central Park", "cloud", "另一双眼睛看见的天空", "The sky through another pair of eyes", ["near", "empty", "fresh"], 30],
    ["sz-book", "深圳", null, "深圳湾公园白鹭坡书吧", "Bailupo Book Bar", "light", "书页上停了一束光", "A little light on a page", ["spark", "noisy", "okay"], 35]
  ];
  function demoMoments(start) {
    return SEEDS.map(([id, city, placeId, place, placeEn, kind, title, titleEn, moods, minutes]) => ({
      id, city, placeId, place, placeEn, kind, title, titleEn, moods,
      startsAt: start, expiresAt: start + minutes * 60000,
      source: "demo_seed", isDemo: true, distanceM: null
    }));
  }
  function active(moment, now) {
    return Number.isFinite(moment.startsAt) && Number.isFinite(moment.expiresAt) &&
      moment.startsAt <= now && now < moment.expiresAt;
  }
  function select(moments, {city, mood, now}) {
    return moments.filter(m => m.city === city && active(m, now))
      .sort((a, b) => Number(b.moods.includes(mood)) - Number(a.moods.includes(mood)) || a.expiresAt - b.expiresAt);
  }
  function cloudTone(mood, report = {}) {
    if (report.valence === "pleasant") return "rainbow";
    if (report.valence === "unpleasant") return "heavy";
    if (["neutral", "mixed"].includes(report.valence)) return "calm";
    if (mood === "bright") return "rainbow";
    if (["low", "tired", "tight", "heated"].includes(mood)) return "heavy";
    return "calm";
  }
  function canReveal(match, now) {
    return Boolean(match && match.isDemo && match.intent === "meet" &&
      match.mine === true && match.theirs === true && !match.blocked &&
      Number.isFinite(match.expiresAt) && now < match.expiresAt);
  }
  function empty() { return {contributions: [], cards: [], match: null}; }
  function read(storage) {
    try {
      const data = JSON.parse(storage.getItem(KEY));
      if (!data || !Array.isArray(data.contributions) || !Array.isArray(data.cards)) return empty();
      return {contributions: data.contributions.slice(-100), cards: data.cards.slice(-100), match: null};
    } catch (_) { return empty(); }
  }
  function write(storage, data) {
    // Consent belongs to this session, never persisted as a future permission.
    try {
      storage.setItem(KEY, JSON.stringify({contributions: data.contributions.slice(-100), cards: data.cards.slice(-100)}));
      return true;
    } catch (_) { return false; }
  }
  function scenario(storage, now) {
    try {
      const saved = Number(storage.getItem(SCENARIO_KEY));
      if (Number.isFinite(saved) && saved > 0 && saved <= now) return saved;
      storage.setItem(SCENARIO_KEY, String(now));
    } catch (_) {}
    return now;
  }
  function contribution(input, now, id) {
    const place = String(input.place || "").trim().slice(0, 80);
    const reason = String(input.reason || "").trim().slice(0, 160);
    const mood = MOODS.includes(input.mood) ? input.mood : null;
    const visibility = input.visibility === "named" ? "named" : "anonymous";
    const nickname = visibility === "named" ? String(input.nickname || "").trim().slice(0, 24) : "";
    if (!place || !reason || !mood || (visibility === "named" && !nickname)) return null;
    const kind = input.kind === "moment" ? "moment" : "place";
    return {id, place, reason, mood, visibility, nickname, kind, city: input.city === "深圳" ? "深圳" : "北京",
      createdAt: now, expiresAt: kind === "moment" ? now + 60 * 60000 : null,
      source: "local_draft", published: false, visits: 0};
  }
  function collect(moment, now, mood, outcome) {
    if (!moment || !["caught", "missed"].includes(outcome)) return null;
    return {id: moment.id, title: moment.title, titleEn: moment.titleEn, place: moment.place,
      placeEn: moment.placeEn, city: moment.city, kind: moment.kind, isDemo: Boolean(moment.isDemo),
      source: moment.source, startsAt: moment.startsAt, expiresAt: moment.expiresAt,
      savedAt: now, mood, outcome, presence: "self_reported"};
  }
  return {KEY, SCENARIO_KEY, MOODS, demoMoments, active, select, cloudTone, canReveal, read, write, scenario, contribution, collect};
});
