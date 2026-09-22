/* Pure state for the local, explicitly labelled moments/community demo. */
(function (root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  else root.CurrentMoments = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  "use strict";
  const KEY = "current.moments.v1";
  const SCENARIO_KEY = "current.moments.scenario.v1";
  const CITIES = ["北京", "上海", "广州", "深圳"];
  const KINDS = ["lasting_place", "timed_beauty", "seasonal", "sensory", "quiet_corner"];
  const MOODS = ["low", "quiet", "noisy", "spark", "tired", "empty", "tight", "heated", "near", "fresh", "bright", "okay"];
  const STOCK = {
    sunset: "/assets/moments/sunset.jpg",
    leaf: "/assets/moments/leaf.jpg",
    cloud: "/assets/moments/cloud.jpg",
    dew: "/assets/moments/dew.jpg",
    book: "/assets/moments/book.jpg"
  };
  const SEEDS = [
    ["bj-light", "北京", "liangmahe", "亮马河", "Liangma River", "light", "水面上，一小片粉色", "A pink reflection on the water", ["low", "tight", "bright"], 25, STOCK.sunset],
    ["bj-leaf", "北京", "tiantan", "天坛公园", "Temple of Heaven", "leaf", "一片叶子，慢慢落下来", "A leaf taking its time", ["tired", "quiet", "noisy"], 40, STOCK.leaf],
    ["bj-sky", "北京", "shichahai", "什刹海", "Shichahai", "cloud", "有人也正在抬头看云", "Someone else looking up", ["near", "empty", "okay"], 30, STOCK.cloud],
    ["bj-dew", "北京", "beihai", "北海公园", "Beihai Park", "dew", "叶尖上，还留着一滴露珠", "A drop still on the leaf", ["low", "quiet", "fresh"], 20, STOCK.dew],
    ["sh-sunset", "上海", null, "徐汇滨江", "West Bund", "light", "江面正把晚霞揉开", "Sunset spreading over the river", ["bright", "low", "tight"], 25, STOCK.sunset],
    ["sh-leaf", "上海", null, "世纪公园", "Century Park", "leaf", "风把树影推过草地", "Tree shadows crossing the grass", ["tired", "quiet", "heated"], 45, STOCK.leaf],
    ["sh-sky", "上海", null, "外滩源", "Rockbund", "cloud", "两栋旧楼之间露出一片云", "A cloud between old buildings", ["near", "empty", "fresh"], 30, STOCK.cloud],
    ["sh-book", "上海", null, "思南书局", "Sinan Books", "light", "窗边的一页被照亮了", "A page lit by the window", ["spark", "noisy", "okay"], 35, STOCK.book],
    ["gz-sunset", "广州", null, "二沙岛", "Ersha Island", "light", "江边的天正变成橙粉色", "The riverside sky turning coral", ["bright", "low", "tight"], 25, STOCK.sunset],
    ["gz-leaf", "广州", null, "海珠湿地", "Haizhu Wetland", "leaf", "一片新叶在水边晃", "A new leaf moving by the water", ["tired", "quiet", "heated"], 45, STOCK.leaf],
    ["gz-sky", "广州", null, "沙面", "Shamian", "cloud", "骑楼上方有一朵慢云", "A slow cloud above the arcades", ["near", "empty", "fresh"], 30, STOCK.cloud],
    ["gz-dew", "广州", null, "云溪植物园", "Yunxi Botanical Garden", "dew", "叶尖的水珠还没落下", "A drop still holding on", ["low", "quiet", "fresh"], 20, STOCK.dew],
    ["sz-sunset", "深圳", null, "深圳湾公园", "Shenzhen Bay Park", "light", "海边，天色慢慢变粉", "The sky turning pink by the bay", ["bright", "low", "tight"], 25, STOCK.sunset],
    ["sz-leaf", "深圳", null, "莲花山公园", "Lianhuashan Park", "leaf", "树影在长椅旁晃了晃", "A shadow beside a bench", ["tired", "quiet", "heated"], 45, STOCK.leaf],
    ["sz-sky", "深圳", null, "中心公园", "Central Park", "cloud", "另一双眼睛看见的天空", "The sky through another pair of eyes", ["near", "empty", "fresh"], 30, STOCK.cloud],
    ["sz-book", "深圳", null, "深圳湾公园白鹭坡书吧", "Bailupo Book Bar", "light", "书页上停了一束光", "A little light on a page", ["spark", "noisy", "okay"], 35, STOCK.book]
  ];
  function demoMoments(start) {
    return SEEDS.map(([id, city, placeId, place, placeEn, kind, title, titleEn, moods, minutes, image]) => ({
      id, city, placeId, place, placeEn, kind, title, titleEn, moods,
      startsAt: start, expiresAt: start + minutes * 60000,
      source: "demo_seed", isDemo: true, distanceM: null, image,
      imageLicense: "Unsplash License", imageLicenseUrl: "https://unsplash.com/license"
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
  function empty() { return {contributions: [], cards: []}; }
  function read(storage) {
    try {
      const data = JSON.parse(storage.getItem(KEY));
      if (!data || !Array.isArray(data.contributions) || !Array.isArray(data.cards)) return empty();
      return {contributions: data.contributions.slice(-100), cards: data.cards.slice(-100)};
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
    const visibility = "anonymous";
    if (!place || !reason || !mood) return null;
    const kind = KINDS.includes(input.kind) ? input.kind : "lasting_place";
    const expiry = {timed_beauty: 60, sensory: 180, seasonal: 10080}[kind] || null;
    // Nearby search is no longer limited to four pilots. Keep the four seeded
    // demo cities, but let an explicitly selected real city travel with a draft.
    const requestedCity = String(input.city || "").trim().slice(0, 40);
    const city = requestedCity || "北京";
    const media = Array.isArray(input.media) ? input.media.slice(0, 4) : [];
    return {id, place, reason, mood, visibility, kind, city,
      createdAt: now, expiresAt: expiry ? now + expiry * 60000 : null, media,
      source: "local_draft", published: false, visits: 0};
  }
  function collect(moment, now, mood, outcome) {
    if (!moment || !["caught", "missed"].includes(outcome)) return null;
    return {id: moment.id, title: moment.title, titleEn: moment.titleEn, place: moment.place,
      placeEn: moment.placeEn, city: moment.city, kind: moment.kind, isDemo: Boolean(moment.isDemo),
      source: moment.source, startsAt: moment.startsAt, expiresAt: moment.expiresAt,
      savedAt: now, mood, outcome, presence: "self_reported"};
  }
  function mediaStore() {
    return new Promise((resolve, reject) => {
      if (typeof indexedDB === "undefined") return reject(new Error("media storage unavailable"));
      const request = indexedDB.open("current-media-v1", 1);
      request.onupgradeneeded = () => request.result.createObjectStore("assets");
      request.onsuccess = () => resolve(request.result);
      request.onerror = () => reject(request.error);
    });
  }
  async function saveMedia(id, file) {
    const db = await mediaStore();
    await new Promise((resolve, reject) => {
      const request = db.transaction("assets", "readwrite").objectStore("assets").put(file, id);
      request.onsuccess = resolve;
      request.onerror = () => reject(request.error);
    });
    db.close();
    return {id, name:file.name, type:file.type, size:file.size};
  }
  async function mediaURL(id) {
    const db = await mediaStore();
    const blob = await new Promise((resolve, reject) => {
      const request = db.transaction("assets").objectStore("assets").get(id);
      request.onsuccess = () => resolve(request.result);
      request.onerror = () => reject(request.error);
    });
    db.close();
    return blob ? URL.createObjectURL(blob) : null;
  }
  return {KEY, SCENARIO_KEY, MOODS, CITIES, KINDS, demoMoments, active, select, cloudTone,
    read, write, scenario, contribution, collect, saveMedia, mediaURL};
});
