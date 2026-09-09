/* 主动触达与守护层的策略（§6.3 路径 A / FR-31 / FR-14 / 守则 11、12）。

   这里只有纯函数：给定「现在几点」和「过去发生过什么」，回答两个问题——
   现在能不能打扰、以及该说哪一种话。抽出来是为了能被测试，
   因为「不打扰」如果只写在文案里、没写在代码里，它就不存在。

   浏览器和 Node 都要用，所以不依赖任何 DOM。 */
(function (root, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  else root.ReachPolicy = api;
})(typeof self !== 'undefined' ? self : this, function () {
  'use strict';

  var DEFAULTS = {
    enabled: true,
    dailyCap: 2,              // 守则 11：主动触达有日上限
    silentFrom: 22,           // 静默时段 22:00–08:00
    silentTo: 8,
    minGapMinutes: 90         // 两次触达之间至少隔这么久
  };

  // 连续被拒之后的降频（守则 11「连续拒绝自动降频」+ FR-14）。
  // 拒得越多，间隔越长；到第四次直接停掉，并且要明说停了。
  var BACKOFF_DAYS = [0, 1, 3, 7];

  function startOfDay(now) {
    var d = new Date(now);
    d.setHours(0, 0, 0, 0);
    return d.getTime();
  }

  function inSilentHours(now, settings) {
    var hour = new Date(now).getHours();
    var from = settings.silentFrom, to = settings.silentTo;
    return from > to ? (hour >= from || hour < to) : (hour >= from && hour < to);
  }

  /* history: {todayCount, todayKey, lastPromptAt, declineStreak, mutedUntil,
               lastOutcomeAt, offersWithoutDeparture} */
  function canReach(now, history, settings) {
    settings = Object.assign({}, DEFAULTS, settings || {});
    history = history || {};

    if (!settings.enabled) return { ok: false, reason: 'disabled' };
    if (history.mutedUntil && now < history.mutedUntil) return { ok: false, reason: 'muted' };
    if (inSilentHours(now, settings)) return { ok: false, reason: 'silent_hours' };

    var sameDay = history.todayKey === startOfDay(now);
    var count = sameDay ? (history.todayCount || 0) : 0;
    if (count >= settings.dailyCap) return { ok: false, reason: 'daily_cap' };

    if (history.lastPromptAt && now - history.lastPromptAt < settings.minGapMinutes * 60000) {
      return { ok: false, reason: 'too_soon' };
    }
    return { ok: true, reason: 'ok' };
  }

  /* 被拒之后往后推多久。第四次起彻底停掉，不再自己回来。 */
  function backoffAfterDecline(now, declineStreak) {
    var index = Math.min(declineStreak, BACKOFF_DAYS.length - 1);
    var days = BACKOFF_DAYS[index];
    return {
      mutedUntil: days ? now + days * 86400000 : startOfDay(now) + 86400000,
      stopped: declineStreak >= BACKOFF_DAYS.length,
      days: days
    };
  }

  /* FR-31 延迟复看：选了「现在不方便」之后，挑一个合适的时机回来一次。
     只回来一次；再拒当晚就不再打扰。 */
  function scheduleRecheck(now, preferredHour) {
    var target = new Date(now);
    var hour = typeof preferredHour === 'number' ? preferredHour : 18;
    target.setHours(hour, 30, 0, 0);
    if (target.getTime() - now < 45 * 60000) target.setTime(now + 90 * 60000);
    // 推到静默时段就作罢——宁可不回来，也不半夜敲人
    if (target.getHours() >= DEFAULTS.silentFrom) return null;
    return target.getTime();
  }

  /* FR-14 防「越来越不出门」：收到推荐却一次都没出发，累计到阈值就换一种说法，
     不再推地方，而是问要不要先别提这件事。 */
  function guardianState(history) {
    history = history || {};
    var stalled = history.offersWithoutDeparture || 0;
    if (stalled >= 3) return 'withdrawn';
    // 守则 12 防依赖：一天里反复回来，提醒一句真实社交/专业帮助
    if ((history.sessionsToday || 0) >= 5) return 'leaning';
    return 'ok';
  }

  return {
    DEFAULTS: DEFAULTS,
    BACKOFF_DAYS: BACKOFF_DAYS,
    startOfDay: startOfDay,
    inSilentHours: inSilentHours,
    canReach: canReach,
    backoffAfterDecline: backoffAfterDecline,
    scheduleRecheck: scheduleRecheck,
    guardianState: guardianState
  };
});
