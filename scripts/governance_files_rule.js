/**
 * 治理文件的**改动方向**判据（源 CNB #269 / #450，2026-10-14）。
 *
 * ## WHY 有这份文件
 *
 * 跨仓 `dev` 分叉反复复发的**结构性根因**：CNB 侧与 GitHub 侧**同时改同一批治理文件**。
 * 实测（2026-10-14，`git merge` 真实冲突面）：
 *
 *     .cnb.yml                                  ← 两边都改
 *     AGENTS.md                                 ← 两边都改
 *     docs/dev/github-cnb-mirror.md             ← 两边都改
 *     scripts/bridge/check_branch_divergence.py ← 两边都改
 *     backend/tests/test_branch_divergence_check.py ← 两边都改
 *
 * 5 个文件、16 处冲突。<此前一次是 25 个文件>。**这不是运气差，是「两边都往同一批文件里写」
 * 的必然结果**——只要这个条件成立，每次收敛完都会再撞一次（AGENTS.md §19「收敛是动作不是状态」）。
 *
 * 故立一条口径（B+C 里的 C）：
 *
 *     **治理文件只在 CNB 侧改**；GitHub 侧不再直接动它们。
 *
 * 这条口径把冲突面从「5 文件 16 处」收敛到**零**——此后 CNB → GitHub 的 push 才是快进。
 *
 * ## 判据
 *
 * 一条 PR 若**改动**了治理文件清单里的任一文件 ⇒ 判为「需要人工确认方向」。
 *
 * ⚠️ **本判据是「提示」不是「阻断」**（有意为之）：
 *    - 治理文件**确实**有时候要从 GitHub 侧改（比如 GitHub 独有的 workflow 需要同步调整）；
 *    - 把它做成阻断，就等于制造**第二条死锁**——想改的人被拦住，只能绕过，反而更糟。
 * 故它只报出来，由人确认「这批改动是不是该在 CNB 侧改」。
 *
 * ## 边界
 *
 * - **纯离线**：输入是调用方给的「改动文件列表」，不拉网络、不读 git；
 * - **不判内容**：只看路径，不看改了什么（判断「该不该这样改」是人的事）；
 * - 清单是显式的、可扩的：新增治理文件时把它加进来即可。
 */

'use strict';

/**
 * 治理文件清单：这些文件的改动会与 CNB 侧撞冲突面。
 * 判据不是「文件重不重要」，而是「**两侧是否都会改它**」——会，就进这个清单。
 */
const GOVERNANCE_FILES = [
  '.cnb.yml',
  'AGENTS.md',
  'docs/dev/github-cnb-mirror.md',
  'scripts/bridge/check_branch_divergence.py',
  'backend/tests/test_branch_divergence_check.py',
];

/** 去掉 `./` 前缀并统一分隔符，便于两边混用写法。 */
function normalizePath(p) {
  if (typeof p !== 'string') return '';
  return p.replace(/^\.\//, '').replace(/\\/g, '/').trim();
}

/**
 * 从改动文件列表里挑出治理文件。
 *
 * @param {string[]} files 形如 `['src/a.ts', '.cnb.yml']`
 * @returns {string[]} 命中的治理文件（去重、保持清单顺序）
 */
function findGovernanceHits(files) {
  const set = new Set((files || []).map(normalizePath));
  return GOVERNANCE_FILES.filter((f) => set.has(f));
}

/**
 * 判定一条 PR 的改动方向。
 *
 * @param {{number?: number|string, files?: string[]}} pull
 * @returns {{ok: boolean, hits: string[], reason: string}}
 */
function checkGovernanceDirection(pull) {
  const number = (pull && pull.number) || '?';
  const hits = findGovernanceHits(pull && pull.files);
  if (hits.length === 0) {
    return { ok: true, hits, reason: `PR #${number} 未改动治理文件，通过` };
  }
  return {
    ok: false,
    hits,
    reason:
      `PR #${number} 改动了 ${hits.length} 个治理文件：${hits.join(' / ')}。` +
      `按口径「治理文件只在 CNB 侧改」，请确认这批改动是否该改在 CNB 侧；` +
      `若确需在 GitHub 侧改（GitHub 独有上下文），请在本 PR 说明理由后放行。`,
  };
}

module.exports = { GOVERNANCE_FILES, normalizePath, findGovernanceHits, checkGovernanceDirection };
