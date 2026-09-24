/**
 * `scripts/close_linked_issues.js` 的回归用例（源 #1683）。
 *
 * ## WHY 有这份文件
 *
 * 该脚本被 `.github/workflows/close-linked-issues.yml` **直接驱动**，且做的是**有副作用**的事：
 * 关闭 issue。它一旦「静默半可用」，后果不是少关一次，而是**误关别人的卡**——所以每个边界
 * 都必须钉住，尤其「宁可不匹配」的那几条：
 *
 *   - 代码块 / 行内代码里的 `Closes #10` 是**在讲机制**（本仓 #1683 的正文正是如此），不是指令；
 *   - `Fixes owner/repo#100` 指的是**别的仓库**，不该动；
 *   - `prefix #10` / `see #10` 不是关键字，不该动。
 *
 * 反过来，该关的没关也是失效（本卡存在的意义就是消灭「合并了但卡没关」），故正向用例同样齐全。
 *
 * ## 怎么跑
 *
 *     node --test "scripts/tests/*.test.js"     # 或根目录 `pnpm test:scripts`
 *
 * 依赖：**零新依赖**（只用 Node 内置 `node:test` / `node:assert`）；
 * `github` / `context` / `core` 全部 mock（纯离线、无网络）。
 */

'use strict';

const assert = require('node:assert/strict');
const { test } = require('node:test');

const closeLinkedIssues = require('../../scripts/close_linked_issues.js');
const { parseClosingKeywords } = closeLinkedIssues;

const REPO = 'imoyao/fundmate';

/** 只关心「解析出哪些编号」，故用辅助函数把结果压平成数组。 */
const nums = (body, opts) => parseClosingKeywords(body, { repo: REPO, ...(opts || {}) }).numbers;

// ---------------------------------------------------------------------------
// 一、解析器（纯函数）
// ---------------------------------------------------------------------------

test('九个关键字与大小写、可选冒号都能识别', () => {
  const keywords = [
    'close', 'closes', 'closed',
    'fix', 'fixes', 'fixed',
    'resolve', 'resolves', 'resolved',
  ];
  for (const kw of keywords) {
    assert.deepEqual(nums(`${kw} #10`), [10], `小写 ${kw}`);
    assert.deepEqual(nums(`${kw.toUpperCase()} #10`), [10], `大写 ${kw}`);
    assert.deepEqual(nums(`${kw}: #10`), [10], `${kw} 带冒号`);
    assert.deepEqual(nums(`${kw.toUpperCase()}:  #10`), [10], `${kw} 大写冒号多空格`);
  }
});

test('markdown 强调符号不影响识别（**Closes #10**）', () => {
  assert.deepEqual(nums('**Closes #10**'), [10]);
  assert.deepEqual(nums('## 收尾\n\nCloses #10\n'), [10]);
  assert.deepEqual(nums('> Closes #10'), [10]);
});

test('重复关键字列表（GitHub 文档示例写法）', () => {
  assert.deepEqual(nums('Resolves #10, resolves #123'), [10, 123]);
});

test('逗号列表（人手常见写法）', () => {
  assert.deepEqual(nums('Closes #10, #11, #12'), [10, 11, 12]);
  assert.deepEqual(nums('Fixes #10,#11'), [10, 11]);
});

test('同一编号重复出现只算一次', () => {
  assert.deepEqual(nums('Closes #10\n\nFixes #10'), [10]);
  assert.deepEqual(nums('Closes #10, #10'), [10]);
});

test('同仓的 owner/repo#N 写法识别为待关闭', () => {
  assert.deepEqual(nums('Closes imoyao/fundmate#10'), [10]);
  assert.deepEqual(nums('Fixes imoyao/fundmate#10, #11'), [10, 11]);
});

test('跨仓引用只登记到 crossRepo，不进待关闭列表', () => {
  const r = parseClosingKeywords('Fixes octo-org/octo-repo#100', { repo: REPO });
  assert.deepEqual(r.numbers, []);
  assert.deepEqual(r.crossRepo, [{ number: 100, repo: 'octo-org/octo-repo' }]);
});

test('引用 PR 自身编号 → 记入 self，不关闭自己', () => {
  const r = parseClosingKeywords('Closes #42', { repo: REPO, selfNumber: 42 });
  assert.deepEqual(r.numbers, []);
  assert.deepEqual(r.self, [42]);
});

test('围栏代码块内的关键字不匹配（正文讲机制时最常见的误伤源）', () => {
  assert.deepEqual(nums('```\nCloses #10\n```'), []);
  assert.deepEqual(nums('~~~\nFixes #10\n~~~'), []);
  assert.deepEqual(nums('说明：\n\n```markdown\nCloses #10\n```\n\n以上是写法示例。'), []);
});

test('行内代码里的关键字不匹配', () => {
  assert.deepEqual(nums('正文里写 `Closes #10` 就会自动关。'), []);
  assert.deepEqual(nums('| 写法 | 效果 |\n|---|---|\n| `Closes #10` | 关闭 |'), []);
});

test('代码块外的关键字照常匹配（不能被剥离逻辑连带吞掉）', () => {
  assert.deepEqual(nums('```\n示例：Closes #99\n```\n\nCloses #10'), [10]);
});

test('词边界：前缀/后缀词里的 fix 不算关键字', () => {
  assert.deepEqual(nums('prefix #10'), []);
  assert.deepEqual(nums('fixedpoint #10'), []);
  assert.deepEqual(nums('suffix #10'), []);
});

test('纯提及不是关键字', () => {
  assert.deepEqual(nums('see #10'), []);
  assert.deepEqual(nums('参考 #10 的讨论'), []);
  assert.deepEqual(nums('https://github.com/imoyao/fundmate/issues/10'), []);
});

test('非法编号（0 / 纯文本）不产生条目', () => {
  assert.deepEqual(nums('Closes #0'), []);
  assert.deepEqual(nums('Closes #'), []);
});

test('空正文 / null / undefined 安全返回空结果', () => {
  for (const body of ['', null, undefined, '无关键字的正文']) {
    assert.deepEqual(parseClosingKeywords(body, { repo: REPO }), {
      numbers: [],
      crossRepo: [],
      self: [],
    });
  }
});

test('多个关键字混排时保持出现顺序', () => {
  assert.deepEqual(nums('Fixes #7\nCloses #3\nResolves #9'), [7, 3, 9]);
});

// ---------------------------------------------------------------------------
// 二、workflow 入口（mock github / context / core）
// ---------------------------------------------------------------------------

function makeCore() {
  const state = { notices: [], warnings: [], failed: null };
  const chain = {
    addHeading: () => chain,
    addRaw: () => chain,
    addList: () => chain,
    write: async () => {},
  };
  return {
    state,
    notice: (m) => state.notices.push(m),
    warning: (m) => state.warnings.push(m),
    setFailed: (m) => {
      state.failed = m;
    },
    summary: chain,
  };
}

/**
 * @param {Record<number, object>} issues  issue_number -> 数据（缺省视为 404）
 */
function makeGithub(issues) {
  const calls = { get: [], update: [] };
  return {
    calls,
    rest: {
      issues: {
        get: async ({ issue_number }) => {
          calls.get.push(issue_number);
          const found = issues[issue_number];
          if (!found) {
            const err = new Error('Not Found');
            err.status = 404;
            throw err;
          }
          return { data: found };
        },
        update: async (params) => {
          calls.update.push(params);
          return { data: {} };
        },
      },
      pulls: {
        get: async ({ pull_number }) => ({ data: issues.__pull || { number: pull_number } }),
      },
    },
  };
}

const openIssue = (number, title) => ({ number, title, state: 'open' });

function makeContext(pr, inputs) {
  return {
    repo: { owner: 'imoyao', repo: 'fundmate' },
    payload: { pull_request: pr, inputs },
  };
}

const mergedPr = (body, extra) => ({
  number: 1680,
  title: 'fix(positions): 示例',
  body,
  merged: true,
  merged_at: '2026-09-24T13:41:23Z',
  base: { ref: 'dev' },
  ...(extra || {}),
});

test('合入 dev 且有关键字 → 逐个关闭并标记 completed', async () => {
  const github = makeGithub({ 1662: openIssue(1662, '卡 A'), 1676: openIssue(1676, '卡 B') });
  const core = makeCore();

  await closeLinkedIssues({
    github,
    context: makeContext(mergedPr('## 收尾\n\nCloses #1662, closes #1676\n')),
    core,
  });

  assert.deepEqual(github.calls.update, [
    { owner: 'imoyao', repo: 'fundmate', issue_number: 1662, state: 'closed', state_reason: 'completed' },
    { owner: 'imoyao', repo: 'fundmate', issue_number: 1676, state: 'closed', state_reason: 'completed' },
  ]);
  assert.equal(core.state.failed, null);
});

test('已关闭的 issue 跳过（幂等：重复触发不重复关、不报错）', async () => {
  const github = makeGithub({ 1662: { number: 1662, title: '已关', state: 'closed' } });
  const core = makeCore();

  await closeLinkedIssues({ github, context: makeContext(mergedPr('Closes #1662')), core });

  assert.deepEqual(github.calls.update, []);
  assert.equal(core.state.failed, null);
});

test('引用的是 PR 而非 issue → 不关（只关 issue）', async () => {
  const github = makeGithub({
    999: { number: 999, title: '某个 PR', state: 'open', pull_request: { url: 'x' } },
  });
  const core = makeCore();

  await closeLinkedIssues({ github, context: makeContext(mergedPr('Closes #999')), core });

  assert.deepEqual(github.calls.update, []);
  assert.ok(core.state.notices.some((n) => n.includes('是 pull request')));
});

test('未合并的 PR 直接跳过', async () => {
  const github = makeGithub({ 10: openIssue(10, 'x') });
  const core = makeCore();

  await closeLinkedIssues({
    github,
    context: makeContext(mergedPr('Closes #10', { merged: false, merged_at: null })),
    core,
  });

  assert.deepEqual(github.calls.get, []);
  assert.deepEqual(github.calls.update, []);
});

test('目标分支不是 dev（如发版 PR）跳过 —— 那个方向由 GitHub 原生处理', async () => {
  const github = makeGithub({ 10: openIssue(10, 'x') });
  const core = makeCore();

  await closeLinkedIssues({
    github,
    context: makeContext(mergedPr('Closes #10', { base: { ref: 'main' } })),
    core,
  });

  assert.deepEqual(github.calls.update, []);
  assert.ok(core.state.notices.some((n) => n.includes('非 dev')));
});

test('正文没有关键字 → 不调任何 API', async () => {
  const github = makeGithub({});
  const core = makeCore();

  await closeLinkedIssues({ github, context: makeContext(mergedPr('只改文档，无关联卡。')), core });

  assert.deepEqual(github.calls.get, []);
  assert.deepEqual(github.calls.update, []);
  assert.equal(core.state.failed, null);
});

test('dry-run 只报告、不实际关闭', async () => {
  const github = makeGithub({ 10: openIssue(10, '卡 X') });
  const core = makeCore();

  await closeLinkedIssues({
    github,
    context: makeContext(mergedPr('Closes #10'), { dry_run: 'true' }),
    core,
  });

  assert.deepEqual(github.calls.update, []);
  assert.deepEqual(github.calls.get, [10]);
});

test('读取不到的编号只告警；全部失败才红（防「本该关却没关」静默溜过）', async () => {
  const github = makeGithub({});
  const core = makeCore();

  await closeLinkedIssues({ github, context: makeContext(mergedPr('Closes #404, #405')), core });

  assert.ok(core.state.warnings.length >= 2);
  assert.ok(core.state.failed && core.state.failed.includes('全部'));
});

test('部分成功时不红（网络抖动不该让门禁噪音化）', async () => {
  const github = makeGithub({ 10: openIssue(10, '存在'), 404: undefined });
  const core = makeCore();

  await closeLinkedIssues({ github, context: makeContext(mergedPr('Closes #10, #404')), core });

  assert.equal(github.calls.update.length, 1);
  assert.equal(core.state.failed, null);
});

test('跨仓引用只告警，不跨仓操作', async () => {
  const github = makeGithub({});
  const core = makeCore();

  await closeLinkedIssues({
    github,
    context: makeContext(mergedPr('Fixes octo-org/octo-repo#100')),
    core,
  });

  assert.deepEqual(github.calls.get, []);
  assert.deepEqual(github.calls.update, []);
  assert.ok(core.state.warnings.some((w) => w.includes('octo-org/octo-repo#100')));
});

test('workflow_dispatch 手动复检：按 inputs.pr_number 回读 PR', async () => {
  const pr = mergedPr('Closes #10');
  const github = makeGithub({ 10: openIssue(10, '卡 Y'), __pull: pr });
  const core = makeCore();

  await closeLinkedIssues({
    github,
    context: { repo: { owner: 'imoyao', repo: 'fundmate' }, payload: { inputs: { pr_number: '1680' } } },
    core,
  });

  assert.deepEqual(github.calls.update.map((u) => u.issue_number), [10]);
});

test('既无事件负载也无 pr_number → 显式失败（不静默通过）', async () => {
  const github = makeGithub({});
  const core = makeCore();

  await closeLinkedIssues({
    github,
    context: { repo: { owner: 'imoyao', repo: 'fundmate' }, payload: {} },
    core,
  });

  assert.ok(core.state.failed && core.state.failed.includes('pr_number'));
});
