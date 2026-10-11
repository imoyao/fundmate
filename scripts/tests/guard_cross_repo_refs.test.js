/**
 * `scripts/guard_cross_repo_refs.mjs` 的回归用例（源：CNB issue #2 的实测反馈）。
 *
 * ## WHY 有这份文件
 *
 * 这条守卫要插进 CI 的 `scripts_test` job（PR 门禁 `gate` 的 needs），
 * 判据一旦写松（漏判）或写紧（误判），代价是**两种**：
 *
 *   - 漏判 → GitHub 链接继续写成裸 `#N`，CNB 上点进去落到本仓的另一个号（用户实测撞到）；
 *   - 误判 → 把讲 CNB 编号（`#14` 里程碑）或代码正则（`#(\d+)`）的正常行判红，
 *     挡掉几十份不相干的 PR。本仓 `AGENTS.md` / `docs/spec/*` 里恰好混排两种编号，
 *     所以误判不是理论风险。
 *
 * 故这里把两类边界都钉住，并按仓里既有做法（guard_control_clip 等）留下**证伪探针**：
 * 把修复注回真实文件必须报红，否则说明用例只是「恰好绿」。
 *
 * ## 怎么跑
 *
 *     node --test "scripts/tests/*.test.js"     # 或根目录 `pnpm test:scripts`
 *
 * 依赖：**零新依赖**（只用 Node 内置 node:test / node:assert），纯离线。
 */

'use strict';

const assert = require('node:assert/strict');
const { test } = require('node:test');
const { mkdtempSync, writeFileSync, readFileSync, rmSync } = require('node:fs');
const { tmpdir } = require('node:os');
const { join } = require('node:path');
const { pathToFileURL } = require('node:url');

const { scanFiles } = require('../guard_cross_repo_refs.mjs');

const GUARD_SRC = readFileSync('scripts/guard_cross_repo_refs.mjs', 'utf8');
// 变体必须写进 scripts/ 目录：守卫用相对路径 import 基线模块，写到 /tmp 会解析不到。
const TMP_DIR = 'scripts';

/** 用一份（可能被改松的）守卫实现扫同一行样本。 */
function scanWith(mod, line) {
  const dir = mkdtempSync(join(TMP_DIR, 'case-'));
  const file = join(dir, 'sample.md');
  writeFileSync(file, line, 'utf8');
  try {
    return mod.scanFiles([file]).hits.length;
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
}

function scan(lines) {
  const dir = mkdtempSync(join(tmpdir(), 'cross-repo-ref-'));
  const file = join(dir, 'sample.md');
  writeFileSync(file, Array.isArray(lines) ? lines.join('\n') : lines, 'utf8');
  try {
    return scanFiles([file]);
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
}

const hitCount = (lines) => scan(lines).hits.length;

// ---------------------------------------------------------------------------
// 一、必须报红：提到 GitHub 却写裸 #N
// ---------------------------------------------------------------------------

test('命中：正文说 GitHub，编号却写成裸 #N', () => {
  assert.equal(hitCount('- 见 imoyao/fundmate#2050 那张'), 0, '限定形态 owner/repo#N 不该报');
  assert.equal(hitCount('- 这卡是 GitHub #2050 的镜像'), 0, '限定形态 GitHub #N 不该报');
  assert.equal(hitCount('- 对应的 GitHub 卡是 #2050'), 1);
  assert.equal(hitCount('- 见 upstream 的 #1996 / #1997'), 2);
  assert.equal(hitCount('- 镜像自 GitHub，原编号 #783'), 1);
});

test('命中：无任何标记的裸编号（守卫无法判断，但行内出现过 GitHub 词即算）', () => {
  assert.equal(hitCount('GitHub 侧讨论见 #1234。'), 1);
});

test('命中：完整链接与裸编号混排，只报没挂源的那个', () => {
  const lines = '- [#2050](https://github.com/imoyao/fundmate/issues/2050) 与 #2051 是同一批';
  assert.equal(hitCount(lines), 1, '挂了链接的那个不该报');
});

test('命中：跨仓写法 imoyao/fundmate#123 算已标注源', () => {
  assert.equal(hitCount('GitHub 见 imoyao/fundmate#123'), 0);
  assert.equal(hitCount('GitHub 见 imoyao/fundmate#123，另有 #456'), 1);
});

// ---------------------------------------------------------------------------
// 二、不许报红：CNB 编号 / 代码 / 已有链接
// ---------------------------------------------------------------------------

test('豁免：行里没有 GitHub 词（CNB 自己的编号，如里程碑 #14）', () => {
  assert.equal(hitCount('- 归入里程碑 #14，禁止散落'), 0);
  assert.equal(hitCount('CNB 侧 #5~#112 是那批镜像卡'), 0, 'CNB 编号不是跨仓引用');
});

test('豁免：行内代码里的裸编号（示例 / 正则）', () => {
  assert.equal(hitCount('幂等键形如 `GitHub 编号：#783`'), 0, '行内代码整段剔除后已无 GitHub 标记');
  assert.equal(hitCount("GITHUB_NUMBER_RE = re.compile(r'GitHub 编号：`#(\\d+)`')"), 0);
});

test('豁免：行尾 cross-repo-ref-allow（反例清单 / 讲机制本身）', () => {
  assert.equal(hitCount('例如：`GitHub #10` 是正例，而 GitHub #10 缺源 不对  <!-- cross-repo-ref-allow -->'), 0);
});

test('豁免：GitHub 完整链接行', () => {
  assert.equal(hitCount('- 来源：https://github.com/imoyao/fundmate/issues/783'), 0);
});

test('非捕获组不误触发豁免（?: 不是 markdown 加粗）', () => {
  // `(?:(?:#(\d+)))` 这类正则里 `(` 紧贴 `?`，不是 markdown 强调开始，豁免不该生效
  const line = "RE = re.compile(r'GitHub #(?:(\\d+)) #99')";
  assert.equal(hitCount(line), 1, '含 ?: 的代码行仍应报红（说明豁免判据没被 ? 撞松）');
});

// ---------------------------------------------------------------------------
// 三、证伪探针（守门的守门）：把判据改松，必须转红
// ---------------------------------------------------------------------------

/** 把守卫源码改一处，跑同一行样本，返回命中数。改不动（字符串没匹配上）直接抛。 */
async function hitsWith(orig, mutate, line) {
  const broken = mutate(orig);
  assert.notEqual(broken, orig, '探针的替换没匹配上——判据文本变了，探针自己先失效了');
  const tmp = join(TMP_DIR, `.variant-${Math.random().toString(36).slice(2)}.mjs`);
  writeFileSync(tmp, broken, 'utf8');
  try {
    const mod = await import(pathToFileURL(tmp).href);
    return scanWith(mod, line);
  } finally {
    rmSync(tmp, { force: true });
  }
}

test('探针：去掉「已标注源」的区间过滤 → 正例（GitHub #2050）被判红', async () => {
  const n = await hitsWith(GUARD_SRC, (s) =>
    s.replace('if (marked.some(([a, b]) => start >= a && start < b)) continue;', ''), '- 这卡是 GitHub #2050 的镜像');
  assert.equal(n, 1, '判据写松后应误报（说明「区间过滤」这一层真在起作用）');
});

test('探针：去掉行级豁免 → 反例清单里的行被判红', async () => {
  const n = await hitsWith(GUARD_SRC, (s) =>
    s.replace("if (line.includes('cross-repo-ref-allow')) return;", 'if (false) return;'),
  '正例 vs 反例：GitHub 那边的 #10 这样写不行  <!-- cross-repo-ref-allow -->');
  assert.equal(n, 1, '豁免层被去掉后该行应报红');
});

test('探针：去掉「行里要有 GitHub 词」前置判据 → CNB 自己的编号被误判', async () => {
  const n = await hitsWith(GUARD_SRC, (s) =>
    s.replace('if (!GH_WORDS_RE.test(line)) return;', 'if (false) return;'), '- 归入里程碑 #14，禁止散落');
  assert.equal(n, 1, '不收窄到 GitHub 行的话，AGENTS.md 里的 CNB 里程碑号会被误报');
});

test('探针：去掉行内代码剔除 → 文档里的示例被判红', async () => {
  const n = await hitsWith(GUARD_SRC, (s) =>
    s.replace('const stripped = stripInlineCode(line);', 'const stripped = line;'),
  '幂等键形如 `GitHub 编号：#783`，另见 GitHub 那边的 #7832');
  assert.equal(n, 1, '不剔行内代码的话，讲机制的示例自己就被判红（文档会没法写）');
});

test('探针：真实规则文本被注回真实文件必须报红，还原后探针编号消失', () => {
  const FILE = 'docs/spec/roadmap.md';
  const original = readFileSync(FILE, 'utf8');
  try {
    writeFileSync(FILE, original + '\n涉及 GitHub 那边的 #9999 的口径。\n', 'utf8');
    const after = scanFiles([join(process.cwd(), FILE)]).hits.filter((h) => h.number === '9999');
    assert.ok(after.length > 0, '把「GitHub 那边的 #9999」注回真实文件后守卫必须报红（否则判据是假绿）');
  } finally {
    writeFileSync(FILE, original, 'utf8');
  }
  const restored = scanFiles([join(process.cwd(), FILE)]).hits.filter((h) => h.number === '9999');
  assert.equal(restored.length, 0, '还原后探针编号应消失');
});

test('判据是行级、不是文件级：不带 GitHub 词的行不报', () => {
  assert.equal(hitCount('探市页的口径见原卡 #9998。'), 0, '没有 GitHub 词的行不该被判跨仓引用');
});

test('探针：基线按行指纹冻结，不是按文件——已脏文件里新增的行仍要报红', async () => {
  // 用真实基线文件 docs/spec/roadmap.md（它本身在基线里），注入一条**新**行：
  // 若基线退化成「文件名进集合就整份放行」，这条会漏报。
  const FILE = 'docs/spec/roadmap.md';
  const original = readFileSync(FILE, 'utf8');
  try {
    writeFileSync(FILE, original + '\n见 GitHub 那边的 #88888 的口径。\n', 'utf8');
    const after = scanFiles([join(process.cwd(), FILE)]).hits.filter((h) => h.number === '88888');
    assert.equal(after.length, 1, '新行必须被报出（说明基线粒度是行、不是文件）');
  } finally {
    writeFileSync(FILE, original, 'utf8');
  }
});

test('基线键纳入文件与行文本：同行改一处即指纹变化', () => {
  const { baselineKey } = require('../guard_cross_repo_refs.mjs');
  const a = baselineKey('a.md', '见 GitHub 卡 #1 的口径');
  assert.equal(a, baselineKey('a.md', '见 GitHub 卡 #1 的口径'), '同一行文本指纹应稳定');
  assert.equal(a, baselineKey('a.md', '见  GitHub   卡 #1 的口径'), '空白差异不该让指纹漂移');
  assert.notEqual(a, baselineKey('a.md', '见 GitHub 卡 #2 的口径'), '内容变了指纹必须变');
  assert.notEqual(a, baselineKey('b.md', '见 GitHub 卡 #1 的口径'), '文件不同指纹必须不同');
});

test('限定形态含 PR / 卡 等词也算挂源（GitHub PR #123）', () => {
  assert.equal(hitCount('中间是 GitHub PR #2049 / GitHub PR #2051。'), 0);
  assert.equal(hitCount('源卡是 GitHub 卡 #2050。'), 0);
  assert.equal(hitCount('两处都指 GitHub，但写成 #2049 就不行'), 1);
});
