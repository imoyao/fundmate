/**
 * `scripts/release_readiness.py` 的回归用例。
 *
 * ## WHY 有这份文件
 *
 * 该脚本是 dev → main 发版的**机械闸**：它判 BLOCK 时会拦住发版，判ok 时会让
 * 「看起来可以发」。两种误判都很贵：
 *
 *   - **假阴性（漏放）**：main 有独有提交却判 ok → 发版 PR 带反向差异合进生产；
 *   - **假阳性（误拦）**：把完成态 PR 判成中间态 → 每周无谓停摆，且机械闸可信度归零
 *     （同issue-health-scan B 类教训：「有过合入 ≠ 验收达成」的误导口径）；
 *   - **口径误导**：报告把机械绿灯写成「可发版」→ 读者以为绿灯=能发，跳过语义复核。
 *
 * 2026-10-08 首版落地时已抓到两处真实误报（见下方用例 3 / 用例 4），本文件逐条钉住。
 *
 * ## 关键反例：为什么「占位」不在中间态信号词表里
 *
 * #1855「按方案 A 处置 views/account 死代码——删重复实现，两页降为占位」与
 * #1854「占位页去假数据」都含「占位」，但它们是**完成态**：刻意把废弃功能收敛成
 * 占位页就是交付结果。首版把「占位」列进信号词表，实跑立刻误伤这2 个 PR。
 * 信号词表里的每个词都要经得起「这卡是不是真的做了一半」的反问。
 *
 * ## 怎么跑
 *
 *     node --test "scripts/tests/*.test.js"     # 或根目录 `pnpm test:scripts`
 *
 * 零新依赖（只用 Node 内置 node:test / node:assert）。行为断言通过子进程调用 **真实**
 * Python 解释器跑 `release_readiness` 的纯函数，不在 JS 里复刻一份逻辑——复刻等于把
 * 被测逻辑抄一份，抄错的那份才是绿的。解释器探测走 `_python-interpreter.mjs`（唯一实现），
 * 找不到就抛错，**不 skip**（skip 在 node --test 里退出码仍为 0，等于门没关）。
 */

import assert from 'node:assert/strict';
import { test } from 'node:test';
import { spawnSync } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { pythonOrFail } from './_python-interpreter.mjs';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = path.resolve(__dirname, '..', '..');
const SRC = fs.readFileSync(path.join(REPO_ROOT, 'scripts', 'release_readiness.py'), 'utf8');

// ---------------------------------------------------------------------------
// Python 解释器：走 `_python-interpreter.mjs` 这份唯一实现
// ---------------------------------------------------------------------------

// 2026-11-02：本文件首版自带一份 `findPython()`，与仓库里其余 5 份拷贝同病——
// 而该收敛机制（#119 / 2026-10-24）在它丢失期间落地，于是它一恢复就被
// `guard_python_interpreter.test.js` 判红。改为接线共享模块，不再本地定义。
const PYTHON = pythonOrFail();
const PY_SNIPPET = `
import json, sys
sys.path.insert(0, r'scripts')
import release_readiness as m
print(json.dumps(eval(r"""__EXPR__"""), ensure_ascii=True, default=list))
`;

function py(expr) {
  const r = spawnSync(PYTHON[0], [...PYTHON.slice(1), '-c', PY_SNIPPET.replace('__EXPR__', expr)], {
    cwd: REPO_ROOT,
    encoding: 'utf8',
    maxBuffer: 8 * 1024 * 1024,
  });
  if (r.status !== 0) {
    throw new Error(`python 求值失败：${expr}\n${r.stderr || ''}`);
  }
  return JSON.parse(r.stdout.trim());
}

// 保留这个空 options 占位而不是直接删掉第三参：33 处调用都带着它。
// **刻意不提供 skip 分支**——解释器缺席时 `pythonOrFail()` 已在模块顶层抛错。
// skip 在 `node --test` 里既不算通过也不算失败、退出码仍为 0，等于这道门从未关过。
const behavioral = {};

// ---------------------------------------------------------------------------
// 项 1：main 有独有提交 → BLOCK（分叉是发版的硬前置）
// ---------------------------------------------------------------------------

test('classify_fork：main 领先 dev 一律 block', behavioral, () => {
  assert.equal(py(`m.classify_fork(300, 3)`), 'block', 'main 独有 3 个提交必须拦');
  assert.equal(py(`m.classify_fork(300, 1)`), 'block', '领先 1 个也要拦，不是「≥N 才拦」');
  assert.equal(py(`m.classify_fork(0, 5)`), 'block', '零领先但 main 独有，仍是分叉');
});

test('classify_fork：dev 领先 main（正常待发状态）→ ok', behavioral, () => {
  assert.equal(py(`m.classify_fork(300, 0)`), 'ok');
  assert.equal(py(`m.classify_fork(1, 0)`), 'ok', '只有一个提交待发也是合法状态');
  assert.equal(py(`m.classify_fork(0, 0)`), 'ok', '两条分支齐平，不需要发版');
});

// ---------------------------------------------------------------------------
// 项 2：反向验证 —— 把「behind 判据」去掉后必须转红
// ---------------------------------------------------------------------------

test('反向验证：classify_fork 一旦忽略 behind，分叉判定全部失效', behavioral, () => {
  // 反向验证：模拟「只按 ahead 判、忽略 behind」的旧实现
  const broken = (ahead, behind) => (ahead === 0 ? 'ok' : 'ok');
  assert.equal(broken(300, 3), 'ok', '旧实现会把分叉判成 ok —— 这正是要防的漏放');
  assert.notEqual(broken(300, 3), py(`m.classify_fork(300, 3)`), '新实现必须能拦住它');
});

// ---------------------------------------------------------------------------
// 项 3：中间态信号词 —— 含真实反例（#1855 / #1854 的「占位」是完成态）
// ---------------------------------------------------------------------------

test('中间态信号：标题自我声明未完成才命中', behavioral, () => {
  assert.equal(py(`m.is_intermediate_title('feat(x): WIP 骨架')`), true);
  assert.equal(py(`m.is_intermediate_title('feat(x): 中间态重构')`), true);
  assert.equal(py(`m.is_intermediate_title('fix(x): 分步实施')`), true);
  assert.equal(py(`m.is_intermediate_title('feat(x): 半成品接口')`), true);
  assert.equal(py(`m.is_intermediate_title('feat(x): 未完成的解析器')`), true);
});

test('中间态信号：「占位」是完成态，不得命中（#1855 / #1854 实证反例）', behavioral, () => {
  // 这两条都是已合入的完成态 PR，首版把「占位」列进信号词表后立刻误伤
  assert.equal(
    py(
      `m.is_intermediate_title(${JSON.stringify(
        'refactor(account): 按方案 A 处置 views/account 死代码——删重复实现，两页降为占位（#1840）',
      )})`,
    ),
    false,
    '#1855 含「降为占位」但是完成态，不该命中',
  );
  assert.equal(
    py(
      `m.is_intermediate_title(${JSON.stringify(
        'fix(frontend): 占位页去假数据、涨跌色归位、新增交互可达性守门（#1839 #1840 #1842）',
      )})`,
    ),
    false,
    '#1854 含「占位页去假数据」但是完成态，不该命中',
  );
  assert.ok(
    !SRC.includes("r'占位'"),
    '信号词表里不该再有裸的「占位」pattern —— 加回来这条测试就该转红',
  );
});

test('中间态信号：正常交付标题不得误伤', behavioral, () => {
  assert.equal(py(`m.is_intermediate_title('feat(a): 三视图 + 读路径提速')`), false);
  assert.equal(py(`m.is_intermediate_title('fix(b): 消除区间相关与真实盈亏消失')`), false);
  assert.equal(py(`m.is_intermediate_title('docs(c): 设计初稿')`), false);
  assert.equal(py(`m.is_intermediate_title(None)`), false, 'None 必须安全返回而非抛异常');
  assert.equal(py(`m.is_intermediate_title('')`), false);
});

test('中间态信号：wip 需词边界，避免误伤含 wip 子串的正常词', behavioral, () => {
  assert.equal(py(`m.is_intermediate_title('feat: swagger 文档补充')`), false);
  assert.equal(py(`m.is_intermediate_title('fix: 修复 swipe 手势')`), false);
  assert.equal(py(`m.is_intermediate_title('feat: WIP 骨架')`), true, '独立 WIP 仍应命中');
});

// ---------------------------------------------------------------------------
// 项 4：closing keyword 解析 —— base=main 时 GitHub 原生生效，写错就真关卡
// ---------------------------------------------------------------------------

test('closing keyword：九个关键字变体全部认（对齐 close_linked_issues.js D37）', behavioral, () => {
  // 回归点：首版把 close 系列写成 `clos(?:e[sd])?`，展开为 clos|close|closeds|closes，
  // **匹配不到 closed**。真源是 `close[sd]?`。这条用例钉住该形态。
  for (const kw of ['close', 'closes', 'closed', 'fix', 'fixes', 'fixed', 'resolve', 'resolves', 'resolved']) {
    assert.deepEqual(
      py(`sorted(m.closers_in('${kw} #42'))`),
      [42],
      `关键字 \`${kw}\` 必须命中（首版 closed 丢失）`,
    );
  }
  assert.deepEqual(py(`sorted(m.closers_in('close #5; closed #6; resolves #7'))`), [5, 6, 7]);
});

test('closing keyword：逗号列表全抓（首版只抓到第一个）', behavioral, () => {
  assert.deepEqual(py(`sorted(m.closers_in('Closes #1926, #1927'))`), [1926, 1927]);
  assert.deepEqual(py(`sorted(m.closers_in('Closes #1、#2、#3'))`), [1, 2, 3]);
  assert.deepEqual(py(`sorted(m.closers_in('Fixes #8,#9'))`), [8, 9]);
  assert.deepEqual(py(`sorted(m.closers_in('Closes #10，#11'))`), [10, 11]);
});

test('closing keyword：跨仓引用只登记不操作，需单独标出', behavioral, () => {
  // close_linked_issues.js 跨仓「只登记不操作」；报告必须能区分，否则读者会误以为
  // 本仓发版 PR 会把 other/repo#55 关掉。
  //
  // 口径说明：跨仓 keyword 是**独立写法**（`Closes other/repo#55`），GitHub 官方也不支持
  // 「`Closes #1, other/repo#2`」这种混合列表当跨仓 —— 所以这里只测独立形态。
  assert.deepEqual(py(`sorted(m.closers_in('Closes other/repo#55'))`), [55]);
  assert.deepEqual(py(`sorted(m.cross_repo_closers('Closes other/repo#55'))`), [55]);
  assert.deepEqual(py(`sorted(m.cross_repo_closers('Closes #1926'))`), [], '本仓不算跨仓');
  assert.deepEqual(
    py(`sorted(m.cross_repo_closers('Refs other/other-repo#7'))`),
    [],
    'Refs 不是 closing keyword，不该被当成跨仓关卡',
  );
});

test('closing keyword：解析发版 PR 正文里的 Closes / Fixes / Resolves', behavioral, () => {
  assert.deepEqual(py(`sorted(m.closers_in('Closes #1926, #1927'))`), [1926, 1927]);
  assert.deepEqual(py(`sorted(m.closers_in('fixes #100'))`), [100]);
  assert.deepEqual(py(`sorted(m.closers_in('Resolved #7'))`), [7]);
  assert.deepEqual(py(`sorted(m.closers_in('close #5; closed #6; resolves #7'))`), [5, 6, 7]);
});

test('closing keyword：代码块与行内代码内的关键字不得匹配', behavioral, () => {
  // 防「文档里讲解该机制」被当成真关键字
  assert.deepEqual(
    py(
      `sorted(m.closers_in(${JSON.stringify(
        '正文说明：功能 PR 写 Closes #123 无效，因为 base 不是默认分支。',
      )}))`,
    ),
    [123],
    '散文的真关键字应当匹配',
  );
  assert.deepEqual(
    py(
      `sorted(m.closers_in(${JSON.stringify('示例：\n```\nCloses #999\n```\n')}))`,
    ),
    [],
    '围栏代码块内的关键字不得匹配',
  );
  assert.deepEqual(
    py(`sorted(m.closers_in(${JSON.stringify('写 `Closes #888` 这样不生效')}))`),
    [],
    '行内代码内的关键字不得匹配',
  );
});

test('closing keyword：无关键字 / 空正文安全返回空集', behavioral, () => {
  assert.deepEqual(py(`sorted(m.closers_in('本次发版不含关卡'))`), []);
  assert.deepEqual(py(`sorted(m.closers_in(''))`), []);
  assert.deepEqual(py(`sorted(m.closers_in(None))`), []);
});

// ---------------------------------------------------------------------------
// 项 5：批次规模护栏 —— 超阈值只warn 不 block
// ---------------------------------------------------------------------------

test('批次规模：超软阈值给 warn，且不升级为 block', behavioral, () => {
  const big = py(`m.diff_size_warn(300, 9.0).level`);
  assert.equal(big, 'warn', '299 提交 / 9 天应 warn');
  const small = py(`m.diff_size_warn(40, 3.0).level`);
  assert.equal(small, 'ok', '40 提交 / 3 天属常规区间');
  assert.equal(py(`m.diff_size_warn(40, 3.0).detail`).includes('常规区间'), true);
});

test('批次规模：只超时间维度也 warn（commit 数少但拖了很久）', behavioral, () => {
  assert.equal(py(`m.diff_size_warn(10, 30.0).level`), 'warn', '10 个提交拖 30 天也该提示');
});

// ---------------------------------------------------------------------------
// 项 6：DDL 风险识别 —— 迁移不可逆
// ---------------------------------------------------------------------------

test('DDL 风险：命中迁移/建表文件时 warn 并列出文件', behavioral, () => {
  const hit = py(`[m.migration_risk_warn(['backend/alembic/versions/x.py']).level, m.migration_risk_warn(['backend/alembic/versions/x.py']).evidence['files']]`);
  assert.equal(hit[0], 'warn');
  assert.deepEqual(hit[1], ['backend/alembic/versions/x.py']);
});

test('DDL 风险：本仓真实迁移文件必须逐条命中（首版结构上不可能亮红）', behavioral, () => {
  // 2026-11-02 修复：首版正则要求 `migrations/` 带斜杠、且 `init_db` 出现在**路径**里。
  // 而本仓迁移函数写在 `backend/app/core/migrations.py`、`init_db()` 是 `database.py`
  // 里的函数名 —— 于是 v0.3.0 发版时 1320 行迁移改动 + 5 张新表被判「未命中」（假绿灯）。
  //
  // 这里**逐条单独**断言，不放进同一个列表：放一起时只要有一个命中就整条绿，
  // 恰好就是这么写的旧用例让这个缺口活了下来。
  for (const f of [
    'backend/app/core/migrations.py',
    'backend/app/core/database.py',
    'backend/app/domains/users/models.py',
    'backend/app/models/sync_log.py',
    'supabase/migrations/001_init.sql',
  ]) {
    assert.equal(
      py(`m.migration_risk_warn([${JSON.stringify(f)}]).level`),
      'warn',
      `${f} 必须命中 DDL 判据`,
    );
  }
});

test('DDL 风险：文件列表被截断时不得判「通过」（拿不到输入不许当正常）', behavioral, () => {
  // compare API 只回前 300 个文件。旧实现即使什么都没匹配到也报 ok，
  // 于是「不知道有没有 DDL」被渲染成「没有 DDL」。
  assert.equal(
    py(`m.migration_risk_warn(['frontend/src/views/x.vue']).level`),
    'ok',
    '列表完整且无命中 ⇒ 才可以是 ok',
  );
  assert.equal(
    py(`m.migration_risk_warn(['frontend/src/views/x.vue'], truncated=True).level`),
    'warn',
    '列表被截断 ⇒ 必须 warn，不能报通过',
  );
  assert.equal(
    py(`m.migration_risk_warn(['frontend/src/views/x.vue'], truncated=True).evidence['truncated']`),
    true,
    'evidence 要能看出为什么不是 ok',
  );
  assert.equal(
    py(`m.migration_risk_warn(['backend/app/core/migrations.py'], truncated=True).level`),
    'warn',
    '命中且截断仍是 warn',
  );
});

test('DDL 风险：纯业务代码改动不得误报', behavioral, () => {
  assert.equal(
    py(`m.migration_risk_warn(['frontend/src/views/x.vue', 'backend/app/domains/pnl/views.py']).level`),
    'ok',
    'vue / views 改动不该被当成 DDL',
  );
  assert.equal(py(`m.migration_risk_warn([]).level`), 'ok', '空列表也不该报错');
});

test('DDL 风险：schema.sql / init_db / .sql 要命中', behavioral, () => {
  for (const f of ['backend/schema.sql', 'backend/app/core/init_db.py', 'x/migrations/001.sql']) {
    assert.equal(py(`m.migration_risk_warn([${JSON.stringify(f)}]).level`), 'warn', `${f} 应命中`);
  }
});

// ---------------------------------------------------------------------------
// 项 7：单 PR 规模护栏
// ---------------------------------------------------------------------------

test('PR 规模：超大 PR warn，常规 PR 返回 None（不产生噪声行）', behavioral, () => {
  assert.equal(py(`m.pr_size_warn({'number': 1978, 'changed_files': 9, 'additions': 1472})`), null);
  assert.equal(
    py(`m.pr_size_warn({'number': 1, 'changed_files': 80, 'additions': 4000}).level`),
    'warn',
  );
  assert.equal(
    py(`m.pr_size_warn({'number': 1, 'changed_files': 9, 'additions': 3000}).level`),
    'warn',
    '行数超阈值也要 warn（1978 的 1472 行已接近软上限）',
  );
});

test('PR 规模：字段缺失时不得崩', behavioral, () => {
  assert.equal(py(`m.pr_size_warn({'number': 5})`), null, '缺字段按 0 处理');
});

// ---------------------------------------------------------------------------
// 项 7.5：待发 PR 计数 —— 一页取不满时只能给下限
// ---------------------------------------------------------------------------

test('待发 PR 计数：一页装满且边界未跨过 ⇒ 未取全（只能给下限）', behavioral, () => {
  // v0.3.0 发版实测：真实 220 个待发 PR，报告写「27 个」并据此断言「标题无中间态信号词」，
  // 实际只覆盖 12%。这里钉住「未取全」必须被识别出来。
  const r = py(
    `m.merged_since_release([
      {'number': 1, 'merged_at': '2026-11-01T00:00:00Z'},
      {'number': 2, 'merged_at': '2026-10-30T00:00:00Z'},
      {'number': 3, 'merged_at': '2026-10-29T00:00:00Z'},
    ], '2026-10-22T00:00:00Z', 3)`,
  );
  assert.equal(r[1], false, '本页装满且末条仍晚于发版时间 ⇒ 后面还有，未取全');
  assert.equal(r[0].length, 3);
});

test('待发 PR 计数：一页没装满 ⇒ 已取全', behavioral, () => {
  const r = py(
    `m.merged_since_release([
      {'number': 1, 'merged_at': '2026-11-01T00:00:00Z'},
    ], '2026-10-22T00:00:00Z', 30)`,
  );
  assert.equal(r[1], true, '不足一页 ⇒ 全量');
  assert.equal(r[0].length, 1);
});

test('待发 PR 计数：本页已跨过发版边界 ⇒ 已取全（不必再多翻页）', behavioral, () => {
  const r = py(
    `m.merged_since_release([
      {'number': 1, 'merged_at': '2026-11-01T00:00:00Z'},
      {'number': 2, 'merged_at': '2026-10-20T00:00:00Z'},
    ], '2026-10-22T00:00:00Z', 2)`,
  );
  assert.equal(r[1], true, '末条已早于发版时间 ⇒ 边界跨过，本页即全量');
  assert.equal(r[0].length, 1, '早于发版时间的那条不算待发');
});

test('待发 PR 计数：不知道上次发版时间 ⇒ 不得声称全量', behavioral, () => {
  const r = py(`m.merged_since_release([{'number': 1, 'merged_at': '2026-11-01T00:00:00Z'}], None, 30)`);
  assert.deepEqual(r, [[], false], '边界未知时既不能给数，也不能说全量');
});

test('待发 PR 计数：空列表不得崩', behavioral, () => {
  assert.deepEqual(py(`m.merged_since_release([], '2026-10-22T00:00:00Z', 30)`), [[], true]);
});

test('静态：报告不得把下限写成精确值', () => {
  // 渲染层必须显式标「下限」，否则读者会把 27 读成「一共 27 个」。
  assert.ok(SRC.includes('下限'), 'render() 必须把未取全的计数标成下限');
  assert.ok(SRC.includes('merged_since_complete'), '报告 dict 必须带取全标志，供渲染层判断');
});

// ---------------------------------------------------------------------------
// 项 8：静态口径断言 —— 防止「报告绿灯被读成可发版」
// ---------------------------------------------------------------------------

test('静态：报告必须显式声明机械绿灯 ≠ 可发版', () => {
  assert.ok(
    SRC.includes('绿灯 ≠ 可发版'),
    'render() 必须带这句免责，否则读者会把机械绿灯当「可以发版」',
  );
  assert.ok(SRC.includes('语义闸（不可机械化）'), '必须有一项显式交接给语义复核');
});

test('静态：脚本永不 merge / push / 关issue', () => {
  // 不可逆动作必须缺席。open_release_pr 只读列表，close_linked_issues 是别的脚本的事。
  const forbidden = [
    /gh\s+pr\s+merge/,
    /\bgit\s+push\b/,
    /state_reason/,
    /--state\s+closed/,
    /gh\s+issue\s+close/,
  ];
  for (const re of forbidden) {
    assert.ok(!re.test(SRC), `不应出现不可逆动作：${re}`);
  }
});

test('静态：不得引入第三方依赖', () => {
  const imports = [...SRC.matchAll(/^\s*(?:from|import)\s+([a-zA-Z0-9_.]+)/gm)].map((m) =>
    m[1].split('.')[0],
  );
  const allowed = new Set([
    '__future__', 'argparse', 'json', 're', 'subprocess', 'sys',
    'dataclasses', 'datetime', 'typing', 'pathlib',
  ]);
  for (const mod of imports) {
    assert.ok(allowed.has(mod), `不允许的依赖：${mod}（须零新依赖）`);
  }
});

test('静态：gh_json 必须走 gh api 子命令且带重试', () => {
  assert.ok(SRC.includes("'gh', 'api'"), 'gh_json 必须调 gh api');
  assert.ok(/def gh_json\(.*retries/.test(SRC), 'gh_json 必须带 retries 参数');
  assert.ok(SRC.includes("except Exception"), '必须捕获异常重试，否则单次网络抖动就整轮失败');
});

test('静态：PR_PAGE 有性能实测注释，避免后人调回100', () => {
  // 调回 per_page=100 会让脚本从1m47s 退回 3m21s 并稳定 SIGTERM（2026-10-08 实测）
  assert.ok(SRC.includes('PR_PAGE = 30'), 'PR_PAGE 必须保持 30');
  assert.ok(SRC.includes('94s'), '性能实测数据必须留在注释里，否则下一个人会「优化」回去');
});
