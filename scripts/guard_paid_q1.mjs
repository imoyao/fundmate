#!/usr/bin/env node
/**
 * 付费卡禁挂 Q1-RED 守卫。
 *
 * ## WHY（源：2026-10-19 预算守卫逼出来的判据）
 *
 * AGENTS.md 里写着一条规则：**付费相关卡一律不得挂 `Q1-RED`**（唯一例外 `#2324`）。
 * 但 2026-10-19 实测发现 `#1288`（付费前端软拦截）既带 `Q1-RED`、又挂在
 * `M1 付费验证 #4` —— **规则与既有数据冲突，且没有任何机器会发现它**。
 *
 * 这条规则能长期空转，正是本轮治理反复出现的失效形态：
 * **规则写进文档，但没有判据 ⇒ 违反时无人知晓。**
 *
 * 直接触发本脚本的是预算守卫 `guard_rule_registry.py`：我往 AGENTS.md 加文字后，
 * 「无判据的硬约束条目」94 > 预算 88 被判红，提示
 * 「新加一条纯文字规则，就得先给它写守卫（预算只减不增）」。
 * 于是这条规则从纯文字升级为机器判据——**守卫逼出了守卫**，这个连锁是设计意图。
 *
 * ## 判据
 *
 * 一张 open issue 若同时满足：
 *   1. 带 `Q1-RED` 标签；
 *   2. 里程碑属于**付费里程碑集合**（默认 `M1 付费验证 Paid Validation`）；
 *   3. 不在例外白名单里（默认 `#2324`）；
 *
 * 则判定为「付费卡违规占用 NOW 档位」。
 *
 * 判据只吃这三样，全是 API 上的客观字段，不涉及「这张卡重不重要」——
 * 那是 owner 的判断（已提 `#2416` 请其裁定 A 摘标签 / B 开例外）。
 *
 * ## 为什么当前是「报告」而不是「阻断」
 *
 * 首次上线时违规项**已经存在**（`#1288`），且**不是 PR 作者能修的**——
 * 修它要改的不是代码而是 owner 的优先级判断。立刻阻断会让此后每个 PR 都红，
 * 而红灯归因不到 PR 作者 ⇒ 又变成「天天响的假信号」（#1434 同构失效）。
 *
 * 故当前形态：**违规项报出 + 退出码 0**，并在输出里指向裁定卡。
 * 待 owner 在 `#2416` 裁定后（摘标签或登记例外），本守卫转阻断（改 `BLOCKING = true`）。
 *
 * ## 用法
 *
 *     node scripts/guard_paid_q1.mjs                # 报告
 *     node scripts/guard_paid_q1.mjs --json
 *     node scripts/guard_paid_q1.mjs --repo imoyao/fundmate
 *
 * 回归网见 `scripts/tests/guard_paid_q1.test.js`。
 */

import { execFileSync } from 'node:child_process';
import { pathToFileURL } from 'node:url';

/** 付费里程碑：挂在这些里程碑上的卡不得占用 NOW 档位。 */
export const PAID_MILESTONES = ['M1 付费验证 Paid Validation'];

/** 例外白名单：owner 显式批准的付费卡可挂 Q1（须在 AGENTS.md 写明理由）。 */
export const ALLOWED_EXCEPTIONS = [2324];

export const Q1 = 'Q1-RED';

/** 是否转为阻断。owner 裁定 `#2416` 之后改 true。 */
export const BLOCKING = false;

/**
 * 纯判据：给一张卡的（里程碑、标签、编号），判定是否违规。
 *
 * @param {{milestone?: string|null, hasQ1: boolean, number: number}} card
 * @returns {{violation: boolean, reason: string}}
 */
export function checkCard(card) {
  const { milestone, hasQ1, number } = card || {};
  if (!hasQ1) return { violation: false, reason: '不带 Q1-RED' };
  if (ALLOWED_EXCEPTIONS.includes(Number(number))) {
    return { violation: false, reason: `#${number} 在例外白名单内（owner 已批准）` };
  }
  if (milestone && PAID_MILESTONES.includes(milestone)) {
    return { violation: true, reason: `#${number} 挂在付费里程碑「${milestone}」却占用 NOW 档位` };
  }
  return { violation: false, reason: '里程碑不属于付费集合' };
}

/** 取当前 open 且带 Q1-RED 的卡（含里程碑）。 */
export function fetchQ1Cards(repo = process.env.GITHUB_REPOSITORY) {
  if (!repo) throw new Error('缺少 GITHUB_REPOSITORY（或 --repo）');
  const out = execFileSync(
    'gh',
    ['issue', 'list', '--repo', repo, '--label', Q1, '--state', 'open', '--limit', '200', '--json', 'number,title,milestone'],
    { encoding: 'utf8', maxBuffer: 32 * 1024 * 1024 },
  );
  const arr = JSON.parse(out || '[]');
  if (!Array.isArray(arr)) return [];
  return arr.map((it) => ({
    number: it.number,
    title: it.title,
    milestone: it.milestone ? it.milestone.title : null,
  }));
}

function parseArgs(argv) {
  const opts = { json: false, repo: process.env.GITHUB_REPOSITORY };
  for (let i = 0; i < argv.length; i++) {
    if (argv[i] === '--json') opts.json = true;
    else if (argv[i] === '--repo') opts.repo = argv[++i];
  }
  return opts;
}

async function main() {
  const opts = parseArgs(process.argv.slice(2));
  let cards;
  try {
    cards = await fetchQ1Cards(opts.repo);
  } catch (err) {
    console.error(`::error::取数失败：${err.message || err}`);
    process.exit(1);
  }

  const hits = cards
    .map((c) => ({ ...c, ...checkCard({ milestone: c.milestone, hasQ1: true, number: c.number }) }))
    .filter((c) => c.violation);

  if (opts.json) {
    console.log(JSON.stringify({ checked: cards.length, violations: hits, blocking: BLOCKING }));
  } else if (hits.length === 0) {
    console.log(`OK：${cards.length} 张 open Q1-RED 卡，无付费卡违规占用。`);
  } else {
    console.error(`发现 ${hits.length} 张付费卡违规占用 NOW 档位：`);
    for (const h of hits) console.error(`  - #${h.number} ${h.title}（${h.milestone}）`);
    console.error('');
    console.error('处置见 `imoyao/fundmate#2416`（待 owner 裁定：A 摘标签 / B 登记例外）。');
    console.error(`当前为报告模式（BLOCKING=${BLOCKING}）；owner 裁定后转阻断。`);
  }

  process.exit(BLOCKING && hits.length > 0 ? 1 : 0);
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  main();
}
