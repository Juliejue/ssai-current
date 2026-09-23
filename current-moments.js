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
    book: "/assets/moments/book.jpg",
    cafe: "/assets/moments/cafe.jpg",
    food: "/assets/moments/food.jpg",
    bar: "/assets/moments/bar.jpg",
    city: "/assets/moments/city.jpg"
  };
  const SEEDS = [
    ["bj-cafe", "北京", "soloist", "soloist coffee", "soloist coffee", "quiet_corner", "玻璃房里有一张空桌", "An empty table in the glass room", ["low", "quiet", "tired"], 180, STOCK.cafe],
    ["bj-book", "北京", "sanlian", "三联韬奋书店", "Sanlian Bookstore", "quiet_corner", "整面书架可以慢慢看", "A whole wall of books to browse", ["spark", "noisy", "okay"], 180, STOCK.book],
    ["bj-sky", "北京", "shichahai", "什刹海", "Shichahai", "timed_beauty", "厚云把天空压低了", "Heavy clouds lowered the sky", ["near", "empty", "fresh"], 180, STOCK.cloud],
    ["bj-sunset", "北京", "liangmahe", "亮马河", "Liangma River", "timed_beauty", "橙色太阳正贴近水面", "The orange sun is nearing the water", ["bright", "low", "tight"], 180, STOCK.sunset],
    ["sh-sunset", "上海", null, "徐汇滨江", "West Bund", "timed_beauty", "橙色夕阳落在静水上", "Orange sunset over still water", ["bright", "low", "tight"], 180, STOCK.sunset],
    ["sh-city", "上海", null, "北外滩", "North Bund", "timed_beauty", "高楼被晚光染成粉金色", "Towers turning rose-gold", ["spark", "near", "fresh"], 180, STOCK.city],
    ["sh-food", "上海", null, "巨鹿路", "Julu Road", "sensory", "一盘刚端上桌的热食", "A warm plate just arrived", ["empty", "tired", "okay"], 180, STOCK.food],
    ["sh-book", "上海", null, "思南书局", "Sinan Books", "quiet_corner", "旅行书排满了一整面墙", "Travel books fill the wall", ["spark", "noisy", "quiet"], 180, STOCK.book],
    ["gz-food", "广州", null, "东山口", "Dongshankou", "sensory", "晚餐刚刚端到桌上", "Dinner just reached the table", ["empty", "tired", "okay"], 180, STOCK.food],
    ["gz-cafe", "广州", null, "沙面", "Shamian", "quiet_corner", "绿植边的咖啡桌空着", "A café table beside the plants", ["low", "quiet", "tired"], 180, STOCK.cafe],
    ["gz-bar", "广州", null, "海心沙", "Haixinsha", "timed_beauty", "蓝绿色舞台灯刚亮起来", "Blue-green stage lights just came on", ["bright", "near", "spark"], 180, STOCK.bar],
    ["gz-lake", "广州", null, "海珠湖", "Haizhu Lake", "lasting_place", "碧绿湖面一直延伸到山脚", "Turquoise water reaches the mountains", ["quiet", "fresh", "tight"], 180, STOCK.leaf],
    ["sz-sunset", "深圳", null, "深圳湾公园", "Shenzhen Bay Park", "timed_beauty", "橙色夕阳正落向水面", "Orange sunset descending toward the water", ["bright", "low", "tight"], 180, STOCK.sunset],
    ["sz-cloud", "深圳", null, "中心公园", "Central Park", "timed_beauty", "厚云之间透出一小片亮处", "A bright patch between heavy clouds", ["near", "empty", "fresh"], 180, STOCK.cloud],
    ["sz-book", "深圳", null, "深圳湾公园白鹭坡书吧", "Bailupo Book Bar", "quiet_corner", "书架上全是旅行与城市", "Shelves full of travel and cities", ["spark", "noisy", "okay"], 180, STOCK.book],
    ["sz-work", "深圳", null, "南头古城", "Nantou Ancient Town", "quiet_corner", "窗边有人安静地打开电脑", "Someone working quietly by the window", ["tired", "quiet", "heated"], 180, STOCK.dew]
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
