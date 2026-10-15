/**
 * `scripts/governance_files_rule.js` 的回归用例（源 CNB #269 / #450，2026-10-14）。
 *
 * ## WHY 有这份文件
 *
 * 这份判据要判的是**别处**（真实 PR 的改动方向）的对错，而它自己出错的方式是
 * **两个方向各一种假信号**，两种都坏：
 *
 *   - **写松**（漏掉治理文件）⇒ 假绿：本该提示的 PR 被判通过，冲突面悄悄长回来，
 *     正是 #269 / #450 反复复发的那件事；
 *   - **写紧**（把普通文件也当治理文件）⇒ 假红：所有 PR 都被提示，人开始忽略它，
 *     信号先不可信、问题才被掩盖（与 #1434 / #1515 同型）。
 *
 * 故重点用例是两端的边界，而不是 happy path。
 *
 * ## 怎么跑
 *
 *     node --test "scripts/tests/*.test.js"     # 或根目录 `pnpm test:scripts`
 *
 * 依赖：**零新依赖**（只用 Node 内置 `node:test` / `node:assert`），纯离线。
 */

'use strict';

const assert = require('node:assert/strict');
const { test } = require('node:test');

const rule = require('../../scripts/governance_files_rule.js');
const { GOVERNANCE_FILES, normalizePath, findGovernanceHits, checkGovernanceDirection } = rule;

const fs = require('node:fs');
const path = require('node:path');

// ---------------------------------------------------------------------------
// 一、路径归一化
// ---------------------------------------------------------------------------

test('normalizePath: 去掉 ./ 前缀并统一反斜杠', () => {
  assert.equal(normalizePath('./AGENTS.md'), 'AGENTS.md');
  assert.equal(normalizePath('a\\b\\c.yml'), 'a/b/c.yml');
  assert.equal(normalizePath('  .cnb.yml  '), '.cnb.yml');
});

test('normalizePath: 非字符串输入不抛异常，返回空串', () => {
  assert.equal(normalizePath(undefined), '');
  assert.equal(normalizePath(null), '');
  assert.equal(normalizePath(42), '');
});

// ---------------------------------------------------------------------------
// 二、命中判定（假绿方向：漏掉治理文件）
// ---------------------------------------------------------------------------

test('findGovernanceHits: 命中治理文件', () => {
  assert.deepEqual(findGovernanceHits(['.cnb.yml', 'src/a.ts']), ['.cnb.yml']);
  assert.deepEqual(findGovernanceHits(['./AGENTS.md']), ['AGENTS.md']);
});

test('findGovernanceHits: 普通文件不命中', () => {
  assert.deepEqual(findGovernanceHits(['src/a.ts', 'frontend/package.json']), []);
});

test('findGovernanceHits: 空输入返回空数组，不抛异常', () => {
  assert.deepEqual(findGovernanceHits([]), []);
  assert.deepEqual(findGovernanceHits(undefined), []);
});

test('findGovernanceHits: 多个命中保持清单顺序且去重', () => {
  const hits = findGovernanceHits(['AGENTS.md', '.cnb.yml', '.cnb.yml']);
  assert.deepEqual(hits, ['.cnb.yml', 'AGENTS.md']);
});

// ---------------------------------------------------------------------------
// 三、方向判定
// ---------------------------------------------------------------------------

test('checkGovernanceDirection: 未碰治理文件 ⇒ ok=true', () => {
  const res = checkGovernanceDirection({ number: 1, files: ['src/a.ts'] });
  assert.equal(res.ok, true);
  assert.deepEqual(res.hits, []);
});

test('checkGovernanceDirection: 碰了治理文件 ⇒ ok=false 且列出命中', () => {
  const res = checkGovernanceDirection({ number: 2172, files: ['.cnb.yml', 'AGENTS.md', 'x/y.ts'] });
  assert.equal(res.ok, false);
  assert.deepEqual(res.hits, ['.cnb.yml', 'AGENTS.md']);
  assert.match(res.reason, /PR #2172/);
});

test('checkGovernanceDirection: 缺编号时用 ? 占位，不抛异常', () => {
  const res = checkGovernanceDirection({ files: ['.cnb.yml'] });
  assert.equal(res.ok, false);
  assert.match(res.reason, /PR #\?/);
});

test('checkGovernanceDirection: files 缺失 ⇒ 视为未改动，ok=true', () => {
  // 拿不到改动列表 ≠ 「改了治理文件」；不得凭空报红（假红方向）。
  assert.equal(checkGovernanceDirection({ number: 9 }).ok, true);
});

// ---------------------------------------------------------------------------
// 四、清单本身（防「清单被改空」这类自我架空）
// ---------------------------------------------------------------------------

test('GOVERNANCE_FILES: 包含实测撞过的 5 个文件', () => {
  // 这 5 个是 2026-10-14 `git merge` 的真实冲突面，写在文件头里。
  // 用例钉住它们，防止有人「顺手清理」把清单改空 —— 清单空了，判据当场失效。
  for (const f of [
    '.cnb.yml',
    'AGENTS.md',
    'docs/dev/github-cnb-mirror.md',
    'scripts/bridge/check_branch_divergence.py',
    'backend/tests/test_branch_divergence_check.py',
  ]) {
    assert.ok(GOVERNANCE_FILES.includes(f), `清单缺少 ${f}`);
  }
});

test('GOVERNANCE_FILES: 清单里的文件都真实存在（防写错路径）', () => {
  // 清单是「路径字符串」，写错一个字符它照样能匹配 —— 但匹配不到真实文件，
  // 判据就永远不触发（静默失效）。故逐个核对文件真实存在。
  const root = path.resolve(__dirname, '..', '..');
  for (const f of GOVERNANCE_FILES) {
    assert.ok(
      fs.existsSync(path.join(root, f)),
      `清单里的 ${f} 在仓库里不存在 —— 路径写错了，该判据对它永远不触发`,
    );
  }
});

// ---------------------------------------------------------------------------
// 五、变异探针：判据真的会红吗
// ---------------------------------------------------------------------------

test('变异探针：把清单清空后，治理文件不再被命中（证明用例确实依赖清单）', () => {
  // 这条不是「测变异」，而是**证明上面那些用例不是恒真**：
  // 若 findGovernanceHits 是靠硬编码而非 GOVERNANCE_FILES 工作，这里就抓不到。
  const original = GOVERNANCE_FILES.slice();
  try {
    GOVERNANCE_FILES.length = 0;
    assert.deepEqual(findGovernanceHits(['.cnb.yml', 'AGENTS.md']), []);
  } finally {
    GOVERNANCE_FILES.push(...original);
  }
  assert.deepEqual(findGovernanceHits(['.cnb.yml']), ['.cnb.yml']);
});
