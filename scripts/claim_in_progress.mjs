#!/usr/bin/env node
/**
 * 认领同步：把「有 PR 正在做这张卡」自动变成 issue 上的 `in-progress` 标签。
 *
 * ## WHY（源：2026-10-19 真实撞车，用户原话「不要做重复工作」）
 *
 * 当晚我在收尾治理卡，正准备去修 `#2406`（转入腿漏传 name/market），
 * **而另一个 agent 的 PR #2415 已经在修同一处**——两个会话、同一份 dict、
 * 同一处改动，谁都没看见对方。差一点就是两套并行解法 + 合并冲突。
 *
 * 事后复盘为什么没被发现，三个既有机制全部落空：
 *
 *   1. `pr-overlap-guard.yml` **只守 4 类治理文件**（`scripts/bridge/`、
 *      `scripts/check_*.py`、`.cnb.yml`、`AGENTS.md`）；`#2415` 改的是
 *      `backend/app/services/conversion_service.py` —— 业务代码根本不在它的视野里。
 *   2. `claim-sync.yml` 解决的是 **CNB 侧**在做什么（`CNB 处理中` 标签），
 *      方向是「CNB → GitHub」。**GitHub 自己这侧的 PR 不会给自己的卡打任何标记**——
 *      双端协作用的认领机制，反而在自己这侧缺了。
 *   3. `#2406` 当时的标签是 `bug, Q1-RED`，**没有任何「有人在做」的信号**。
 *
 * 于是踩出一个讽刺的结论：**我们为「另一端的仓库在改什么」建了实时认领，
 * 却没为本仓库自己建。** 跨端协作的可见性做得比本地协作还好。
 *
 * ## 为什么是「自动打标签」而不是「开工前记得查 PR」
 *
 * 用户给的约束决定了形状（原话）：
 * 「**只能打 label，因为我们有时候会有多个 agent AI 修改代码。**」
 *
 * 多个 agent 并行是常态，而 agent **不会主动去查 open PR**——它拿到一张卡就去改。
 * 所以「开工前先查有没有 PR 在动它」是软约束，会被绕开（本轮治理已反复证明：
 * 写进 AGENTS.md 的规则对 AI 不可靠）。
 *
 * 唯一可靠的形状是：**把 PR 的存在自动投影到 issue 标签上**——
 * 标签是 agent 看 issue 时**顺带就能看到**的信息，不需要它额外做一次查询。
 * 判据也是客观的（PR 存在与否是事实），不依赖任何人的自觉。
 *
 * ## 判据
 *
 * 1. PR 打开 / 从草稿转正式 → 给正文关联的每个 issue 打 `in-progress`；
 * 2. PR 关闭（合并或放弃）→ **仅当该 issue 不再被任何 open PR 关联时**才摘标签
 *    （多个 PR 做同一张卡是常见的，先关一个不该把标记摘掉）；
 * 3. 同一 issue 被 **≥2 个 open PR** 关联 → 判为**撞车**，在 issue 下评论告警
 *    （幂等：同一组 PR 只留一条评论）。
 *
 * 第 3 条是本守卫最值钱的部分：它不是阻止（阻止会惩罚先动手的人），
 * 而是**让撞车在第一时间可发现**——并行 agent 各自的视角里都只有自己，
 * 只有把信息写到共享的 issue 上，双方才可能看见。
 *
 * ## 用法
 *
 *     node scripts/claim_in_progress.mjs --event opened --pr 2415
 *     node scripts/claim_in_progress.mjs --event closed --pr 2415 --json
 *
 * 退出码：撞车时仍为 0（告警不是阻断，理由见上）。
 *
 * 回归网见 `scripts/tests/claim_in_progress.test.js`。
 */

import { execFileSync } from 'node:child_process';
import { pathToFileURL } from 'node:url';
import { createRequire } from 'node:module';

const require = createRequire(import.meta.url);

/** 认领标记标签。 */
export const CLAIM_LABEL = 'in-progress';

/** 撞车告警评论的隐藏键（幂等用）。 */
export const COLLISION_MARKER = 'claim-collision-alert';

/**
 * 纯判据：给定「该 issue 当前被几个 open PR 关联」与标签现状，决定动作。
 *
 * @param {object} input
 * @param {number} input.openPrCount 关联该 issue 的 open PR 数
 * @param {boolean} input.hasLabel 该 issue 现在有没有 `in-progress`
 * @param {'opened'|'closed'} input.event 触发的 PR 事件
 * @returns {{label: 'add'|'remove'|'none', collision: boolean, reason: string}}
 */
export function decideClaim({ openPrCount, hasLabel, event }) {
  const n = Number(openPrCount);
  if (!Number.isFinite(n) || n < 0) {
    // 取数失败时**什么都不做**。认领标记错了的代价是挡住别人或误导别人，
    // 比「暂时没标记」更糟——这与容量守卫「取数失败判红」的取向相反，是刻意的：
    // 容量守卫报错只是让 owner 白做一次减法，这里报错会让别人误判卡被占用。
    return { label: 'none', collision: false, reason: '取数失败：不做任何改动，避免误标占用状态' };
  }

  const collision = n >= 2;

  if (event === 'closed') {
    // 关闭：只要还有别的 open PR 关联，就保持占用标记
    if (n > 0) {
      return { label: 'none', collision, reason: `仍有 ${n} 个 open PR 关联，保持占用标记` };
    }
    return hasLabel
      ? { label: 'remove', collision: false, reason: '已无 open PR 关联，摘掉占用标记' }
      : { label: 'none', collision: false, reason: '已无 open PR 关联且本就无标记' };
  }

  // opened：有 PR 就该标记
  if (n > 0 && !hasLabel) {
    return { label: 'add', collision, reason: `有 ${n} 个 open PR 关联，打上占用标记` };
  }
  if (n > 0 && hasLabel) {
    return { label: 'none', collision, reason: '已有占用标记（幂等）' };
  }
  return { label: 'none', collision: false, reason: '无 open PR 关联' };
}

/**
 * 从 PR 正文解析关联的 issue 编号。
 *
 * 复用 `scripts/close_linked_issues.js` 的 `parseClosingKeywords`（**单一来源**），
 * 再补一层「非 closing 的显式关联」（`关联 #N` / `Refs #N` / 行内代码 `` `#N` ``）——
 * 很多 PR 只是顺带引用某张卡而并不关闭它，那同样构成「有人在做」。
 *
 * 只认**挂源形态**的 GitHub 编号，不猜分支名里的数字（双端编号是两个独立空间）。
 *
 * @param {string} body PR 正文
 * @returns {number[]} 去重后的 issue 编号
 */
export function parseLinkedIssues(body, repo = process.env.GITHUB_REPOSITORY) {
  const { parseClosingKeywords } = require('./close_linked_issues.js');
  const out = new Set();

  // 注意返回形状是 `{ numbers, crossRepo, self }` 而不是数组——
  // 早期版本按数组解开，得到 `undefined is not iterable`，且**只在有正文时才炸**，
  // 于是守卫在真实 PR 上静默失效。这里显式取 `.numbers`，并用 Array 兜住。
  const parsed = parseClosingKeywords(body || '', {}) || {};
  const closing = Array.isArray(parsed.numbers) ? parsed.numbers : [];
  for (const n of closing) if (Number.isFinite(Number(n))) out.add(Number(n));

  // 显式关联但非 closing 的写法
  const text = String(body || '');
  // 「关联 `GitHub #2406`」这种带挂源前缀 + 行内代码的写法是最常见形态，
  // 早期正则不允许中间出现 `GitHub` / 反引号，直接漏掉 ⇒ 守卫对真实 PR 静默失效。
  const re = /(?:关联|相关|参见|见|Refs?|Ref\b|Part\s+of|Towards?)\s*[：:]?\s*`?\s*(?:GitHub|GH)?\s*#(\d+)/gi;
  let m;
  while ((m = re.exec(text)) !== null) out.add(Number(m[1]));

  // 行内代码的裸编号 `` `#N` ``（挂源形态之一，见 guard_cross_repo_refs）
  const inline = text.match(/`#[0-9]+`/g) || [];
  for (const t of inline) out.add(Number(t.replace(/[^0-9]/g, '')));

  // 限仓形态 `owner/repo#N`（本仓 PR 正文里最常见的挂源写法）。
  // 注意**必须校验前缀是本仓**：引用别仓的卡不构成「本仓这张卡有人在做」，
  // 双端编号是两个独立空间，不加校验会把 CNB 的 #N 也认领过来。
  if (repo) {
    const own = String(repo).toLowerCase();
    const re2 = /([A-Za-z0-9._-]+)\/([A-Za-z0-9._-]+)#(\d+)/g;
    let m2;
    while ((m2 = re2.exec(text)) !== null) {
      if (`${m2[1]}/${m2[2]}`.toLowerCase() === own) out.add(Number(m2[3]));
    }
  }

  return [...out].filter((n) => Number.isFinite(n) && n > 0).sort((a, b) => a - b);
}

/** 取当前 open 且关联该 issue 的 PR 数（只看本仓库）。 */
export function countOpenPrsForIssue(issue, repo = process.env.GITHUB_REPOSITORY, excludePr = null) {
  if (!repo) throw new Error('缺少 GITHUB_REPOSITORY（或 --repo）');
  // 不用 shell:true 与 --jq：Windows 下 shell:true 会把 jq 表达式交给 cmd 解析而静默失败。
  const out = execFileSync(
    'gh',
    ['pr', 'list', '--repo', repo, '--state', 'open', '--limit', '200', '--json', 'number,body'],
    { encoding: 'utf8', maxBuffer: 32 * 1024 * 1024 },
  );
  const arr = JSON.parse(out || '[]');
  if (!Array.isArray(arr)) return 0;
  return arr.filter(
    (pr) => pr.number !== Number(excludePr) && parseLinkedIssues(pr.body || '').includes(Number(issue)),
  ).length;
}

function parseArgs(argv) {
  const opts = { json: false, repo: process.env.GITHUB_REPOSITORY };
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (a === '--json') opts.json = true;
    else if (a === '--pr') opts.pr = Number(argv[++i]);
    else if (a === '--event') opts.event = argv[++i];
    else if (a === '--repo') opts.repo = argv[++i];
  }
  return opts;
}

async function main() {
  const opts = parseArgs(process.argv.slice(2));
  if (!opts.pr || !opts.event) {
    console.error('用法：node scripts/claim_in_progress.mjs --pr N --event opened|closed');
    process.exit(2);
  }

  const body = execFileSync('gh', ['pr', 'view', String(opts.pr), '--repo', opts.repo, '--json', 'body', '--jq', '.body'], {
    encoding: 'utf8',
  });
  const issues = parseLinkedIssues(body);
  const results = [];

  for (const n of issues) {
    let openCount = 0;
    let hasLabel = false;
    try {
      // 关闭事件下要把自己排除掉（自己已经关了，不算「还有 PR 在做」）
      openCount =
        countOpenPrsForIssue(n, opts.repo, opts.event === 'closed' ? opts.pr : null) +
        (opts.event === 'closed' ? 0 : 0);
      const labels = execFileSync('gh', ['issue', 'view', String(n), '--repo', opts.repo, '--json', 'labels', '--jq', '[.labels[].name] | join(",")'], {
        encoding: 'utf8',
      });
      hasLabel = String(labels).split(',').includes(CLAIM_LABEL);
    } catch (err) {
      results.push({ issue: n, ...decideClaim({ openPrCount: NaN, hasLabel: false, event: opts.event }), error: String(err.message || err) });
      continue;
    }

    const verdict = decideClaim({ openPrCount: openCount, hasLabel, event: opts.event });

    if (verdict.label === 'add') {
      try {
        execFileSync('gh', ['issue', 'edit', String(n), '--repo', opts.repo, '--add-label', CLAIM_LABEL], { encoding: 'utf8' });
      } catch (err) {
        verdict.error = String(err.message || err);
      }
    } else if (verdict.label === 'remove') {
      try {
        execFileSync('gh', ['issue', 'edit', String(n), '--repo', opts.repo, '--remove-label', CLAIM_LABEL], { encoding: 'utf8' });
      } catch (err) {
        verdict.error = String(err.message || err);
      }
    }

    // 撞车告警：写进 issue 评论，双方共享的视角。幂等由隐藏键保证。
    if (verdict.collision) {
      try {
        const existing = execFileSync(
          'gh',
          ['issue', 'view', String(n), '--repo', opts.repo, '--json', 'comments', '--jq', `[.comments[] | select(.body | test("${COLLISION_MARKER}"))] | length`],
          { encoding: 'utf8', maxBuffer: 16 * 1024 * 1024 },
        );
        if (String(existing).trim() === '0') {
          const md = [
            `<!-- ${COLLISION_MARKER} -->`,
            `⚠️ **检测到撞车**：当前有 **${openCount} 个 open PR** 同时关联本卡。`,
            '',
            '并行 agent / 会话各自只看得到自己那一半，所以这条提醒写在**共享的 issue** 上，',
            '好让双方都能看见。请**先协调再继续**，避免两套解法合并时冲突。',
            '',
            '查看是谁在做：',
            '',
            '```bash',
            `gh pr list --repo ${opts.repo} --state open --search "${n}"`,
            '```',
            '',
            `注：本提醒由 \`scripts/claim_in_progress.mjs\` 自动发出，卡上的 \`${CLAIM_LABEL}\` 标签同样由它维护。`,
          ].join('\n');
          execFileSync('gh', ['issue', 'comment', String(n), '--repo', opts.repo, '--body', md], { encoding: 'utf8' });
          verdict.commentPosted = true;
        } else {
          verdict.commentPosted = false;
        }
      } catch (err) {
        verdict.error = String(err.message || err);
      }
    }

    results.push({ issue: n, ...verdict });
  }

  if (opts.json) console.log(JSON.stringify({ pr: opts.pr, event: opts.event, issues, results }));
  else for (const r of results) console.log(`#${r.issue}: label=${r.label} collision=${r.collision} — ${r.reason}`);

  // 撞车不阻断：阻止会惩罚先动手的人，我们要的是「可发现」不是「禁止」。
  process.exit(0);
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  main();
}
