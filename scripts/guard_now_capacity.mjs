#!/usr/bin/env node
/**
 * NOW 超额记账：Q1-RED 存量超上限时给每张 Q1 卡打「NOW-超额」标签，回落时自动撤掉。
 *
 * ## WHY 是「记账」而不是「拦截」（这一段是本守卫的设计核心）
 *
 * ## 1、上一版写错了对象
 *
 * 上一版守卫（已删）判据是「Q1 标签挂载时间晚于 PR 创建时间」，本意是拦「PR 里给卡提优先级」。
 * 但把它的判据摊开看，它实际只拦一个极窄动作，而**完全拦不住真正的目标场景**：
 *
 *   - 新建一张 Q1 issue → 标签挂在 PR 之前（往往还没有 PR）→ **放行**
 *   - 推进一张既有 Q1 卡 → 标签早于 PR → **放行**
 *
 * 也就是说，它看起来像档位闸门，实际对「又提了一张紧急卡」完全不设防。
 * **一个看起来像闸门、实际不设防的东西比没有闸门更糟**——因为你会以为这里有闸门，
 * 于是把注意力放在别处（真实案例：owner 问「那我紧急问题该怎么登记」时，
 * 答案是「随便提，守卫不管」，而守卫的存在本身是误导）。
 *
 * ## 2、为什么拦截本身是错的设计
 *
 * 假设拦截真的做对了（拦住第 6 张 Q1），会发生什么：
 *
 *   发现生产事故 → 登记 → 被守卫拦住 → 「Q1 满了，先关一张再提」
 *
 * 这时候要关的那一张，只能是「先关掉另一张同样紧急的」。于是唯一的出路是
 * **owner 在紧急时刻做资源排序决策**，而且必须当场做。
 * 更糟的是它会诱发绕行：AI 会「先提普通卡、再补 Q1 标签」或「拆成两张卡」，
 * 于是数据变脏而闸门形同虚设。
 *
 * **紧急性不是可以用配额排队的东西。** 容量上限如果挂在登记环节，
 * 惩罚的是做正确动作的人。所以登记必须零摩擦——这与用户的既有习惯一致
 * （发现就记到 GitHub issue），不需要改。
 *
 * ## 3、那容量上限还有什么用
 *
 * 它的作用不是「限制新增」，而是「**让超容状态持续可见，直到被还清**」。
 * 具体形态是给存量 Q1 卡打一个 `NOW-超额` 标签：
 *
 *   - 超容时：每张 open Q1-RED 卡自动带 `NOW-超额`，看板上一眼看出「现在超了」；
 *   - 回落时（有人摘掉/完成一张 Q1）：**自动撤掉**标签，不需要谁记得去清。
 *
 * 三个性质是刻意的：
 *   1. **零摩擦**：登记新紧急卡不需要先还债；
 *   2. **绑定到卡**：超容不是一个匿名数字，而是每张卡上看得见的标记；
 *   3. **自动结清**：容量回到上限内就自动干净，不留「记得清一下」的维护债。
 *
 * 顺带一个好处：Q1 卡上出现 `NOW-超额` 恰好是一个**客观的排序提示**——
 * 在超容期间，先动哪张卡是 owner 的决定，但「全都超着」这件事不再需要记忆。
 *
 * ## 4、谁该还这笔债
 *
 * 一次扫描（issue-health-scan / 人工看板巡检）时，按「最近有没有动过」决定降级谁。
 * **不要求 owner 主动记得**——记忆是最不可靠的一环，本轮治理已经吃过一次亏：
 * 月度复查写进 AGENTS.md 没人执行，最后是靠一条 CI 判据才立住。
 *
 * ## 用法
 *
 *     node scripts/guard_now_capacity.mjs --apply --repo imoyao/fundmate
 *
 * `--apply` 会实际增删标签（需 `issues: write`）；不加 `--apply` 只打印将要做什么（dry-run，默认）。
 *
 * 退出码：dry-run 时若当前超容返回 1（便于 CI 观察，但不阻断）；`--apply` 成功后恒为 0
 * ——**刻意不阻断**，理由见 §2。
 *
 * 回归网见 `scripts/tests/guard_now_capacity.test.js`。
 */

import { execFileSync } from 'node:child_process';
import { pathToFileURL } from 'node:url';
import { createRequire } from 'node:module';

const require = createRequire(import.meta.url);

/** 默认上限：与 AGENTS.md 的 Q1 漂移阈值一致，改这里必须同步改那份文档。 */
export const DEFAULT_LIMIT = 5;

/** 超额标记标签：容量超限时挂在每张 open Q1-RED 卡上。 */
export const OVERFLOW_LABEL = 'NOW-超额';

export const Q1_LABEL = 'Q1-RED';

/**
 * 纯判据：给定 open Q1 数量与上限，返回结论。
 *
 * 抽成纯函数是为了能测。守卫的危险不在「算错」，而在**判据被改松**——
 * 所以测试里除了正例，还必须钉住「超容量必须报红」这个反向用例（证伪探针）。
 *
 * @param {number} openQ1Count open 且带 Q1-RED 的 issue 数
 * @param {number} [limit=DEFAULT_LIMIT]
 * @returns {{ok: boolean, count: number, limit: number, message: string}}
 */
export function evaluateCapacity(openQ1Count, limit = DEFAULT_LIMIT) {
  const n = Number(openQ1Count);
  const lim = Number(limit);

  if (!Number.isFinite(n) || n < 0) {
    // 取数失败时**不放行也不报红**：红灯要能指认问题，报「未知」比报「超容」诚实。
    return {
      ok: false,
      count: n,
      limit: lim,
      message: `Q1-RED 计数非法（count=${openQ1Count}），取数失败，判红以免静默放行。`,
    };
  }

  if (n > lim) {
    return {
      ok: false,
      count: n,
      limit: lim,
      message:
        `NOW 档位（Q1-RED）已超容量：当前 ${n} 张 open，上限 ${lim} 张。\n` +
        `**这不阻塞登记**——发现紧急问题请直接提卡挂 \`${Q1_LABEL}\`，不要先还债。\n` +
        `超额期间每张 Q1 卡会自动带 \`${OVERFLOW_LABEL}\` 标签；\n` +
        `还债方式：完成或摘掉其中一张，标签会自动撤掉。判据见 scripts/guard_now_capacity.mjs。`,
    };
  }

  return {
    ok: true,
    count: n,
    limit: lim,
    message: `NOW 档位容量正常：${n}/${lim} 张 open Q1-RED。`,
  };
}

/**
 * 纯判据：给定容量结论与每张卡的现状，算出每张卡该加还是该撤超额标签。
 *
 * 这是本守卫真正落地的那一步，必须能脱离网络测——所以它只吃纯数据。
 *
 * @param {{count: number, limit: number}} capacity evaluateCapacity 的返回（不含 message）
 * @param {Array<{number: number, hasOverflow: boolean}>} cards 全部 open Q1-RED 卡
 * @returns {{overCapacity: boolean, toLabel: number[], toUnlabel: number[]}}
 */
export function planOverflowLabels(capacity, cards) {
  const over = Number(capacity.count) > Number(capacity.limit);
  const toLabel = [];
  const toUnlabel = [];
  for (const card of cards || []) {
    if (over && !card.hasOverflow) toLabel.push(card.number);
    else if (!over && card.hasOverflow) toUnlabel.push(card.number);
  }
  return { overCapacity: over, toLabel, toUnlabel };
}

/** 取全部 open Q1-RED 卡（含是否已带超额标签）。 */
export async function fetchOpenQ1Cards(repo = process.env.GITHUB_REPOSITORY) {
  if (!repo) throw new Error('缺少 GITHUB_REPOSITORY（或 --repo）');
  // 不用 shell:true、不用 --jq：Windows 下 shell:true 会把 jq 表达式交给 cmd 解析而报
  // 「'select' 不是内部或外部命令」，取数静默失败 → 守卫入参变 NaN。
  // 这类「取数失败伪装成业务结论」的坑比直接报错难查得多。
  const out = execFileSync(
    'gh',
    [
      'issue',
      'list',
      '--repo',
      repo,
      '--label',
      Q1_LABEL,
      '--state',
      'open',
      '--limit',
      '200',
      '--json',
      'number,labels',
    ],
    { encoding: 'utf8', maxBuffer: 32 * 1024 * 1024 },
  );
  const arr = JSON.parse(out || '[]');
  if (!Array.isArray(arr)) return [];
  return arr.map((it) => ({
    number: it.number,
    hasOverflow: (it.labels || []).some((l) => l && l.name === OVERFLOW_LABEL),
  }));
}

function parseArgs(argv) {
  const opts = { limit: DEFAULT_LIMIT, json: false, apply: false, repo: process.env.GITHUB_REPOSITORY };
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (a === '--limit') opts.limit = Number(argv[++i]);
    else if (a === '--json') opts.json = true;
    else if (a === '--apply') opts.apply = true;
    else if (a === '--repo') opts.repo = argv[++i];
  }
  return opts;
}

async function main() {
  const opts = parseArgs(process.argv.slice(2));

  let cards;
  try {
    cards = await fetchOpenQ1Cards(opts.repo);
  } catch (err) {
    const verdict = evaluateCapacity(NaN, opts.limit);
    const msg = `::error::取数失败：${err.message || err}`;
    if (opts.json) console.log(JSON.stringify({ ...verdict, error: String(err.message || err) }));
    else console.error(msg);
    process.exit(1);
  }

  const verdict = evaluateCapacity(cards.length, opts.limit);
  const plan = planOverflowLabels({ count: cards.length, limit: opts.limit }, cards);

  const done = { labeled: [], unlabelled: [] };
  if (opts.apply) {
    for (const n of plan.toLabel) {
      try {
        execFileSync('gh', ['issue', 'edit', String(n), '--repo', opts.repo, '--add-label', OVERFLOW_LABEL], {
          encoding: 'utf8',
        });
        done.labeled.push(n);
      } catch (err) {
        console.error(`::error::给 #${n} 加 ${OVERFLOW_LABEL} 失败：${err.message || err}`);
      }
    }
    for (const n of plan.toUnlabel) {
      try {
        execFileSync('gh', ['issue', 'edit', String(n), '--repo', opts.repo, '--remove-label', OVERFLOW_LABEL], {
          encoding: 'utf8',
        });
        done.unlabelled.push(n);
      } catch (err) {
        console.error(`::error::给 #${n} 撤 ${OVERFLOW_LABEL} 失败：${err.message || err}`);
      }
    }
  }

  if (opts.json) {
    console.log(JSON.stringify({ ...verdict, plan, applied: opts.apply ? done : null }));
  } else {
    console.log(verdict.message);
    if (plan.overCapacity) {
      console.log(
        opts.apply
          ? `已加 ${OVERFLOW_LABEL}：${done.labeled.join(', ') || '（无）'}`
          : `[dry-run] 将加 ${OVERFLOW_LABEL}：${plan.toLabel.join(', ') || '（无）'}`,
      );
    } else {
      console.log(
        opts.apply
          ? `已撤 ${OVERFLOW_LABEL}：${done.unlabelled.join(', ') || '（无）'}`
          : `[dry-run] 将撤 ${OVERFLOW_LABEL}：${plan.toUnlabel.join(', ') || '（无）'}`,
      );
    }
    if (!opts.apply) console.log('（加 --apply 才实际增删标签）');
  }

  // 刻意不因超容而 exit 1：超容不是错误状态，是需要还的债。
  // 唯一非零退出的情况已在上面（取数失败）处理。
  process.exit(0);
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  // 不用 top-level await：guard_*.mjs 会被 CJS 测试用 require() 引入，
  // 带 TLA 的 ESM 图在 CJS 里 require 会直接抛 ERR_REQUIRE_ASYNC_MODULE。
  main();
}
