/**
 * `scripts/guard_now_capacity.mjs` 的回归用例。
 *
 * ## WHY 有这份文件
 *
 * 本守卫是 NOW 档位的容量记账器。**它最重要的性质是「不阻塞登记」**——
 * 上一版把容量做成 PR 拦截，被证伪了（拦不到「提新卡」这个真正的目标场景，
 * 却给 owner 制造了「这里有闸门」的错觉）。所以测试重心不在「算得对不对」，
 * 而在**守住它不去变成拦截器**。
 *
 * 特别要防的三种退化：
 *   1. 超限时 `exit 1` 阻断 → 惩罚发现紧急问题的人，owner 会去加豁免；
 *   2. 加一个「豁免名单」入参 → 闸门一开就等于没有；
 *   3. 撤回标签需要人工触发 → 维护债累积，最后没人看标签。
 *
 * ## 反向验证（证伪探针）
 *
 * 见文件末尾。仓里惯例：注回旧行为必须被用例抓住，否则用例只是「恰好绿」。
 *
 * ## 怎么跑
 *
 *     node --test "scripts/tests/guard_now_capacity.test.js"
 *
 * 依赖：零新依赖（Node 内置 node:test / node:assert），纯离线（不调 API）。
 */

'use strict';

const assert = require('node:assert/strict');
const { test } = require('node:test');
const { readFileSync } = require('node:fs');

const { evaluateCapacity, planOverflowLabels, DEFAULT_LIMIT, OVERFLOW_LABEL, Q1_LABEL } = require('../guard_now_capacity.mjs');

test('默认上限 5，与 AGENTS.md 的 Q1 漂移阈值一致', () => {
  assert.equal(DEFAULT_LIMIT, 5);
});

test('超容报错必须明说「不阻塞登记」，且给出登记指引', () => {
  const v = evaluateCapacity(9);
  assert.equal(v.ok, false);
  // 这是本轮改版的全部要点：措辞不能暗示「先还债才能提卡」
  assert.match(v.message, /不阻塞登记/);
  assert.match(v.message, /直接提卡/);
  assert.match(v.message, new RegExp(OVERFLOW_LABEL));
});

test('未超容 → 通过', () => {
  for (const n of [0, 1, 3, 4, 5]) assert.equal(evaluateCapacity(n).ok, true, `${n} 应通过`);
});

test('等值放行（`>` 而非 `>=`）——等值红灯会天天响，等于没响', () => {
  assert.equal(evaluateCapacity(DEFAULT_LIMIT).ok, true);
  assert.equal(evaluateCapacity(DEFAULT_LIMIT + 1).ok, false);
});

test('取数失败（NaN / 负数）→ 判红但不谎报「超容」', () => {
  for (const bad of [NaN, -1, undefined]) {
    const v = evaluateCapacity(bad);
    assert.equal(v.ok, false);
    assert.match(v.message, /取数失败/);
    assert.doesNotMatch(v.message, /已超容量/);
  }
});

test('超容时给所有无标记的 Q1 卡加超额标签', () => {
  const plan = planOverflowLabels({ count: 7, limit: 5 }, [
    { number: 1, hasOverflow: false },
    { number: 2, hasOverflow: false },
  ]);
  assert.equal(plan.overCapacity, true);
  assert.deepEqual(plan.toLabel, [1, 2]);
  assert.deepEqual(plan.toUnlabel, []);
});

test('超容时不重复加已带标记的卡（幂等，否则每次扫描都刷一遍 API）', () => {
  const plan = planOverflowLabels({ count: 7, limit: 5 }, [
    { number: 1, hasOverflow: true },
    { number: 2, hasOverflow: false },
  ]);
  assert.deepEqual(plan.toLabel, [2]);
});

test('容量回落到上限内 → 自动撤掉超额标签（自动结清，不留维护债）', () => {
  const plan = planOverflowLabels({ count: 4, limit: 5 }, [
    { number: 1, hasOverflow: true },
    { number: 2, hasOverflow: true },
    { number: 3, hasOverflow: false },
  ]);
  assert.equal(plan.overCapacity, false);
  assert.deepEqual(plan.toUnlabel, [1, 2]);
  assert.deepEqual(plan.toLabel, []);
});

test('恰好等于上限 → 不算超容，撤标记', () => {
  const plan = planOverflowLabels({ count: 5, limit: 5 }, [{ number: 1, hasOverflow: true }]);
  assert.equal(plan.overCapacity, false);
  assert.deepEqual(plan.toUnlabel, [1]);
});

test('空卡列表不炸', () => {
  assert.deepEqual(planOverflowLabels({ count: 0, limit: 5 }, []), {
    overCapacity: false,
    toLabel: [],
    toUnlabel: [],
  });
});

test('标签常量拼写正确（写错就静默失效——标签名错了只会永远 toLabel 同一批）', () => {
  assert.equal(OVERFLOW_LABEL, 'NOW-超额');
  assert.equal(Q1_LABEL, 'Q1-RED');
});

test('CLI 源码里不得对超容 exit 1（守住「不阻塞」这条设计承诺）', () => {
  const src = readFileSync('scripts/guard_now_capacity.mjs', 'utf8');
  const cli = src.slice(src.indexOf('async function main'));
  const code = cli
    .split(/\r?\n/)
    .map((l) => l.replace(/\/\/.*$/, ''))
    .join('\n');
  // 只允许两处 process.exit：取数失败（1）与正常收尾（0）。
  // **不允许第三处**——那几乎必然是「超容就退」被加了回来。
  const exits = [...code.matchAll(/process\.exit\(([^)]*)\)/g)].map((m) => m[1].trim());
  assert.ok(exits.length <= 2, `超容不得阻断；CLI 段出现 ${exits.length} 处 process.exit（应≤2）`);
  assert.ok(
    exits.every((e) => e === '0' || e === '1'),
    `process.exit 参数只能是 0/1，实际 ${exits.join(',')}`,
  );
  assert.ok(exits.includes('0'), '正常收尾必须 exit 0（超容不是错误状态）');
  // 且 CLI 段里不得引用 ok 决定退出码（超容时 ok=false，若用它 exit 1 就变回拦截器了）
  assert.doesNotMatch(code, /verdict\.ok\s*\?\s*0\s*:\s*1/, '退出码不得由 evaluateCapacity.ok 决定');
});

test('判据不含豁免入参——不给「白名单」留后门', () => {
  assert.ok(evaluateCapacity.length <= 2, `入参不该超过 (count, limit)，实际 ${evaluateCapacity.length}`);
  const src = readFileSync('scripts/guard_now_capacity.mjs', 'utf8');
  const fn = src.slice(src.indexOf('export function evaluateCapacity'), src.indexOf('/**\n * 纯判据：给定容量结论'));
  for (const bad of ['exempt', 'allowlist', 'whitelist', '豁免名单']) {
    assert.ok(!fn.includes(bad), `判据内不应出现「${bad}」`);
  }
});

test('证伪探针：把「不阻塞」改回「超容即 exit 1」必须被抓出', () => {
  // 真实现：超容时 plan 照样算完、标签照样加，退出码仍是 0。
  // 若有人「顺手」改成 exit 1，上面那条源码断言会红。
  const plan = planOverflowLabels({ count: 99, limit: 5 }, [{ number: 1, hasOverflow: false }]);
  assert.deepEqual(plan.toLabel, [1], '超容仍应照常打标签，而不是提前退出');
  const src = readFileSync('scripts/guard_now_capacity.mjs', 'utf8');
  assert.doesNotMatch(src, /if \(!verdict\.ok\)\s*process\.exit/, '不得因超容提前退出');
});

test('证伪探针：把「自动撤标签」删掉必须被抓出', () => {
  // 真实现：容量回落时 toUnlabel 非空。若删掉这半边，用例会红。
  const plan = planOverflowLabels({ count: 2, limit: 5 }, [{ number: 9, hasOverflow: true }]);
  assert.deepEqual(plan.toUnlabel, [9]);
});
