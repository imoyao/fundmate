/**
 * `scripts/claim_in_progress.mjs` 的回归用例。
 *
 * ## WHY 有这份文件
 *
 * 这个守卫的存在理由是 2026-10-19 的一次真实撞车：两个 agent 会话同时改
 * `#2406` 的同一处代码，而当时三个既有机制全部落空（overlap 守卫不守业务代码、
 * claim-sync 只同步 CNB 侧、issue 上没有任何占用标记）。
 *
 * 所以测试重心不是「标签加得对不对」，而是**守住它的两个设计承诺**：
 *   1. **取数失败时什么都不做**（认领标记错了会误导别人，比没标记更糟）；
 *   2. **撞车不阻断**（阻止会惩罚先动手的人，要的是可发现不是禁止）。
 *
 * 另外要钉住「多个 PR 做同一张卡」这个真实场景——先关一个不能把标记摘掉。
 *
 * ## 怎么跑
 *
 *     node --test "scripts/tests/claim_in_progress.test.js"
 *
 * 依赖：零新依赖，纯离线。
 */

'use strict';

const assert = require('node:assert/strict');
const { test } = require('node:test');
const { readFileSync } = require('node:fs');

const { decideClaim, parseLinkedIssues, CLAIM_LABEL, COLLISION_MARKER } = require('../claim_in_progress.mjs');

test('常量：标签名与隐藏键拼写（写错会导致整套机制静默失效）', () => {
  assert.equal(CLAIM_LABEL, 'in-progress');
  assert.equal(COLLISION_MARKER, 'claim-collision-alert');
});

test('PR 打开 → 打标', () => {
  const v = decideClaim({ openPrCount: 1, hasLabel: false, event: 'opened' });
  assert.equal(v.label, 'add');
  assert.equal(v.collision, false);
});

test('PR 打开但已有标记 → 幂等，不重复打', () => {
  assert.equal(decideClaim({ openPrCount: 1, hasLabel: true, event: 'opened' }).label, 'none');
});

test('PR 关闭且无其他 PR → 摘标', () => {
  assert.equal(decideClaim({ openPrCount: 0, hasLabel: true, event: 'closed' }).label, 'remove');
});

test('PR 关闭但**还有别的 PR 在做** → 保持占用（先关一个不该释放卡）', () => {
  const v = decideClaim({ openPrCount: 1, hasLabel: true, event: 'closed' });
  assert.equal(v.label, 'none', '还有 1 个 open PR 就不该摘标记');
  assert.match(v.reason, /仍有 1 个 open PR/);
});

test('同一 issue 被 ≥2 个 open PR 关联 → 判为撞车', () => {
  assert.equal(decideClaim({ openPrCount: 2, hasLabel: true, event: 'opened' }).collision, true);
  assert.equal(decideClaim({ openPrCount: 1, hasLabel: true, event: 'opened' }).collision, false);
});

test('取数失败 → 什么都不做（误标占用比没标更糟）', () => {
  for (const bad of [NaN, -1, undefined]) {
    const v = decideClaim({ openPrCount: bad, hasLabel: false, event: 'opened' });
    assert.equal(v.label, 'none', `${bad} 不应产生任何改动`);
    assert.match(v.reason, /取数失败/);
  }
});

test('无 PR 关联 → 不动', () => {
  assert.equal(decideClaim({ openPrCount: 0, hasLabel: false, event: 'opened' }).label, 'none');
});

test('解析：closing 关键字（Closes / Fixes / Resolves）', () => {
  const issues = parseLinkedIssues('closes #2406\nFixes #100\nresolves #7');
  assert.ok(issues.includes(2406));
  assert.ok(issues.includes(100));
});

test('解析：非 closing 的显式关联（关联 / 相关 / Refs / Part of）', () => {
  const issues = parseLinkedIssues('关联 `GitHub #2406`\nRefs #99\nPart of #88');
  assert.ok(issues.includes(2406), '关联应被识别——很多 PR 只引用不关闭');
  assert.ok(issues.includes(99));
});

test('解析：行内代码裸编号 `` `#N` ``（挂源形态）', () => {
  assert.ok(parseLinkedIssues('顺带提到 `#2406` 的背景').includes(2406));
});

test('解析：去重且排序', () => {
  const issues = parseLinkedIssues('closes #5\n关联 #5\n`#3`');
  assert.deepEqual(issues, [3, 5]);
});

test('解析：围栏代码块内的关键字不误伤（复用 close_linked_issues 的 stripCode）', () => {
  const body = '```\ncloses #9999\n```\n正文：closes #1';
  const issues = parseLinkedIssues(body);
  assert.ok(!issues.includes(9999), '代码块内的不应被解析');
  assert.ok(issues.includes(1));
});

test('CLI 不对撞车 exit 非 0（告警不是阻断）', () => {
  const src = readFileSync('scripts/claim_in_progress.mjs', 'utf8');
  const cli = src.slice(src.indexOf('async function main'));
  const code = cli.split(/\r?\n/).map((l) => l.replace(/\/\/.*$/, '')).join('\n');
  // 只允许两处：用法错误 exit 2、正常收尾 exit 0
  const exits = [...code.matchAll(/process\.exit\(([^)]*)\)/g)].map((m) => m[1].trim());
  assert.ok(exits.includes('0'), '必须有 exit 0 的正常收尾');
  assert.ok(!exits.some((e) => e === '1'), '撞车不得 exit 1——阻止会惩罚先动手的人');
});

test('证伪探针：把「还有 PR 就保持占用」改写成「关闭即摘标」必须被抓出', () => {
  // 真实现：关闭但仍有 1 个 open PR → 保持。朴素版会摘标。
  const naive = (event) => (event === 'closed' ? 'remove' : 'add');
  assert.equal(decideClaim({ openPrCount: 1, hasLabel: true, event: 'closed' }).label, 'none');
  assert.equal(naive('closed'), 'remove', '朴素版会误摘 → 说明这条判据确实拦住了东西');
});

test('证伪探针：把取数失败改成「判为占用」必须被抓出', () => {
  const real = decideClaim({ openPrCount: NaN, hasLabel: false, event: 'opened' });
  assert.equal(real.label, 'none');
  const failClosed = () => 'add';
  assert.equal(failClosed(), 'add', 'fail-closed 版会误标占用 → 两者结论必须相反');
});
