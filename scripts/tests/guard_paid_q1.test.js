/**
 * `scripts/guard_paid_q1.mjs` 的回归用例。
 *
 * ## WHY 有这份文件
 *
 * 这条守卫是**被预算守卫逼出来的**（AGENTS.md 纯文字规则 94 > 预算 88 被判红，
 * 提示「新加一条纯文字规则，就得先给它写守卫」），所以它肩负的正是
 * AGENTS.md 那条规则本该有、却没有的效力：让「付费卡违规占用 NOW 档位」
 * 这件事**在无人记得的情况下也能被发现**。
 *
 * 已在真实数据上命中一次：`#1288`（付费前端软拦截，挂 `M1 付费验证 #4`）带 `Q1-RED`。
 *
 * 测试重心：
 *   1. 判据只吃客观字段（里程碑/标签/编号），**不判断卡片重不重要**；
 *   2. 例外白名单必须生效且**可审计**（`#2324` 是 owner 明确批准的）；
 *   3. 当前**不阻断**（违规项既已存在且非 PR 作者可修，阻断会造出天天响的假信号）。
 *
 * ## 怎么跑
 *
 *     node --test "scripts/tests/guard_paid_q1.test.js"
 */

'use strict';

const assert = require('node:assert/strict');
const { test } = require('node:test');

const { checkCard, PAID_MILESTONES, ALLOWED_EXCEPTIONS, Q1, BLOCKING } = require('../guard_paid_q1.mjs');

const PAID = PAID_MILESTONES[0];

test('付费里程碑 + Q1-RED → 违规（真实案例 #1288 的判据）', () => {
  const v = checkCard({ milestone: PAID, hasQ1: true, number: 1288 });
  assert.equal(v.violation, true);
  assert.match(v.reason, /付费里程碑/);
});

test('付费里程碑但无 Q1 → 不违规（付费卡可以存在，只是不能占 NOW）', () => {
  assert.equal(checkCard({ milestone: PAID, hasQ1: false, number: 1288 }).violation, false);
});

test('非付费里程碑 + Q1 → 不违规', () => {
  assert.equal(checkCard({ milestone: 'M2 免费核心 Free Core', hasQ1: true, number: 2372 }).violation, false);
});

test('例外白名单生效（#2324 owner 已批准）', () => {
  const v = checkCard({ milestone: PAID, hasQ1: true, number: 2324 });
  assert.equal(v.violation, false);
  assert.match(v.reason, /例外白名单/);
});

test('白名单只对指定编号生效，不是「付费卡一律放行」', () => {
  assert.equal(checkCard({ milestone: PAID, hasQ1: true, number: 2325 }).violation, true);
});

test('无里程碑不算违规（判据不猜，只看明确归属）', () => {
  assert.equal(checkCard({ milestone: null, hasQ1: true, number: 999 }).violation, false);
});

test('常量：付费集合与例外清单，且例外必须是显式的少数', () => {
  assert.equal(Q1, 'Q1-RED');
  assert.ok(PAID_MILESTONES.length >= 1);
  assert.deepEqual(ALLOWED_EXCEPTIONS, [2324], '例外必须是显式清单，便于审计');
});

test('判据不接收「重要性」入参——不给主观判断留位置', () => {
  // checkCard 只吃 (milestone, hasQ1, number)。若哪天加了 priority/importance，
  // 守卫就开始替 owner 判断「这卡重不重要」，那正是本守卫要避免的。
  const src = require('node:fs').readFileSync('scripts/guard_paid_q1.mjs', 'utf8');
  const fn = src.slice(src.indexOf('export function checkCard'), src.indexOf('/** 取当前 open'));
  for (const bad of ['importance', 'priority', 'severity', '重要性']) {
    assert.ok(!fn.includes(bad), `判据内不应出现「${bad}」`);
  }
});

test('当前为报告模式而非阻断（违规项非 PR 作者可修，阻断会造假信号）', () => {
  assert.equal(BLOCKING, false);
  // 注释里必须写清何时转阻断，否则这个 false 会永远留着
  const src = require('node:fs').readFileSync('scripts/guard_paid_q1.mjs', 'utf8');
  assert.match(src, /裁定.*转阻断|转阻断/, '必须写明转阻断的条件');
});

test('证伪探针：把「无 Q1 也算违规」写错必须被抓出', () => {
  const real = checkCard({ milestone: PAID, hasQ1: false, number: 1288 });
  const broken = () => ({ violation: true });
  assert.equal(real.violation, false);
  assert.equal(broken().violation, true, '两者结论必须相反');
});

test('证伪探针：删掉例外白名单必须被抓出', () => {
  // 真实现：#2324 豁免。若白名单被清空，#2324 会被判违规。
  const withAllow = checkCard({ milestone: PAID, hasQ1: true, number: 2324 });
  assert.equal(withAllow.violation, false);
  assert.ok(ALLOWED_EXCEPTIONS.includes(2324), '白名单必须真的包含 #2324');
});
