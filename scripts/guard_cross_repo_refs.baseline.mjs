/**
 * 跨仓引用守卫的**存量基线**（冻结于 2026-10-11）。
 *
 * 键 = `文件路径|行指纹`，**不是文件名** —— 这点是刻意的：只按文件冻结的话，
 * 一个已经脏了的文件里**新增**的裸引用会跟着蒙混过关。按行指纹冻结后，
 * 基线里没登记的新行一律阻断，无论它落在哪个文件。
 *
 * 为什么冻结而不是一次改完：上线时全仓 89 处命中，多数是误报形态
 * （上游项目名 `pytest #3221`、GitHub Project 编号 `Project #3`、历史文档的旧文风），
 * 一次性改完会把这次修复摊成 90 处无关 diff，评审反而看不清规则本身。
 *
 * 行文本被改动 → 指纹失效 → 该行重新变红。这是**期望行为**：改到那行时顺手挂源。
 * 守卫也会把已失效的条目列出来催你删档，避免基线长成「永远豁免」的垃圾桶。
 *
 * 重新生成：`node scripts/guard_cross_repo_refs.mjs --freeze`
 */
export const BASELINE_FILES = new Set([
'docs/bias-datasource-troubleshooting.md|af65802733a9',
  'docs/bias-datasource-troubleshooting.md|c8a2ecba7741',
  'docs/design/index.md|4811fac4b74a',
  'docs/dev/custome-restful.md|3548c8919ed6',
  'docs/dev/db-choice.md|6b230de66a4f',
  'docs/dev/flask-auth.md|43c302e832b6',
  'docs/dev/flask-auth.md|5e2cb0a180b9',
  'docs/dev/flask-auth.md|70176aeb7c86',
  'docs/dev/fund-portfolio.md|29bda6fedac0',
  'docs/dev/import-trade-records.md|34626837701a',
  'docs/dev/something-that-is-untested-is-broken.md|85f5a87800a5',
  'docs/dev/sqlalchemy-usage.md|a1f2b0d01c92',
  'docs/features/watchlist.md|60ca29c7ae8a',
  'docs/spec/decisions.md|0550f86efd2d',
  'docs/spec/decisions.md|3920f8315518',
  'docs/spec/decisions.md|7f3b6e291c89',
  'docs/spec/decisions.md|99d12a8705c1',
  'docs/spec/decisions.md|d20fc03a2e02',
  'docs/spec/decisions.md|da64dd2d5bce',
  'docs/spec/decisions.md|dbd2445db662',
  'docs/spec/importer-architecture.md|716d6a6a9c67',
  'docs/spec/launch-priority-baseline.md|4830ec2c1606',
  'docs/spec/roadmap.md|0a046dc589b8',
  'docs/spec/roadmap.md|15004e10d6b8',
  'docs/spec/roadmap.md|2458c7e6dacc',
  'docs/spec/roadmap.md|9470caf67966',
  'docs/spec/roadmap.md|b2739d32658c',
  'docs/spec/roadmap.md|cccf9e0721bc',
  'docs/spec/roadmap.md|d9c4dcf1de72',
  'docs/spec/tech-debt.md|4fda943ac39c',
  'docs/spec/tech-debt.md|fdeae4d83f50',
  'docs/working-notes/README.md|773138170554',
  'docs/working-notes/agent-dev-progress-2026-09-26.md|31859d351d08',
  'docs/working-notes/e-account-import-data-decentralization-plan-2026-08-16.md|501128050304',
  'docs/working-notes/e-account-import-data-decentralization-plan-2026-08-16.md|c8e537f506eb',
  'docs/working-notes/eastmoney-antiscrape-2026-08-05.md|af65802733a9',
  'docs/working-notes/eastmoney-antiscrape-2026-08-05.md|c8a2ecba7741',
  'docs/working-notes/issue-triage/triage-report.md|1ccb25646984',
  'docs/working-notes/mvp-launch-blockers-2026-08-18.md|047b29d5c392',
  'docs/working-notes/page-split-welcome-vs-panorama-2026-08-13.md|d1840a470f91',
  'docs/working-notes/sw-industry-source-plan-2026-09-14.md|fbfc4d84cee0',
  'docs/working-notes/unified-import-entry-evaluation-2026-08-16.md|152573433ffe',
  'docs/working-notes/unified-import-entry-evaluation-2026-08-16.md|2ca751449a6a',
  'docs/working-notes/unified-import-entry-evaluation-2026-08-16.md|3c98f12a4de0',
  'docs/working-notes/unified-import-entry-evaluation-2026-08-16.md|3fb64a882071',
  'docs/working-notes/unified-import-entry-evaluation-2026-08-16.md|5633cd72587e',
  'docs/working-notes/unified-import-entry-evaluation-2026-08-16.md|6be18e930888',
  'docs/working-notes/unified-import-entry-evaluation-2026-08-16.md|a8e21d4fab3d',
  'docs/working-notes/unified-import-entry-evaluation-2026-08-16.md|a9d621af6c59',
  'docs/working-notes/unified-import-entry-evaluation-2026-08-16.md|aca3b8c9479b',
  'docs/working-notes/worktile-migration-map-2026-08-09.md|7cefe3e83336',
  'scripts/tests/close_linked_issues.test.js|144dd11b3224',
  'scripts/tests/close_linked_issues.test.js|19d8bde80c29',
  'scripts/tests/close_linked_issues.test.js|caaa0787d297',
  'scripts/tests/close_linked_issues.test.js|f1f2edf5649f',
]);
