/**
 * `scripts/audit_text_contrast.mjs` 的回归用例（#1586）。
 *
 * WHY 有这份文件
 * --------------
 * 这个审计器是 #1586 的**验收工具**——「探市页不达标清零」这句话靠它复核。
 * 而它初版有两个**取证缺陷**，都会让结论系统性偏错：
 *
 *   ① **字号判定方向错**：只在 `color:` 行**之后**找 `font-size`，而本仓绝大多数规则把
 *      `font-size` 写在 `color:` **之前**（`.bias-updated { font-size: 12px; color: … }`），
 *      于是全部退化成「字号?」、一律按 4.5:1 判 → **把「大字达标」误报成「不达标」**
 *      （32 处命中里有一批本是 3:1 即达标的装饰/大字）。
 *   ② **暗色端零覆盖**：暗色令牌是 `rgb(237 234 229 / N%)` 半透明写法，原 `parseHex` 返回
 *      `null` 后 `continue` → **所有暗色 `color:` 用法从未被计算过**，暗色端等于没扫。
 *
 * 两个缺陷都属于「工具悄悄给错答案」——比漏报更坏，因为人会拿它当验收依据。
 * 故钉住：既钉正确行为，也钉**不能过度抑制**（真不达标项必须仍被报出来）。
 *
 * 怎么跑
 * ------
 *     node --test "scripts/tests/*.test.js"      # 或根目录 `pnpm test:scripts`
 *
 * 依赖：**零新依赖**（只用 Node 内置 `node:test` / `node:assert`）。
 * 做法：在临时目录里造一棵最小的 `frontend/src`（令牌表 + 夹具样式），
 * 然后**以子进程跑真脚本**——测的是真实入口，不是重构出来的内部函数。
 */

import { test } from 'node:test';
import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import { mkdtempSync, mkdirSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const HERE = dirname(fileURLToPath(import.meta.url));
const SCRIPT = resolve(HERE, '..', 'audit_text_contrast.mjs');

/** 亮色令牌表：只放夹具用得到的，值取自真实 `frontend/src/style/colors.css`。 */
const COLORS_CSS = `:root {
  --bg-page: #fdfbf7;
  --bg-card: #ffffff;
  --text-tertiary: #8c8478;
  --text-tertiary-ink: #6b6258;
  --color-rise: #e34f38;
  --color-rise-ink: #c0341f;
}
`;

/** 暗色令牌表：刻意用半透明写法——缺陷 ② 的诱因就是这个形态。 */
const DARK_SCSS = `:root.dark {
  --bg-page: #1a1816;
  --bg-card: #242120;
  --text-tertiary: rgb(237 234 229 / 40%);
  --text-tertiary-ink: rgb(237 234 229 / 72%);
}
`;

const FIXTURE = `/* 夹具：#1586 审计器回归
   每段对应一条断言，段名即用例名。 */

/* ① 字号写在 color 之前 + 大字（28px/700）→ 按 3:1 判，达标，不得进「不达标」 */
.size-before {
  font-size: 28px;
  font-weight: 700;
  color: var(--color-rise);
}

/* ② 字号来自祖先规则（SCSS 嵌套）：祖先 12px → 子规则必须按 12px 判、标出来源 */
.ancestor-small {
  font-size: 12px;

  &__child {
    color: var(--text-tertiary);
  }
}

/* ③ 同上但祖先是大字（26px）→ 达标，不得进「不达标」 */
.ancestor-large {
  font-size: 26px;

  &__big-child {
    color: var(--color-rise);
  }
}

/* ④ 真不达标（12px 正文）→ 必须仍被报出来（防豁免机制过度抑制） */
.real-bad {
  font-size: 12px;
  color: var(--text-tertiary);
}

/* ⑤ 人工豁免指令 → 移入「已登记豁免」，不进「不达标」 */
.exempted {
  font-size: 15px;

  /* audit-text-contrast: exempt 用例理由（回归夹具） */
  color: var(--text-tertiary);
}

/* ⑥ 暗色半透明令牌（选择器含 dark）→ 必须做 alpha 合成后参与判定 */
.panel-dark__text {
  color: var(--text-tertiary);
}
`;

/** 造一棵最小仓库树并跑真脚本，返回 stdout。 */
function runAudit(extraArgs = []) {
  const root = mkdtempSync(join(tmpdir(), 'audit-contrast-'));
  try {
    mkdirSync(join(root, 'frontend', 'src', 'style'), { recursive: true });
    writeFileSync(join(root, 'frontend', 'src', 'style', 'colors.css'), COLORS_CSS);
    writeFileSync(join(root, 'frontend', 'src', 'style', 'dark.scss'), DARK_SCSS);
    writeFileSync(join(root, 'frontend', 'src', 'fixture.scss'), FIXTURE);
    return execFileSync(process.execPath, [SCRIPT, ...extraArgs], { cwd: root, encoding: 'utf8' });
  } finally {
    rmSync(root, { recursive: true, force: true });
  }
}

/** 只取某一报告段落的正文（`=== 标题 ===` 之间）。 */
function section(out, title) {
  const lines = out.split('\n');
  const start = lines.findIndex(l => l.startsWith('===') && l.includes(title));
  if (start < 0) return '';
  const rest = lines.slice(start + 1);
  const end = rest.findIndex(l => l.startsWith('===') || l.startsWith('说明：'));
  return (end < 0 ? rest : rest.slice(0, end)).join('\n');
}

/**
 * 「已是文字级令牌但仍不达标」段。
 * 注意夹具里 `--text-tertiary` 属**文字级**令牌，命中落在这里 —— 不是首段
 * 「不达标（建议换 -ink）」（那段只收「底色级令牌当文字色」，本夹具为 0 处）。
 */
function noInkBad(out) {
  return section(out, '已是文字级令牌但仍不达标');
}

const full = (() => {
  let cached = null;
  return () => (cached ??= runAudit(['--all']));
})();

test('缺陷①：font-size 写在 color 之前时仍能取到（大字按 3:1 判）', () => {
  const out = full();
  const large = section(out, '大字/装饰场景');
  // 28px/700 属大字 → 3.86:1 达标 → 出现在「大字」段，而不是「不达标」段。
  const sizeBefore = large.split('\n\n').find(b => b.includes('.size-before')) || '';
  assert.match(sizeBefore, /\[28px 700\]/, '大字段应带出 28px/700 的字号判据');
  assert.ok(!sizeBefore.includes('字号?'), `28px 已声明，不得退化成「字号?」：\n${large}`);
  assert.ok(!noInkBad(out).includes('.size-before'), '大字达标项不得被误报为不达标');
});

test('缺陷①续：字号来自祖先规则时按继承值判并标出来源', () => {
  const bad = noInkBad(full());
  assert.match(bad, /&__child/, '继承 12px 的子规则应被判为不达标');
  assert.match(bad, /\[12px\][^\n]*继承自[^\n]*\.ancestor-small/, '应带出继承到的字号与来源选择器');
});

test('缺陷①续：祖先为大字时不再误报', () => {
  const out = full();
  assert.ok(!noInkBad(out).includes('&__big-child'), '继承 26px 应判为达标');
  assert.match(section(out, '大字/装饰场景'), /&__big-child/, '应落在大字段并标出继承字号');
});

test('缺陷②：暗色半透明令牌需 alpha 合成后参与判定（原实现整片跳过）', () => {
  const bad = noInkBad(full());
  const block = bad.split('\n\n').find(b => b.includes('panel-dark__text')) || '';
  assert.ok(block, '暗色 context 的用法必须被扫到（原实现返回 null 后 continue）');
  assert.match(block, /rgb\(237 234 229 \/ 40%\)/, '应回显原始半透明值，便于人工复核');
  // 合成后必须真的用暗卡底算：3.32:1，而不是拿亮色值算出 3.69:1。
  assert.match(block, /3\.32:1/, '应按暗卡底合成后计算对比度');
});

test('缺陷③：暗色行的「换 -ink 后」建议须用暗色 -ink 值（不得混主题）', () => {
  const bad = noInkBad(full());
  const block = bad.split('\n\n').find(b => b.includes('panel-dark__text')) || '';
  // 暗色 --text-tertiary-ink = rgb(... / 72%)，对暗卡 7.55:1；若误用亮色 #6b6258 会算出 2.67:1。
  assert.match(block, /换 `--text-tertiary-ink` 后 7\.55:1/, '应给出暗色 -ink 的对比度');
  assert.ok(!block.includes('2.67:1'), '不得拿亮色 -ink 值去估算暗色行');
});

test('真不达标项仍被抓到（豁免机制不得过度抑制）', () => {
  const bad = noInkBad(full());
  assert.match(bad, /\.real-bad/, '12px 正文的 --text-tertiary 必须报出');
  assert.match(bad, /--text-tertiary #8c8478/, '应回显令牌与其亮色值');
});

test('exempt 指令：移入「已登记豁免」并保留理由与选择器，不进「不达标」', () => {
  const out = full();
  assert.ok(!noInkBad(out).includes('.exempted'), '豁免项不得出现在不达标段');
  const exempted = section(out, '已登记豁免');
  assert.match(exempted, /\.exempted/, '应带出选择器，使豁免可被定位');
  assert.match(exempted, /用例理由（回归夹具）/, '应带出理由文本，使豁免可追溯');
});

test('汇总口径：不达标数与豁免数可被复核', () => {
  const out = full();
  // 不达标 3 处 = real-bad + ancestor-small &__child + panel-dark__text
  const listed = noInkBad(out)
    .split('\n')
    .filter(l => l.startsWith('frontend')).length;
  assert.equal(listed, 3, `不达标段应恰好 3 条，实际 ${listed} 条：\n${out}`);
  assert.match(out, /已登记豁免（代码内有 audit-text-contrast 指令，共 1 处）/);
  assert.match(out, /发现「底色级令牌当文字色」 2 处，其中按其字号判据不达标 0 处/);
});
