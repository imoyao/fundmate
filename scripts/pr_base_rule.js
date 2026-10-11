/**
 * 分支 base 判据（源 CNB #123）：**功能分支 PR 一律 base=`dev`，只有发版 PR 用 `main`**。
 *
 * ## WHY 有这份文件
 *
 * CNB #123 的质问是「提 PR 到底提到 dev 还是 main，必须固定下来，你现在这么随意提」。
 * 事实核查后：不是「随意」，而是**规范只写了「功能分支 base=dev」，从没写「什么时候允许
 * base=main」**——于是「这改动要尽快生效 / 它要跑 cron」就成了每个人各自的理由。代价是
 * 实测已发生：CNB 侧 `main` 与 `dev` **互不包含**（`main` 独有 6 个提交、`dev` 独有 10 个），
 * 镜像链路「改的代码在 dev、会被执行的代码在 main」，两边结论相反。
 *
 * 把判据机械化的意义：**base 对不对是可以算的，不是可以商量的。**
 * 只靠文档写「禁止」不够（AGENTS.md 早就写了「功能分支合入目标一律是 dev」，
 * 依然连续多个 PR 用 main）——要有一个能在 CI 上跑、对**真实 PR 列表**出结论的检查。
 *
 * ## 判据
 *
 * 一条 PR 的 base 是 `main` **当且仅当**它是发版 PR：head 就是 `dev` 本身。
 * 其余任何情况（head 是 `feat/*` / `fix/*` / `docs/*` / 任何非 `dev` 分支）base 必须是 `dev`。
 *
 * ## 边界（刻意的）
 *
 * - **不判「该不该发版」**：发版频率是人的判断，本脚本只判 base 与 head 是否自洽；
 * - **不联网**：输入是调用方给的 PR 记录数组，便于离线测试与复用；
 * - **白名单是显式且需留痕的**：历史误提已发生，豁免必须写成一条带原因与来源的记录，
 *   不允许「反正它是历史」这类理由。
 *
 * ## 怎么跑
 *
 *     node --test "scripts/tests/*.test.js"       # 或根目录 `pnpm test:scripts`
 *     node scripts/pr_base_rule.js               # 打印判据说明与当前白名单
 */

'use strict';

/** 集成分支：功能分支 PR 的唯一合法 base。 */
const INTEGRATION_BRANCH = 'dev';

/** 稳定分支：只有发版 PR（head === dev）可以用它当 base。 */
const RELEASE_BRANCH = 'main';

/** 去掉 `refs/heads/` 前缀，便于混用两种写法。 */
function normalizeRef(ref) {
  if (typeof ref !== 'string') return '';
  return ref.replace(/^refs\/heads\//, '').trim();
}

/** head 是不是 `dev` 本身 —— 这是「发版 PR」的唯一定义。 */
function isReleasePull(head) {
  return normalizeRef(head) === INTEGRATION_BRANCH;
}

/**
 * 检查单条 PR 的 base 是否合规。
 *
 * @returns {{ok: boolean, reason: string, expectedBase: string}}
 */
function checkPullBase(pull) {
  const base = normalizeRef(pull && pull.base);
  const head = normalizeRef(pull && pull.head);
  const number = (pull && pull.number) || '?';

  if (!base || !head) {
    return { ok: false, reason: `PR #${number} 缺少 base 或 head，无法判定`, expectedBase: INTEGRATION_BRANCH };
  }

  if (base === INTEGRATION_BRANCH) {
    return { ok: true, reason: `PR #${number} base=dev，合规`, expectedBase: INTEGRATION_BRANCH };
  }

  if (base === RELEASE_BRANCH) {
    if (isReleasePull(head)) {
      return { ok: true, reason: `PR #${number} 是发版 PR（dev → main），合规`, expectedBase: RELEASE_BRANCH };
    }
    return {
      ok: false,
      expectedBase: INTEGRATION_BRANCH,
      reason:
        `PR #${number} base=main 但 head=${head}（不是 dev）——` +
        `只有「head 就是 dev」的发版 PR 才允许 base=main。` +
        `功能分支请改指 dev；若这批改动确实该生效，另开一张 dev→main 的发布 PR。`,
    };
  }

  return {
    ok: false,
    expectedBase: INTEGRATION_BRANCH,
    reason: `PR #${number} base=${base} 不是合法目标分支（只允许 dev 或 main）`,
  };
}

/**
 * 批量检查；返回违规项列表（空数组 = 全绿）。
 *
 * @param {Array} pulls 形如 `[{number, base, head}]`
 * @param {object} [opts]
 * @param {number[]} [opts.exemptNumbers] 显式豁免的 PR 编号（历史误提，需留痕）
 */
function findBaseViolations(pulls, opts) {
  const exempt = new Set((opts && opts.exemptNumbers) || []);
  const out = [];
  for (const pull of pulls || []) {
    const num = Number((pull && pull.number) || 0);
    if (exempt.has(num)) continue;
    const res = checkPullBase(pull);
    if (!res.ok) out.push({ number: num, base: normalizeRef(pull.base), head: normalizeRef(pull.head), reason: res.reason });
  }
  return out;
}

/**
 * 历史误提的显式白名单。**每条都要有原因与来源**，不允许「反正它是历史」。
 *
 * 这些 PR 的 base 确实是 `main` 而 head 不是 `dev`（违反本判据），但已合并、不可追改；
 * 登记在此是为了让「当前违规数」这个数字有意义——新出现的违规必须立刻处理。
 */
const KNOWN_HISTORICAL_VIOLATIONS = [
  { number: 114, reason: 'GitHub→CNB 建卡脚本首版，误以 main 为 base（CNB #123 实测）' },
  { number: 122, reason: '镜像卡快照声明 PR，误以 main 为 base（CNB #123 实测）' },
  { number: 124, reason: '镜像卡更正台账 PR，误以 main 为 base（CNB #123 实测）' },
  { number: 126, reason: '镜像路线决策文档 PR，误以 main 为 base（CNB #123 实测）' },
];

module.exports = {
  INTEGRATION_BRANCH,
  RELEASE_BRANCH,
  normalizeRef,
  isReleasePull,
  checkPullBase,
  findBaseViolations,
  KNOWN_HISTORICAL_VIOLATIONS,
};

// 直接执行时打印判据说明（`node scripts/pr_base_rule.js`）。
if (require.main === module) {
  console.log('PR base 判据（CNB #123）');
  console.log(`  功能 / 文档分支 PR → base=${INTEGRATION_BRANCH}（默认）`);
  console.log(`  发版 PR（head=${INTEGRATION_BRANCH}）→ base=${RELEASE_BRANCH}`);
  console.log(`  其余一律违规。`);
  console.log('\n已登记的历史误提（豁免，不代表合规）：');
  for (const item of KNOWN_HISTORICAL_VIOLATIONS) {
    console.log(`  #${item.number}  ${item.reason}`);
  }
}
