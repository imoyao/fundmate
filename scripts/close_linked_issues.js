/**
 * 按 closing keyword 关闭关联 issue（`.github/workflows/close-linked-issues.yml` 经
 * `actions/github-script` 调用）。
 *
 * ## WHY 需要它（2026-09-24 查证，源 #1683）
 *
 * GitHub 只在 PR 目标为**仓库默认分支**时解释 `Closes` / `Fixes` / `Resolves #N`。
 * 官方文档（`linking-a-pull-request-to-an-issue`）原文：
 *
 * > The special keywords in a pull request description are interpreted **only when the pull request
 * > targets the repository's default branch**. If the pull request targets **any other branch**,
 * > then these keywords are **ignored, no links are created**, and merging the PR has no effect
 * > on the issues.
 *
 * 本仓默认分支是 `main`，而功能 PR 一律 base=`dev` ⇒ 关键字**被完全忽略**（连 link 都不建）。
 * 实测（2026-09-24）：最近 100 个已关闭 PR 里 **15 个**正文写了 `Closes #NNNN`，**全部无效**，
 * issue 每次靠人肉关。阳性/阴性对照：
 *
 *   - 阳性（`base=main`）PR #1295 merged `11:50:17` → #822 `closed` `11:50:18`（**1 秒**，自动关）；
 *   - 阴性（`base=dev`）PR #1679 merged `12:51:00` → #1678 先被人 `commented`、`12:51:18` 才 `closed`（人肉）。
 *
 * 本模块在 **dev 合入**时补上这一步 —— 语义上「dev 合入 = 该卡完成」，与既有实践一致，
 * 只是把人工动作机器化。发版 PR（`dev → main`）**不需要**它：那个方向 GitHub 原生就会关。
 *
 * ## WHY 抽成单文件而非内联进 workflow
 *
 * 同 `ai_review_verify_guard.js` 的先例：关键字解析有一堆边界（围栏/行内代码、跨仓、逗号列表、
 * 词边界…），内联进 YAML 就没法单测。而这类解析器一旦「静默半可用」——比如把文档示例里的
 * `` `Closes #10` `` 当成真指令——后果是**误关别人的卡**。故解析与副作用分离：解析器是纯函数，
 * 由 `scripts/tests/close_linked_issues.test.js` 钉住。
 *
 * ## 用法
 *
 *     await require(`${process.env.GITHUB_WORKSPACE}/scripts/close_linked_issues.js`)({ github, context, core });
 *
 * 入参走 workflow 上下文：事件路径用 `context.payload.pull_request`；`workflow_dispatch` 手动复检
 * 路径用 `inputs.pr_number` / `inputs.dry_run`（事件负载为空）。
 */
'use strict';

/**
 * 把围栏代码块（``` / ~~~）整段与行内代码（`...`）剔除后再解析。
 *
 * WHY：PR 正文里出现 `Closes #123` 的常见场景是**在讲这个机制本身**（本仓 issue #1683 的正文就是），
 * 或贴了一段别的 PR 的示例。GitHub 自己也不解释代码块里的关键字。少关一次远好于误关一次，
 * 故这里**宁可不匹配**。
 */
function stripCode(text) {
  const kept = [];
  let inFence = false;
  for (const line of String(text).split('\n')) {
    if (/^\s*(?:```|~~~)/.test(line)) {
      inFence = !inFence;
      continue;
    }
    if (!inFence) kept.push(line);
  }
  return kept.join('\n').replace(/`[^`\n]*`/g, ' ');
}

/**
 * GitHub 支持的九个关键字：close/closes/closed、fix/fixes/fixed、resolve/resolves/resolved。
 * 大小写不敏感，关键字后可跟一个可选冒号（`Closes: #10` / `CLOSES #10` / `CLOSES: #10` 均合法）。
 */
const KEYWORD_RE =
  /\b(?:close[sd]?|fix(?:e[sd])?|resolve[sd]?)\b\s*:?\s*(?:([A-Za-z0-9][A-Za-z0-9_.-]*)\/([A-Za-z0-9][A-Za-z0-9_.-]*))?#(\d+)/gi;

/**
 * 关键字之后的逗号列表（`Closes #10, #11, #12`）。
 * GitHub 文档的示例是**重复关键字**（`Resolves #10, resolves #123`），但逗号列表是更常见的人手写法，
 * 两种都收 —— 只是重复关键字本来就会被主正则再匹配一次，这里专门补逗号这种。
 */
const TAIL_RE = /^\s*,\s*#(\d+)/;

/**
 * 纯函数：从 PR 正文里抽出要关闭的 issue 编号。
 *
 * @param {string|null|undefined} body PR 正文（markdown）
 * @param {{repo?: string, selfNumber?: number}} [opts]
 *   `repo` 为当前仓库 `owner/name`（用于判跨仓）；`selfNumber` 为 PR 自身编号（排除自引用）。
 * @returns {{numbers: number[], crossRepo: Array<{number:number,repo:string}>, self: number[]}}
 *   - `numbers`：**本仓、非自身、去重后**待关闭的 issue 编号，保持出现顺序；
 *   - `crossRepo`：指向其他仓库的引用（调用方只告警、不跨仓操作）；
 *   - `self`：引用 PR 自身编号的（不关自己）。
 */
function parseClosingKeywords(body, opts) {
  const { repo, selfNumber } = opts || {};
  const result = { numbers: [], crossRepo: [], self: [] };
  if (!body) return result;

  const text = stripCode(body);
  const ownRepo = String(repo || '').toLowerCase();
  const seen = new Set();

  const add = (rawNum, owner, name) => {
    const n = Number(rawNum);
    if (!Number.isInteger(n) || n <= 0) return;

    // 跨仓写法 `Fixes owner/repo#100`：本仓的才处理，别的仓一律不动（避免误关别人仓库的卡）
    if (owner && name && `${owner}/${name}`.toLowerCase() !== ownRepo) {
      if (!result.crossRepo.some((x) => x.number === n && x.repo === `${owner}/${name}`)) {
        result.crossRepo.push({ number: n, repo: `${owner}/${name}` });
      }
      return;
    }

    if (selfNumber && n === selfNumber) {
      if (!result.self.includes(n)) result.self.push(n);
      return;
    }

    if (seen.has(n)) return;
    seen.add(n);
    result.numbers.push(n);
  };

  KEYWORD_RE.lastIndex = 0;
  let m;
  while ((m = KEYWORD_RE.exec(text)) !== null) {
    add(m[3], m[1], m[2]);

    let tail = text.slice(KEYWORD_RE.lastIndex);
    let t;
    while ((t = TAIL_RE.exec(tail)) !== null) {
      add(t[1]);
      tail = tail.slice(t[0].length);
    }
  }

  return result;
}

/**
 * workflow 入口。
 *
 * 行为：
 *   - 未合并 / 目标分支不是 `dev` → 直接跳过（发版方向交给 GitHub 原生）；
 *   - 正文无可关闭关键字 → 跳过（绿）；
 *   - 逐个目标：读不到 → 告警；是 PR → 跳过；已关 → 跳过（幂等）；否则关闭（`state_reason=completed`）。
 *
 * 红绿语义（对齐本仓「防假成功」）：**单个**目标失败只告警、不红；**全部**目标都失败才
 * `core.setFailed` —— 否则「本该关却没关」会以绿灯静默溜过去，正是本卡要消灭的失效形态。
 */
module.exports = async function closeLinkedIssues({ github, context, core }) {
  const { owner, repo } = context.repo;
  const fullRepo = `${owner}/${repo}`;
  const inputs = context.payload.inputs || {};
  const dryRun = inputs.dry_run === 'true' || inputs.dry_run === true;

  let pr = context.payload.pull_request;
  if (!pr) {
    const num = Number(inputs.pr_number);
    if (!Number.isInteger(num) || num <= 0) {
      core.setFailed('既无 pull_request 负载，也未提供有效的 inputs.pr_number');
      return;
    }
    pr = (await github.rest.pulls.get({ owner, repo, pull_number: num })).data;
  }

  const label = `#${pr.number}`;

  if (!(pr.merged === true || pr.merged_at)) {
    core.notice(`${label} 未合并，跳过。`);
    return;
  }

  const baseRef = pr.base && pr.base.ref;
  if (baseRef !== 'dev') {
    core.notice(`${label} 目标分支是 ${baseRef}（非 dev），跳过 —— 默认分支方向由 GitHub 原生关闭。`);
    return;
  }

  const parsed = parseClosingKeywords(pr.body, { repo: fullRepo, selfNumber: pr.number });

  for (const x of parsed.crossRepo) {
    core.warning(`${label} 引用了**其他仓库**的 ${x.repo}#${x.number}，本 workflow 不跨仓操作，已跳过。`);
  }
  if (parsed.self.length) {
    core.notice(`${label} 引用了自身编号 ${parsed.self.map((n) => `#${n}`).join(', ')}，跳过。`);
  }

  if (!parsed.numbers.length) {
    core.notice(`${label} 正文里没有可关闭的 closing keyword，无需操作。`);
    return;
  }

  const closed = [];
  const skipped = [];
  let failures = 0;

  for (const n of parsed.numbers) {
    let issue;
    try {
      issue = (await github.rest.issues.get({ owner, repo, issue_number: n })).data;
    } catch (e) {
      failures += 1;
      const why = e && (e.status || e.message);
      skipped.push(`#${n}（读取失败：${why}）`);
      core.warning(`${label} 引用的 #${n} 读取失败：${why}`);
      continue;
    }

    if (issue.pull_request) {
      skipped.push(`#${n}（是 PR，非 issue）`);
      core.notice(`#${n} 是 pull request；本 workflow 只关 issue，跳过。`);
      continue;
    }

    if (issue.state === 'closed') {
      skipped.push(`#${n}（已关闭）`);
      continue;
    }

    if (dryRun) {
      closed.push(`#${n} ${issue.title}（dry-run，未实际关闭）`);
      continue;
    }

    try {
      await github.rest.issues.update({
        owner,
        repo,
        issue_number: n,
        state: 'closed',
        state_reason: 'completed',
      });
      closed.push(`#${n} ${issue.title}`);
      core.notice(`已关闭 #${n}「${issue.title}」—— 由 ${label} 合入 dev 触发。`);
    } catch (e) {
      failures += 1;
      const why = e && (e.status || e.message);
      skipped.push(`#${n}（关闭失败：${why}）`);
      core.warning(`${label} 关闭 #${n} 失败：${why}`);
    }
  }

  if (core.summary) {
    core.summary.addHeading(`自动关闭关联 issue（${label}）`, 3);
    core.summary.addRaw(`触发 PR：${label} ${pr.title || ''}\n目标分支：${baseRef}\n`);
    if (dryRun) core.summary.addRaw('**dry-run：未实际关闭任何 issue**\n');
    if (closed.length) core.summary.addList(closed.map((x) => `已关闭 ${x}`));
    if (skipped.length) core.summary.addList(skipped.map((x) => `跳过 ${x}`));
    await core.summary.write();
  }

  // 全部目标都失败 → 红。单个失败不红（网络抖动不该让门禁噪音化）。
  if (failures > 0 && failures === parsed.numbers.length) {
    core.setFailed(
      `${label} 引用了 ${parsed.numbers.length} 个 issue，但**全部**操作失败 —— 请人工确认并补关。`
    );
  }
};

// 供 scripts/tests/close_linked_issues.test.js 直接断言（解析器是纯函数，可离线测）
module.exports.parseClosingKeywords = parseClosingKeywords;
module.exports.stripCode = stripCode;
