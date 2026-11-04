#!/usr/bin/env node
// 页面规模门禁（issue #980 治本项）
//
// 扫描 .vue 文件行数，做两件事：
//   1. 存量可见：报告超阈清单（原能力）；
//   2. 增量冻结：配合 `--baseline`，把「已超阈的存量」登记成基线，此后
//      **只减不增** —— 存量文件涨一行、或新增一个超阈文件，都判红。
//
// WHY 要基线（2026-10-24 实测，证据见 issue #980 评论）
// ---------------------------------------------------
// 本卡此前已拆过 9 个页面，但 `--mode warn` 只是「打印一下」，没人守：
//   WatchlistFilterBar 332 → 497 / welcome 370 → 440 /
//   reconcile-workbench 336 → 405 / watchlist/index 369 → 403
// 4 个已回超 400 行阈值。**不设闸，拆完必涨**，拆多少都是白干。
// 故本脚本的判据从「报告趋势」升级为「冻结增量」，与仓库既有基线守卫
// （`guard_price_precision.mjs` / `guard_detail_tables.py`）同一纪律。
//
// 用法
// ----
//   # CI（cwd = frontend/，基线在仓库根 scripts/ 下）
//   node ../scripts/check_vue_size.mjs --threshold 400 --mode fail \
//        --baseline ../scripts/vue-size-baseline.json
//
//   # 本地收敛后收紧基线（**只允许下调**，上调会被拒绝）
//   node ../scripts/check_vue_size.mjs --update-baseline --baseline ../scripts/vue-size-baseline.json
//
// 参数
// ----
//   --root <dir>           扫描根目录（相对 cwd），默认 src
//   --threshold <n>        行数阈值，默认 400（也认基线里的 threshold）
//   --mode warn|fail       warn=始终退出 0；fail=有违规时退出 1
//   --baseline <path>      基线 JSON；给了它判据才升级为「只减不增」
//   --update-baseline      按当前实测重写基线（只允许下调 / 移除）
//
// 退出码
// ------
//   0 = 通过（warn 模式即便有违规也返回 0）
//   1 = 命中栅栏（fail 模式）
//   2 = 拿不到输入 / 口径冲突（**不得**当成通过，否则是假绿）
//
// 已知不做
// --------
// 只数行数。把逻辑挪进 composable 但组件本身仍混乱，本门禁看不见 —— 它是
// 「规模」判据，不是「内聚性」判据，别拿它替代 review。

import { readFileSync, readdirSync, writeFileSync, statSync } from 'node:fs';
import { join, extname, relative } from 'node:path';

const args = process.argv.slice(2);
function getArg(name, def) {
  const i = args.indexOf(name);
  return i >= 0 && i + 1 < args.length ? args[i + 1] : def;
}
const hasFlag = name => args.includes(name);

const root = getArg('--root', 'src');
const mode = getArg('--mode', 'warn');
const baselinePath = getArg('--baseline', null);
const updateBaseline = hasFlag('--update-baseline');
const explicitThreshold = hasFlag('--threshold') ? parseInt(getArg('--threshold'), 10) : null;

if (!['warn', 'fail'].includes(mode)) {
  console.error(`[页面规模门禁] --mode 只认 warn / fail，收到 ${mode}`);
  process.exit(2);
}
if (explicitThreshold !== null && !Number.isInteger(explicitThreshold)) {
  console.error(`[页面规模门禁] --threshold 只认整数，收到 ${getArg('--threshold')}`);
  process.exit(2);
}
if (!statSync(root, { throwIfNoEntry: false })?.isDirectory()) {
  console.error(`[页面规模门禁] 扫描根目录不存在或不是目录：${root}`);
  console.error('  （cwd 是不是没设成 frontend/？--root 默认是相对 cwd 的 src）');
  process.exit(2);
}

// ── 基线读取 ────────────────────────────────────────────────────────────
function loadBaseline(path, allowMissing) {
  if (!path) return null;
  let raw;
  try {
    raw = readFileSync(path, 'utf8');
  } catch (e) {
    // 首次建立基线时文件本来就不存在，那是正常路径；但**校验**时读不到，
    // 说明基线丢了 —— 静默降级成 warn 就是假绿，故判 exit 2。
    if (allowMissing && e.code === 'ENOENT') return { threshold: undefined, files: {} };
    console.error(`[页面规模门禁] 读不到基线文件 ${path}：${e.message}`);
    console.error('  基线缺失 ≠「没有存量」——静默降级成 warn 就是假绿，故判 exit 2。');
    process.exit(2);
  }
  let parsed;
  try {
    parsed = JSON.parse(raw);
  } catch (e) {
    console.error(`[页面规模门禁] 基线 JSON 解析失败 ${path}：${e.message}`);
    process.exit(2);
  }
  if (!parsed || typeof parsed !== 'object' || typeof parsed.files !== 'object' || parsed.files === null) {
    console.error('[页面规模门禁] 基线格式不对：需要 { threshold, files: { "<相对 root 的路径>": 行数 } }');
    process.exit(2);
  }
  for (const [k, v] of Object.entries(parsed.files)) {
    if (!Number.isInteger(v) || v <= 0) {
      console.error(`[页面规模门禁] 基线条目非法：${k} = ${JSON.stringify(v)}（须为正整数行数）`);
      process.exit(2);
    }
  }
  return parsed;
}

const baseline = loadBaseline(baselinePath, updateBaseline);

// 阈值口径必须唯一：命令行与基线同时声明且不等 ⇒ 谁对说不清，不给猜。
if (
  baseline &&
  Number.isInteger(baseline.threshold) &&
  explicitThreshold !== null &&
  baseline.threshold !== explicitThreshold
) {
  console.error(
    `[页面规模门禁] 阈值口径冲突：命令行 --threshold ${explicitThreshold} vs 基线 threshold ${baseline.threshold}`
  );
  console.error('  同一份判据只能有一个阈值，否则红/绿取决于谁先被读到。');
  process.exit(2);
}
const threshold = explicitThreshold ?? (Number.isInteger(baseline?.threshold) ? baseline.threshold : 400);

// ── 扫描 ────────────────────────────────────────────────────────────────
function walk(dir, acc) {
  let entries;
  try {
    entries = readdirSync(dir, { withFileTypes: true });
  } catch {
    return acc;
  }
  for (const entry of entries) {
    const full = join(dir, entry.name);
    if (entry.isDirectory()) {
      // 跳过依赖与缓存目录
      if (entry.name === 'node_modules' || entry.name.startsWith('.')) continue;
      walk(full, acc);
    } else if (entry.isFile() && extname(entry.name) === '.vue') {
      acc.push(full);
    }
  }
  return acc;
}

const files = walk(root, []);

// 基线 key 一律 POSIX 分隔符：Windows 下 join 出来是反斜杠，直接存进基线会让
// 同一文件在两个平台上是两条记录 —— 兜底记录看不到真身，门禁在 CI 上假绿。
const keyOf = f => relative(root, f).split('\\').join('/');

const measured = new Map();
for (const f of files) {
  let lines;
  try {
    lines = readFileSync(f, 'utf8').split('\n').length;
  } catch {
    continue;
  }
  measured.set(keyOf(f), lines);
}

const oversized = [...measured.entries()].filter(([, n]) => n > threshold).sort((a, b) => b[1] - a[1]);

// ── --update-baseline：只允许下调 ────────────────────────────────────────
if (updateBaseline) {
  if (!baselinePath) {
    console.error('[页面规模门禁] --update-baseline 需要同时给 --baseline <path>，否则不知道写哪儿');
    process.exit(2);
  }
  const prev = baseline?.files ?? {};
  const next = Object.fromEntries(oversized);
  const raised = Object.keys(next).filter(k => k in prev && next[k] > prev[k]);
  if (raised.length > 0) {
    console.error('[页面规模门禁] 拒绝写入：基线只能下调，以下条目比基线更大了 ——');
    for (const k of raised) console.error(`  ${k}: ${prev[k]} → ${next[k]}（+${next[k] - prev[k]}）`);
    console.error('  放宽基线等于关闸。要让它合法，先拆文件；确实拆不动则改判据本身并留痕。');
    process.exit(2);
  }
  const keys = Object.keys(next).sort();
  const payload = {
    $comment:
      '页面规模门禁基线（issue #980）：只减不增。由 `node scripts/check_vue_size.mjs --update-baseline --baseline <本文件>` 生成；' +
      '上调会被脚本拒绝，拆小了会自动收紧。新增超阈文件不在基线内则直接判红。',
    issue: 980,
    threshold,
    generatedAt: new Date().toISOString().slice(0, 10),
    files: Object.fromEntries(keys.map(k => [k, next[k]])),
  };
  writeFileSync(baselinePath, `${JSON.stringify(payload, null, 2)}\n`, 'utf8');
  console.log(`[页面规模门禁] 基线已写入 ${baselinePath}（${keys.length} 项，阈值 ${threshold}）`);
  process.exit(0);
}

// ── 判据 ────────────────────────────────────────────────────────────────
console.log(
  `\n[页面规模门禁] 扫描 ${files.length} 个 .vue 文件，阈值 ${threshold} 行（模式=${mode}${
    baseline ? `，基线 ${Object.keys(baseline.files).length} 项` : '，无基线'
  }）`
);

if (!baseline) {
  // 兼容旧行为：只报告趋势（fail 时按阈值判红）
  if (oversized.length === 0) {
    console.log('✅ 无超出阈值的文件。');
    process.exit(0);
  }
  console.log(`⚠️  ${oversized.length} 个文件超出阈值：`);
  for (const [k, n] of oversized) console.log(`  ${String(n).padStart(5)} 行  ${k}`);
  console.log('\n说明：未提供 --baseline，本检查只报告趋势（warn）／仅按阈值判红（fail）。');
  console.log('要把增量真正冻住，加 --baseline scripts/vue-size-baseline.json（详见 issue #980）。');
  process.exit(mode === 'fail' ? 1 : 0);
}

const base = baseline.files;
const violations = [];
const hints = [];

// ① 新增超阈：基线里没有、现在超阈 ⇒ 新长出来的上帝页面
for (const [k, n] of oversized) {
  if (!(k in base)) violations.push({ kind: 'NEW', key: k, lines: n });
}
// ② 回涨：基线里有、现在比基线大 ⇒ 拆完又长回去（本卡实测的主形态）
for (const [k, n] of measured) {
  if (k in base && n > base[k]) violations.push({ kind: 'GROW', key: k, lines: n, base: base[k] });
}
// ③ 收紧提示：已降到阈值内 / 已变小的，提示可收紧（不判红，否则拆小了反而变红）
for (const [k, b] of Object.entries(base)) {
  if (!measured.has(k)) {
    hints.push(`${k} 已不存在（删除或改名），可用 --update-baseline 清理`);
    continue;
  }
  const n = measured.get(k);
  if (n <= threshold) hints.push(`${k} 已降到 ${n} 行（≤ ${threshold}），可用 --update-baseline 移出基线`);
  else if (n < b) hints.push(`${k} 已从 ${b} 降到 ${n} 行，可用 --update-baseline 收紧`);
}

if (violations.length === 0) {
  console.log(`✅ 通过：存量 ${Object.keys(base).length} 项基线内无回涨，且无新增超阈文件。`);
  if (hints.length > 0) {
    console.log(`提示：${hints.length} 项可以收紧基线（不影响本次结论）`);
    for (const h of hints.slice(0, 10)) console.log(`  · ${h}`);
    if (hints.length > 10) console.log(`  · …另有 ${hints.length - 10} 项`);
  }
  process.exit(0);
}

console.log(`❌ ${violations.length} 项违反「只减不增」：`);
for (const v of violations) {
  if (v.kind === 'NEW') {
    console.log(`  [NEW]  ${v.key} ${v.lines} 行（新增文件超阈值 ${threshold}）`);
  } else {
    console.log(`  [GROW] ${v.key} ${v.lines} 行（基线 ${v.base}，+${v.lines - v.base}）`);
  }
}
console.log(`
怎么修（按优先级）：
  1. 把涨出来的部分拆出去（子组件 / composable / 常量），让文件回到基线以内；
  2. 若这段逻辑确实必须留在页面里，同 PR 内拆出等量行数（净零也可以）；
  3. 非必要不碰基线 —— --update-baseline 只接受下调，上调会被直接拒绝。
来源：issue #980（上帝页面拆分）。基线文件：${baselinePath}
`);
process.exit(mode === 'fail' ? 1 : 0);
