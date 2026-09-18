/**
 * `scripts/ai_review_verify_guard.js` 的回归用例（#1584）。
 *
 * WHY 有这份文件
 * --------------
 * 该脚本被 `.github/workflows/ai-review.yml` **直接驱动**，同时决定三件事：
 *   ① 本轮审查是否算「真产出」（否则 `core.setFailed()` → job 红）；
 *   ② 是否清理 agent 协议信封泄漏的评论；
 *   ③ （2026-09-17 起，#1581 行为 a）统计「生成标记」类幻觉并写进 job summary。
 * 三者里任何一处写错，后果都是**把 job 带红或带绿**（假红灯 / 假绿），故值得钉住。
 *
 * 这份文件是 #1582 的临时 harness 的固化版——那个 harness 当时**当场抓到过一个真 bug**
 * （初版在「无标记」分支误写 `return`，会把整个防假成功判定跳过），说明这类回归网确有用。
 *
 * 怎么跑
 * ------
 *     node --test scripts/tests/        # 或根目录 `pnpm test:scripts`
 *
 * 依赖：**零新依赖**（只用 Node 内置 `node:test` / `node:assert`）；
 * `github` / `context` / `core` 全部 mock，调用签名与 workflow 一致（纯离线、无网络）。
 */

'use strict';

const assert = require('node:assert/strict');
const { test } = require('node:test');

const guard = require('../../scripts/ai_review_verify_guard.js');

const INLINE_TAG = '\n\n#ai-review-inline';
const SUMMARY_TAG = '\n\n#ai-review-summary';
/** 让 `countAll()`（行内评论 + reviews）大于审查前快照，避免走「重试 5×5s」的等待分支。
 *  它只影响 mock 的计数，不改变被断言的行为。 */
const ONE_REVIEW = [{ id: 'r1' }];

/** mock @actions/core（含 summary 链式 API）。 */
function makeCore({ withSummary = true } = {}) {
  const calls = { info: [], warning: [], notice: [], failed: [], summary: [] };
  const summary = {
    addHeading(t) {
      calls.summary.push(['heading', t]);
      return this;
    },
    addTable(rows) {
      calls.summary.push(['table', rows]);
      return this;
    },
    addRaw(t) {
      calls.summary.push(['raw', t]);
      return this;
    },
    async write() {
      calls.summary.push(['write']);
      return this;
    },
  };
  const core = {
    calls,
    info: m => calls.info.push(m),
    warning: m => calls.warning.push(m),
    notice: m => calls.notice.push(m),
    setFailed: m => calls.failed.push(m),
  };
  if (withSummary) core.summary = summary;
  return core;
}

/** mock github.rest（只用到 4 个方法）。 */
function makeGithub({ inline = [], general = [], reviews = [], deleted = [] }) {
  return {
    rest: {
      pulls: {
        listReviewComments: async () => ({ data: inline }),
        listReviews: async () => ({ data: reviews }),
        deleteReviewComment: async a => deleted.push(`inline#${a.comment_id}`),
      },
      issues: {
        listComments: async () => ({ data: general }),
        deleteComment: async a => deleted.push(`general#${a.comment_id}`),
      },
    },
  };
}

const CONTEXT = { payload: { pull_request: { number: 0 } }, repo: { owner: 'o', repo: 'r' } };

async function run({
  inline = [],
  general = [],
  reviews = ONE_REVIEW,
  before = '0',
  selectedOk = 'false',
  core,
  github,
} = {}) {
  process.env.AI_REVIEW_BEFORE = before;
  process.env.AI_REVIEW_SELECTED_OK = selectedOk;
  process.env.AI_REVIEW_ROUND = '1';
  const c = core || makeCore();
  const deleted = [];
  const g = github || makeGithub({ inline, general, reviews, deleted });
  await guard({ github: g, context: CONTEXT, core: c });
  return { core: c, deleted };
}

/** 取 job summary 里的表格数据行（去掉表头）。 */
function summaryRows(core) {
  const entry = core.calls.summary.find(x => x[0] === 'table');
  return entry ? entry[1].slice(1) : [];
}

// ---------------------------------------------------------------------------
// ① 「生成标记」幻觉统计（#1581 行为 a）—— 只计数、不删除、不改成败
// ---------------------------------------------------------------------------

test('假 inline 意见（`# added`）→ 计数 1，且不删除、不判失败', async () => {
  const { core, deleted } = await run({
    inline: [
      { id: 1, path: 'frontend/a.vue', line: 33, body: '[阻断] 行尾的 `# added` 会进入 SCSS 源码' + INLINE_TAG },
    ],
  });
  const rows = summaryRows(core);
  assert.equal(rows.length, 1, '应命中 1 条');
  assert.equal(rows[0][0], 'inline', '通道应为 inline');
  assert.deepEqual(deleted, [], '行为 a 不得删除任何评论');
  assert.deepEqual(core.calls.failed, [], '不得影响 job 成败');
});

test('假 summary 意见（`// added`，即 #1578 第 5 次复发同型）→ 计数 1', async () => {
  const { core, deleted } = await run({
    general: [
      {
        id: 2,
        body: '## 审查结论\n`docs/spec/ai-review.md:57` 新增行行尾带 `// added` 标记' + SUMMARY_TAG,
      },
    ],
  });
  const rows = summaryRows(core);
  assert.equal(rows.length, 1);
  assert.equal(rows[0][0], 'summary', '第 5 次复发发生在摘要通道，必须扫到');
  assert.deepEqual(deleted, []);
});

test('真意见（引 diff 内真实片段、无生成标记）→ 不命中', async () => {
  const { core } = await run({
    inline: [
      {
        id: 3,
        path: 'backend/a.py',
        line: 70,
        body: '[次要] 建议给 basic 字典构造补 `.get()` 防御（同函数 redeem 循环已做 `if not code: continue`）' + INLINE_TAG,
      },
    ],
  });
  assert.deepEqual(summaryRows(core), [], '真意见不得被计数');
  assert.ok(
    core.calls.info.some(m => m.includes('未发现')),
    '应打「未发现」info，便于在日志里确认该步骤确实跑过'
  );
});

test('混合（假 / 真 / 「在讨论该幻觉」）→ 命中 2 条（已知误计 1 条，符合设计）', async () => {
  const { core, deleted } = await run({
    inline: [
      { id: 4, path: 'a.md', line: 1, body: '行尾 `# added` 应删除' + INLINE_TAG },
      { id: 5, path: 'b.md', line: 2, body: '这段逻辑没问题' + INLINE_TAG },
      { id: 6, path: 'c.md', line: 3, body: '本文件没有 `# added` 残留，无需处理' + INLINE_TAG },
    ],
  });
  const rows = summaryRows(core);
  assert.equal(rows.length, 2, '1 条真幻觉 + 1 条「在讨论该幻觉」（行为 a 下的已知误计）');
  assert.deepEqual(deleted, []);
});

test('core.summary 缺失（更老的 @actions/core）→ 不抛错，仍打告警', async () => {
  const core = makeCore({ withSummary: false });
  const { deleted } = await run({
    inline: [{ id: 7, path: 'y.vue', line: 1, body: '行尾 `# added` 应删除' + INLINE_TAG }],
    core,
  });
  assert.ok(core.calls.warning.some(m => m.includes('疑似')), '仍应打「疑似」告警');
  assert.deepEqual(deleted, []);
});

test('统计步骤自身抛错 → 不上抛、留「已跳过」告警、主判定照常', async () => {
  const core = makeCore();
  const deleted = [];
  const github = makeGithub({
    inline: [{ id: 9, path: 'z.ts', line: 1, body: '普通意见，无标记' + INLINE_TAG }],
    deleted,
  });
  // 步骤 4 是 `listComments()` 的第 3 次调用（步骤 2 / 步骤 3 各一次），只在第 3 次抛错，
  // 才能精确打到「新增步骤」内部的 try/catch，而不误伤既有代码路径。
  let calls = 0;
  const realListComments = github.rest.issues.listComments;
  github.rest.issues.listComments = async args => {
    calls += 1;
    if (calls === 3) throw new Error('boom（仿真：仅步骤 4 的评论接口失败）');
    return realListComments(args);
  };
  await assert.doesNotReject(() => run({ core, github }), '附加观测的异常不得向上抛（否则会把 job 带红）');
  assert.ok(core.calls.warning.some(m => m.includes('已跳过')));
  assert.deepEqual(core.calls.failed, [], '主判定应正常放行');
});

// ---------------------------------------------------------------------------
// ② 既有语义回归：防假成功 / 协议信封清理 / 成功路径
//    改这个脚本时，最该钉住的就是这三条 —— 它们直接决定 job 的红绿。
// ---------------------------------------------------------------------------

test('零产出（无任何 AI 评论）→ 仍 setFailed（防假成功语义）', async () => {
  const { core } = await run({ before: '0', selectedOk: 'false', reviews: ONE_REVIEW });
  assert.equal(core.calls.failed.length, 1, '必须判失败，否则假成功会伪装成通过');
  assert.ok(core.calls.failed[0].includes('未产出任何有效评论'));
});

test('零产出但 PR 上已有历史 AI 评论 + 探测选中健康模型 → 不判失败，但打「假成功」告警', async () => {
  // 该分支（#1411 的残留缺口）只在「本轮无新增评论」时触发——脚本会按设计重试 5 次 × 5s，
  // 故本用例约 25s（比其余用例慢，属预期成本；这也是它单独成条的原因）。
  const { core } = await run({
    before: '1',
    selectedOk: 'true',
    reviews: ONE_REVIEW,
    general: [{ id: 21, body: '历史审查结论（上一轮留下的）' + SUMMARY_TAG }],
  });
  assert.deepEqual(core.calls.failed, [], '有历史评论兜底时保持成功结论（既有设计）');
  assert.ok(core.calls.warning.some(m => m.includes('未新增评论')), '必须打出醒目告警');
});

test('协议信封泄漏 → 仍被删除，且不计入生成标记统计', async () => {
  const { core, deleted } = await run({
    inline: [
      { id: 11, path: 'x.ts', line: 9, body: '{"action": "TOOL_CALL", "command": "git diff"}' + INLINE_TAG },
    ],
  });
  assert.deepEqual(deleted, ['inline#11'], '协议泄漏评论必须被清理');
  assert.deepEqual(summaryRows(core), [], '协议泄漏评论不应计入标记统计');
});

test('有新增评论且清理后仍有 AI 评论 → 放行（成功路径不得被统计步骤破坏）', async () => {
  const { core } = await run({
    inline: [{ id: 12, path: 'ok.ts', line: 1, body: '正常意见' + INLINE_TAG }],
    before: '0',
  });
  assert.deepEqual(core.calls.failed, []);
  assert.ok(core.calls.info.some(m => m.includes('已发布评论')));
});
