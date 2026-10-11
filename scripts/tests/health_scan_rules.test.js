/**
 * `scripts/issue_health_scan.py` 的回归用例（源 #1908）。
 *
 * ## WHY 有这份文件
 *
 * 该脚本每周一自动跑、把周报评论进 #1709「Issue 体检周报（固定跟踪卡）」，它的分类直接
 * 决定「哪些卡被建议关掉」。写错的代价分两类，都很贵：
 *
 *   - **假阳性**：把「只交付了一部分」的卡报成 A 类强信号 → 人工照着关 → 关早卡；
 *   - **口径误导**：B 类写「可关候选」，读者会以为「合过 = 验收达成」→ 大tracker 被误关。
 *
 * 2026-10-06 逐张实证复核（#1709 评论）发现五处口径问题，本文件把它们逐条钉住。
 *
 * ## 怎么跑
 *
 *     node --test "scripts/tests/*.test.js"     # 或根目录 `pnpm test:scripts`
 *
 * 零新依赖（只用 Node 内置 node:test / node:assert）。行为断言通过子进程调用 **真实**
 * Python 解释器跑 `issue_health_scan` 的纯函数（`closer_refs` / `classify` / `dedupe_bd`），
 * 不是在 JS 里复刻一份逻辑——复刻等于把被测逻辑抄一份，抄错的那份才是绿的。
 * 若环境里找不到 Python，行为用例会显式 skip 并打印原因，静态口径断言仍然执行。
 */

'use strict';

const assert = require('node:assert/strict');
const { test } = require('node:test');
const { spawnSync } = require('node:child_process');
const fs = require('node:fs');
const path = require('node:path');

const REPO_ROOT = path.resolve(__dirname, '..', '..');
const SRC = fs.readFileSync(
  path.join(REPO_ROOT, 'scripts', 'issue_health_scan.py'),
  'utf8',
);

// ---------------------------------------------------------------------------
// Python 解释器探测（行为断言用；CI 的 ubuntu-latest 自带 python3）
// ---------------------------------------------------------------------------

function findPython() {
  const candidates = [];
  if (process.env.PYTHON) candidates.push([process.env.PYTHON]);
  if (process.platform === 'win32') {
    candidates.push(['python'], ['py', '-3']);
  } else {
    candidates.push(['python3'], ['python']);
  }
  for (const args of candidates) {
    const r = spawnSync(args[0], [...args.slice(1), '--version'], { encoding: 'utf8' });
    if (!r.error && r.status === 0) return args;
  }
  return null;
}

const PYTHON = findPython();
const PY_SNIPPET = `
import json, sys
sys.path.insert(0, r'scripts')
import issue_health_scan as m
print(json.dumps(eval(r"""__EXPR__"""), ensure_ascii=True, default=list))
`;

/** 在真实 Python 里求值一个表达式，返回 JSON 解析后的结果。 */
function py(expr) {
  if (!PYTHON) throw new Error('找不到 Python 解释器');
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

/** closer_refs 的断言形态：返回 [强信号编号(升序), 限定降级编号(升序)]。 */
const refs = (bodyLiteral) =>
  py(`[sorted(m.closer_refs(${bodyLiteral})[0]), sorted(m.closer_refs(${bodyLiteral})[1])]`);

/** 只在有 Python 时执行的行为用例。 */
const behavioral = {
  skip: PYTHON ? false : '本机找不到 Python 解释器，行为断言跳过（静态断言仍执行）',
};

// ---------------------------------------------------------------------------
// 项 1：closing keyword 带括号限定词 → 从 A 降级为 B
// ---------------------------------------------------------------------------

test('项1·无限定词的 closing keyword 仍算 A 类强信号', behavioral, () => {
  assert.deepEqual(refs("'Closes #1915'"), [[1915], []]);
  assert.deepEqual(refs("'fixes #1286'"), [[1286], []]);
  assert.deepEqual(refs("'Resolves #12, resolves #13'"), [[12, 13], []]);
  assert.deepEqual(refs("''"), [[], []]);
  // 已知边界（既有行为，不在 #1908 范围）：CLOSER_KW 只认 resolv/resolve**s**/**ed，
  // 裸 `resolve #13` 不算关键字——GitHub 本身也没有裸 resolve 关键字，故不改实现，
  // 这里钉住以防误改。
  assert.deepEqual(refs("'resolve #13'"), [[], []]);
});

test('项1·括号限定词（部分 / 仅 / …）降级，不进 A 类', behavioral, () => {
  // 本轮实证的三个真实写法
  assert.deepEqual(refs("'Closes #1286（数据底座部分）'"), [[], [1286]]);
  assert.deepEqual(refs("'Closes #1285（仅备注编辑部分）'"), [[], [1285]]);
  assert.deepEqual(refs("'Closes #1167（部分：投顾抓取）'"), [[], [1167]]);
  // 半角括号 + 英文限定词同样识别
  assert.deepEqual(refs("'Fixes #20 (part only)'"), [[], [20]]);
});

test('项1·换行后再出现的括号不算本次 keyword 的限定词', behavioral, () => {
  // 降级只看紧随其后的括号：正文别处谈「部分」不能把强信号降级掉
  assert.deepEqual(refs("'Closes #10\\n\\n（部分说明见 PR 描述）'"), [[10], []]);
  // 同段紧跟（允许空格）才算限定
  assert.deepEqual(refs("'Closes #10 （仅前端）'"), [[], [10]]);
});

test('项1·同一编号同时有强信号与限定信号时以强信号为准', behavioral, () => {
  assert.deepEqual(refs("'Closes #10\\n\\nCloses #10（部分）'"), [[10], [10]]);
});

test('项1·classify 把限定降级判成 B 而非 A', behavioral, () => {
  const c = 'm.classify';
  const issue = "{'number': 1286, 'title': 'feat: shu ju di diao'}";
  // 有限定词 closer：closers 为空（closer_refs 已降级），但关联 PR 已合入 → B
  assert.equal(py(`${c}(${issue}, [], [1286], [1900], [])`), 'B');
  // 无限定词 closer → A
  assert.equal(py(`${c}(${issue}, [1900], [], [1900], [])`), 'A');
  // 有开放关联 PR → 两类都不进
  assert.equal(py(`${c}(${issue}, [1900], [], [1900], [1901])`), null);
  // 既无 closer 也无合入 → 不进候选
  assert.equal(py(`${c}(${issue}, [], [], [], [])`), null);
});

test('项1·split_closers 把已合入 PR 分成 closer / 降级两拨（scan 路径的守门）', behavioral, () => {
  // 强信号：PR 正文里是裸 keyword
  assert.deepEqual(py(`list(m.split_closers(10, [1900], m.closer_refs('Closes #10')))`), [
    [1900],
    [],
  ]);
  // 限定降级：PR 正文带括号限定词 —— 不能进 closer 那一拨（否则 A 段会收它）
  assert.deepEqual(py(`list(m.split_closers(1286, [1900], m.closer_refs('Closes #1286（数据底座部分）')))`), [
    [],
    [1900],
  ]);
  // 多 PR 且同一编号在强/弱两侧都出现（一个 PR 写裸 keyword、另一个写限定词）：
  // 合并口径下强信号优先 —— 两个已合入 PR 都算 closer，该卡不重复落进降级那一拨
  const refs = "m.closer_refs('Closes #7\\n\\nFixes #7（仅前端）')";
  assert.deepEqual(py(`list(m.split_closers(7, [1900, 1901], ${refs}))`), [[1900, 1901], []]);
  // 只有限定信号的两个 PR → 整卡不进 A，两拨都归到降级
  const refs2 = "m.closer_refs('Closes #7（仅前端）\\n\\nFixes #7（部分）')";
  assert.deepEqual(py(`list(m.split_closers(7, [1900, 1901], ${refs2}))`), [[], [1900, 1901]]);
  // 该编号没被任何已合入 PR 的 keyword 引用 → 两拨都空（不进 A/B 的closer 部分）
  assert.deepEqual(py(`list(m.split_closers(999, [1900], m.closer_refs('Closes #7')))`), [
    [],
    [],
  ]);
});

// ---------------------------------------------------------------------------
// 项 2：自动告警卡 / 固定跟踪卡不进 A/B
// ---------------------------------------------------------------------------

/** 本轮实证的两个应被排除的卡：#1490 自动告警、#1709 周报自身。 */
const ALERT_ISSUE = '{"number": 1490, "title": "【自动告警】每日调度 daily-snapshot 失败"}';
const TRACKER_ISSUE = '{"number": 1709, "title": "Issue 体检周报（固定跟踪卡）"}';
const NORMAL_ISSUE = '{"number": 1908, "title": "fix(health-scan): 五项修正"}';

test('项2·【自动告警】与固定跟踪卡识别为 TRACK_ONLY', behavioral, () => {
  assert.equal(py(`m.is_track_only(${ALERT_ISSUE})`), true);
  assert.equal(py(`m.is_track_only(${TRACKER_ISSUE})`), true);
  assert.equal(py(`m.is_track_only(${NORMAL_ISSUE})`), false);
});

test('项2·TRACK_ONLY 卡即便有关联 PR 合入也不进 A/B', behavioral, () => {
  assert.equal(py(`m.classify(${ALERT_ISSUE}, [1900], [], [1900], [])`), 'TRACK_ONLY');
});

// ---------------------------------------------------------------------------
// 项 4：B∩D 去重（同一张卡只出一处）
// ---------------------------------------------------------------------------

test('项4·同时命中 B 与 D 的卡只保留在 D，B 侧返回编号供附注', behavioral, () => {
  const weak = "[({'number': 1028}, [1900], ''), ({'number': 1764}, [1901], '')]";
  const stale = "[{'number': 1028}]";
  const kept = py(
    `[i[0]['number'] for i in m.dedupe_bd(${weak}, ${stale})[0]]`,
  );
  assert.deepEqual(kept, [1764]);
  assert.deepEqual(py(`m.dedupe_bd(${weak}, ${stale})[1]`), [1028]);
});

test('项4·无重叠时 B 侧原样保留、附注为空', behavioral, () => {
  const weak = "[({'number': 1764}, [1901], '')]";
  const stale = "[{'number': 1028}]";
  const res = py(
    `[m.dedupe_bd(${weak}, ${stale})[0][0][0]['number'], m.dedupe_bd(${weak}, ${stale})[1]]`,
  );
  assert.deepEqual(res, [1764, []]);
});

test('项4·本轮实证的四个重叠卡（#1028/#1014/#894/#808）全部只进 D', behavioral, () => {
  const weak =
    "[({'number': 1028}, [1], ''), ({'number': 1014}, [2], '')," +
    " ({'number': 894}, [3], ''), ({'number': 808}, [4], '')]";
  const stale =
    "[{'number': 1028}, {'number': 1014}, {'number': 894}, {'number': 808}]";
  assert.deepEqual(py(`m.dedupe_bd(${weak}, ${stale})[0]`), []);
  assert.deepEqual(py(`m.dedupe_bd(${weak}, ${stale})[1]`), [1028, 1014, 894, 808]);
});

// ---------------------------------------------------------------------------
// 项 3 / 项 5：措辞与反例（静态口径断言，任何环境都执行）
// ---------------------------------------------------------------------------

// ---------------------------------------------------------------------------
// 项 3 / 项 4：报告输出口径（真跑 render）+ 静态兜底
// ---------------------------------------------------------------------------

/** 用假数据渲染一份周报（不联网）。 */
const report = (over) =>
  py(`m.render(${over.total ?? 3}, ${over.strong ?? '[]'}, ${over.weak ?? '[]'}, ${over.checked ?? '[]'}, ${over.stale ?? '[]'}, ${over.zombie ?? '[]'}, ${over.track ?? '[]'}, ${over.overlap ?? '[]'})`);

const WEAK_1028 = "({'number': 1028, 'title': '债务卡', 'labels': [], 'updated_at': '2026-01-01T00:00:00Z'}, [1900], '')";
const WEAK_1764 = "({'number': 1764, 'title': 'feat 卡', 'labels': [], 'updated_at': '2026-01-01T00:00:00Z'}, [1901], '')";

test('项3·B 类不再叫「可关候选」，改「已合 PR 待复核」', behavioral, () => {
  const out = report({ weak: `[${WEAK_1764}]` });
  assert.ok(out.includes('### B. 已合 PR 待复核'), 'B 段标题应为「已合 PR 待复核」');
  assert.ok(!out.includes('可关候选'), '报告里不应再出现「可关候选」这一误导措辞');
  assert.ok(out.includes('不等于验收达成'), '处置约定须写明「有过合入 ≠ 验收达成」');
});

test('项4·B∩D 重叠卡只在 D 出现，B 段给出附注', behavioral, () => {
  const stale =
    "[{'number': 1028, 'title': '债务卡', 'labels': [], 'updated_at': '2026-01-01T00:00:00Z'}]";
  // 端到端：去重发生在 scan() 里，故这里复现真实调用链 dedupe_bd → render
  const out = py(
    `(lambda: (lambda w, s: m.render(3, [], w[0], [], s, [], [], w[1]))` +
      `(m.dedupe_bd([${WEAK_1028}, ${WEAK_1764}], ${stale}), ${stale}))()`,
  );
  const bSection = out.slice(out.indexOf('### B.'), out.indexOf('### C.'));
  const dSection = out.slice(out.indexOf('### D.'));
  // 卡列表行（以 '- #' 开头）才决定「出现在哪一段」；附注行（'>'）允许点名编号
  const bCards = bSection.split('\n').filter((l) => l.trimStart().startsWith('- #'));
  assert.ok(
    !bCards.some((l) => l.includes('#1028')),
    'B 段卡列表不应再出现重叠卡 #1028'
  );
  assert.ok(
    bCards.some((l) => l.includes('#1764')),
    'B 段应保留非重叠卡 #1764'
  );
  assert.ok(bSection.includes('同时命中 D'), 'B 段应附注重叠情况');
  assert.ok(bSection.includes('#1028'), '附注里应点名被移到 D 的编号');
  assert.ok(dSection.includes('#1028'), 'D 段应保留重叠卡 #1028');
});

test('项4·限定降级的卡在 B 段带降级标注', behavioral, () => {
  const weak =
    "({'number': 1286, 'title': 'feat 数据底座', 'labels': [], 'updated_at': '2026-01-01T00:00:00Z'}, [1900], ' | closing keyword 带括号限定词，已从 A 降级待复核')";
  const out = report({ weak: `[${weak}]` });
  const bSection = out.slice(out.indexOf('### B.'), out.indexOf('### C.'));
  assert.ok(bSection.includes('#1286'));
  assert.ok(bSection.includes('已从 A 降级待复核'), '降级卡应带说明，便于人工复核');
});

test('项2·被排除的两类卡在报告里单独说明', behavioral, () => {
  const out = report({
    track: "[{'number': 1490}, {'number': 1709}]",
  });
  assert.ok(out.includes('#1490') && out.includes('#1709'));
  assert.ok(out.includes('按生命周期排除'), '应说明这两类卡被排除的理由');
});

test('项5·报告正文不再引用被证伪的 #1349 反例', behavioral, () => {
  const out = report({});
  assert.ok(!out.includes('#1349'), '报告不应再引用 #1349 作反例');
});

test('项3/项5·docstring 与输出层同步（静态兜底，防注释层回潮）', () => {
  assert.ok(SRC.includes('已合 PR 待复核'), 'B 类标题应改为「已合 PR 待复核」');
  assert.ok(!SRC.includes('可关候选'), '不应再出现「可关候选」这一误导措辞');
  assert.ok(!SRC.includes('#1349'), '不应再引用 #1349 作反例');
  assert.ok(!SRC.includes('误标'), '不应再出现「误标」这一被证伪的说法');
});

test('项3·B 类反例改用真反例（#1460 / #1121 / #980）', () => {
  for (const n of ['#1460', '#1121', '#980']) {
    assert.ok(SRC.includes(n), `B 类反例应包含 ${n}`);
  }
});

test('项5·被证伪的「PR #1349 误标 #1133」反例已从脚本移除', () => {
  // #1908 项5：#1133 的权威需求细化评论（2026-08-29）§4 明确含「快照一致性对账 + 温柔提醒」，
  // PR #1349 实现与之一一对应，是真压轴交付而非误标——该反例不成立，不得再当依据。
  assert.ok(!SRC.includes('#1349'), '不应再引用 #1349 作反例');
  assert.ok(!SRC.includes('误标'), '不应再出现「误标」这一被证伪的说法');
});