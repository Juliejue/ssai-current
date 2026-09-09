/* 守则 11「防打扰」和 FR-14「连续被拒降打扰」的回归测试。
   这两条如果只写在文案里、没写在代码里，它就不存在。 */
const test = require('node:test');
const assert = require('node:assert');
const P = require('../reach-policy.js');

const at = (h, m = 0) => new Date(2026, 8, 10, h, m).getTime();
const day = P.startOfDay(at(12));

test('静默时段不打扰（跨午夜也算）', () => {
  assert.equal(P.inSilentHours(at(23), P.DEFAULTS), true);
  assert.equal(P.inSilentHours(at(3), P.DEFAULTS), true);
  assert.equal(P.inSilentHours(at(7, 59), P.DEFAULTS), true);
  assert.equal(P.inSilentHours(at(8), P.DEFAULTS), false);
  assert.equal(P.inSilentHours(at(16), P.DEFAULTS), false);
});

test('日上限用完就不再来', () => {
  const history = { todayKey: day, todayCount: 2 };
  assert.equal(P.canReach(at(16), history, {}).reason, 'daily_cap');
  assert.equal(P.canReach(at(16), { todayKey: day, todayCount: 1 }, {}).ok, true);
});

test('跨天之后额度会重置', () => {
  const yesterday = P.startOfDay(at(12)) - 86400000;
  assert.equal(P.canReach(at(16), { todayKey: yesterday, todayCount: 9 }, {}).ok, true);
});

test('两次触达之间要留间隔', () => {
  const history = { todayKey: day, todayCount: 1, lastPromptAt: at(15, 30) };
  assert.equal(P.canReach(at(16), history, {}).reason, 'too_soon');
  assert.equal(P.canReach(at(17, 5), history, {}).ok, true);
});

test('用户关掉之后就是关掉，不留后门', () => {
  assert.equal(P.canReach(at(16), {}, { enabled: false }).reason, 'disabled');
});

test('静音期内不打扰，到期自动恢复', () => {
  const muted = { mutedUntil: at(20) };
  assert.equal(P.canReach(at(16), muted, {}).reason, 'muted');
  assert.equal(P.canReach(at(20, 1), muted, {}).ok, true);
});

test('连续被拒，间隔越来越长，第四次彻底停掉', () => {
  const now = at(16);
  const first = P.backoffAfterDecline(now, 1);
  const second = P.backoffAfterDecline(now, 2);
  const third = P.backoffAfterDecline(now, 3);
  assert.ok(second.mutedUntil > first.mutedUntil, '第二次要比第一次久');
  assert.ok(third.mutedUntil > second.mutedUntil, '第三次要比第二次久');
  assert.equal(first.stopped, false);
  assert.equal(P.backoffAfterDecline(now, 4).stopped, true, '第四次起不再自己回来');
});

test('第一次被拒当天不再打扰', () => {
  const now = at(16);
  const back = P.backoffAfterDecline(now, 1);
  assert.equal(P.canReach(at(19), { mutedUntil: back.mutedUntil }, {}).reason, 'muted');
});

test('FR-31 延迟复看安排在下班时间，且不会太急', () => {
  const target = P.scheduleRecheck(at(14), 18);
  assert.ok(target, '下午选「现在不方便」应当安排一次复看');
  assert.equal(new Date(target).getHours(), 18);
  assert.equal(new Date(target).getMinutes(), 30);
});

test('复看时间太近就往后挪，不能刚说完就回来', () => {
  const target = P.scheduleRecheck(at(18, 10), 18);
  assert.ok(target - at(18, 10) >= 45 * 60000, '至少要隔 45 分钟');
});

test('复看会落进静默时段就干脆不回来', () => {
  assert.equal(P.scheduleRecheck(at(21, 40), 18), null, '宁可不回来，也不半夜敲人');
});

test('FR-14 连续三次给了推荐都没出发，就换一种说法', () => {
  assert.equal(P.guardianState({ offersWithoutDeparture: 2 }), 'ok');
  assert.equal(P.guardianState({ offersWithoutDeparture: 3 }), 'withdrawn');
});

test('守则 12 一天里反复回来，提醒一句', () => {
  assert.equal(P.guardianState({ sessionsToday: 4 }), 'ok');
  assert.equal(P.guardianState({ sessionsToday: 5 }), 'leaning');
});
