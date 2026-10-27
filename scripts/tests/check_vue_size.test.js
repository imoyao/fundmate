/**
 * `scripts/check_vue_size.mjs` 的回归用例（issue #980 治本项）。
 *
 * ## WHY 有这份文件
 *
 * 本卡此前已经拆过 9 个页面，靠的是一条 `--mode warn` 的 CI 步骤 —— 它只打印
 * 不拦截。2026-10-24 实测：`WatchlistFilterBar` 332 → 497、`welcome` 370 → 440、
 * `reconcile-workbench` 336 → 405、`watchlist/index` 369 → 403，4 个已回超 400 行。
 * **拆完就涨回去**，因为没有任何东西拦住「涨」这个动作本身。
 *
 * 加基线冻结很容易写成「看起来有闸门、实际不设防」，故本文件钉两类证据：
 *
 * 1. **主判据真绿**：真实仓库 + 真实基线跑下来 exit 0（存量不误伤，否则没人看它）；
 * 2. **变异探针真红**：涨一行 / 新长一个超阈文件，必须 exit 1 并在输出里点名。
 *
 * 另有四条防「假绿 / 假红」：
 * 3. 基线**缺失**或**损坏**必须 exit 2（不得静默降级成 warn，那就是假绿）；
 * 4. `--update-baseline` 试图**上调**必须 exit 2 且**文件未被改写**（放宽闸门 = 关闸）；
 * 5. 拆小了必须**不判红**（否则谁拆谁被拦，闸门会被绕开）；
 * 6. 阈值口径冲突（命令行 vs 基线）必须 exit 2（红/绿不能取决于谁先被读到）。
 */

const { test } = require('node:test');
const assert = require('node:assert/strict');
const { spawnSync } = require('node:child_process');
const { mkdtempSync, mkdirSync, writeFileSync, readFileSync } = require('node:fs');
const { tmpdir } = require('node:os');
const { join } = require('node:path');

const root = join(__dirname, '..', '..');
const script = join(root, 'scripts', 'check_vue_size.mjs');
const realBaseline = join(root, 'scripts', 'vue-size-baseline.json');

/** 跑门禁；返回 { code, out }（失败不抛，交给断言判断） */
function run(cwd, extraArgs = []) {
  const r = spawnSync(process.execPath, [script, ...extraArgs], {
    cwd,
    encoding: 'utf8',
    // shell 必须为 false：Windows 下交给 cmd 解析会静默吃掉参数
    shell: false,
  });
  return { code: r.status, out: `${r.stdout ?? ''}${r.stderr ?? ''}` };
}

/** 生成恰好 n 行的假 .vue（无末尾换行，使 split('\n').length === n） */
const vueOf = n => Array.from({ length: n }, (_, i) => `<!-- L${i} -->`).join('\n');

/** 建一个临时仓库骨架：src/*.vue + baseline.json */
function sandbox({ files = {}, baselineFiles = {}, threshold = 400, rawBaseline = null } = {}) {
  const dir = mkdtempSync(join(tmpdir(), 'vue-size-'));
  mkdirSync(join(dir, 'src', 'views'), { recursive: true });
  for (const [rel, n] of Object.entries(files)) {
    writeFileSync(join(dir, 'src', rel), vueOf(n), 'utf8');
  }
  if (rawBaseline !== null) {
    writeFileSync(join(dir, 'baseline.json'), rawBaseline, 'utf8');
  } else {
    writeFileSync(
      join(dir, 'baseline.json'),
      JSON.stringify({ issue: 980, threshold, files: baselineFiles }, null, 2),
      'utf8'
    );
  }
  return dir;
}

const ARGS = ['--root', 'src', '--mode', 'fail', '--baseline', 'baseline.json'];

// ── 1. 主判据：真实仓库为绿 ──────────────────────────────────────────────
test('真实仓库 + 真实基线：exit 0（存量不误伤）', () => {
  const { code, out } = run(join(root, 'frontend'), [
    '--threshold',
    '400',
    '--mode',
    'fail',
    '--baseline',
    '../scripts/vue-size-baseline.json',
  ]);
  assert.equal(code, 0, `真实仓库应为绿，实际 exit ${code}\n${out}`);
  assert.match(out, /通过：存量 \d+ 项基线内无回涨/);
});

test('真实基线里的 key 一律是 POSIX 分隔符（否则 CI 上假绿）', () => {
  const b = JSON.parse(readFileSync(realBaseline, 'utf8'));
  const keys = Object.keys(b.files);
  // 空基线是**合法终点**：#980 把所有超阈文件都降到 400 行以下后，基线就该是空的
  // （2026-10-27 批 B11 起如此）。这里不再要求非空——但那也不等于门禁失效：
  // 「新增超阈文件」与「基线内文件回涨」两条变异探针在下面各自钉着，
  // 清空基线能绕过的是「存量记账」，绕不过「新文件必须 ≤400」。
  assert.ok(
    b.files !== null && typeof b.files === 'object' && !Array.isArray(b.files),
    'baseline.files 必须是对象'
  );
  const backslashed = keys.filter(k => k.includes('\\'));
  assert.deepEqual(backslashed, [], `基线 key 混入反斜杠：${backslashed.slice(0, 3).join(' | ')}`);
  assert.equal(b.threshold, 400);
  assert.equal(b.issue, 980);
});

// ── 2. 变异探针：回涨必须红 ──────────────────────────────────────────────
test('探针：基线内文件涨 1 行 → [GROW] 红（exit 1）', () => {
  const dir = sandbox({
    files: { 'views/Big.vue': 401, 'views/Small.vue': 10 },
    baselineFiles: { 'views/Big.vue': 400, 'views/Small.vue': 10 },
  });
  const { code, out } = run(dir, ARGS);
  assert.equal(code, 1, `回涨应判红，实际 exit ${code}\n${out}`);
  assert.match(out, /\[GROW\] views\/Big\.vue 401 行（基线 400，\+1）/);
});

test('探针：新增超阈文件（基线里没有）→ [NEW] 红（exit 1）', () => {
  const dir = sandbox({
    files: { 'views/NewGod.vue': 900 },
    baselineFiles: {},
  });
  const { code, out } = run(dir, ARGS);
  assert.equal(code, 1, `新增超阈应判红，实际 exit ${code}\n${out}`);
  assert.match(out, /\[NEW\]\s+views\/NewGod\.vue 900 行/);
});

test('探针：新增文件未超阈 → 绿（阈值内不该被拦）', () => {
  const dir = sandbox({ files: { 'views/NewOk.vue': 400 }, baselineFiles: {} });
  const { code, out } = run(dir, ARGS);
  assert.equal(code, 0, `400 行恰好等于阈值，不应判红，实际 exit ${code}\n${out}`);
});

// ── 3. 防假红：拆小了不许被拦 ────────────────────────────────────────────
test('拆小了（仍超阈值但比基线小）→ 绿，并提示可收紧', () => {
  const dir = sandbox({
    files: { 'views/Shrunk.vue': 420 },
    baselineFiles: { 'views/Shrunk.vue': 460 },
  });
  const { code, out } = run(dir, ARGS);
  assert.equal(code, 0, `拆小了反被判红，闸门会被绕开\n${out}`);
  assert.match(out, /已从 460 降到 420 行/);
});

test('拆到阈值以内 → 绿，并提示移出基线', () => {
  const dir = sandbox({
    files: { 'views/Gone.vue': 380 },
    baselineFiles: { 'views/Gone.vue': 900 },
  });
  const { code, out } = run(dir, ARGS);
  assert.equal(code, 0, out);
  assert.match(out, /已降到 380 行（≤ 400），可用 --update-baseline 移出基线/);
});

// ── 4. 防假绿：拿不到输入必须 exit 2 ────────────────────────────────────
test('基线文件缺失（校验模式）→ exit 2，不得当成通过', () => {
  const dir = sandbox({ files: { 'views/A.vue': 10 } });
  const { code, out } = run(dir, ['--root', 'src', '--mode', 'fail', '--baseline', 'nope.json']);
  assert.equal(code, 2, `基线缺失应 exit 2，实际 ${code}\n${out}`);
  assert.match(out, /读不到基线文件/);
});

test('基线 JSON 损坏 → exit 2', () => {
  const dir = sandbox({ files: { 'views/A.vue': 10 }, rawBaseline: '{ not json' });
  const { code, out } = run(dir, ARGS);
  assert.equal(code, 2, out);
  assert.match(out, /解析失败/);
});

test('基线条目非正整数 → exit 2', () => {
  const dir = sandbox({ files: { 'views/A.vue': 10 }, rawBaseline: JSON.stringify({ files: { 'views/A.vue': 0 } }) });
  const { code, out } = run(dir, ARGS);
  assert.equal(code, 2, out);
  assert.match(out, /基线条目非法/);
});

test('扫描根目录不存在 → exit 2', () => {
  const dir = sandbox({ files: {} });
  const { code, out } = run(dir, ['--root', 'no-such-src', '--mode', 'fail', '--baseline', 'baseline.json']);
  assert.equal(code, 2, out);
  assert.match(out, /扫描根目录不存在/);
});

test('阈值口径冲突（命令行 ≠ 基线）→ exit 2', () => {
  const dir = sandbox({ files: { 'views/A.vue': 500 }, baselineFiles: { 'views/A.vue': 500 }, threshold: 400 });
  const { code, out } = run(dir, [...ARGS, '--threshold', '300']);
  assert.equal(code, 2, out);
  assert.match(out, /阈值口径冲突/);
});

// ── 5. --update-baseline：只允许下调 ────────────────────────────────────
test('--update-baseline 拒绝上调：exit 2 且文件未被改写', () => {
  const dir = sandbox({
    files: { 'views/Big.vue': 600 },
    baselineFiles: { 'views/Big.vue': 500 },
  });
  const before = readFileSync(join(dir, 'baseline.json'), 'utf8');
  const { code, out } = run(dir, [...ARGS, '--update-baseline']);
  assert.equal(code, 2, `上调基线必须被拒，实际 exit ${code}\n${out}`);
  assert.match(out, /拒绝写入：基线只能下调/);
  assert.equal(readFileSync(join(dir, 'baseline.json'), 'utf8'), before, '被拒时不得留下半写状态');
});

test('--update-baseline 允许下调，并移除已缩小的条目', () => {
  const dir = sandbox({
    files: { 'views/Big.vue': 450, 'views/Gone.vue': 380 },
    baselineFiles: { 'views/Big.vue': 700, 'views/Gone.vue': 900 },
  });
  const { code, out } = run(dir, [...ARGS, '--update-baseline']);
  assert.equal(code, 0, `下调应被接受，实际 exit ${code}\n${out}`);
  const after = JSON.parse(readFileSync(join(dir, 'baseline.json'), 'utf8'));
  assert.equal(after.files['views/Big.vue'], 450, '应收紧到实测值');
  assert.ok(!('views/Gone.vue' in after.files), '已降到阈值内的条目应被移出基线');
});

test('--update-baseline 首次建立基线（文件原本不存在）→ 直接生成', () => {
  const dir = sandbox({ files: { 'views/Big.vue': 800, 'views/Ok.vue': 100 } });
  const { code, out } = run(dir, ['--root', 'src', '--mode', 'fail', '--baseline', 'fresh.json', '--update-baseline']);
  assert.equal(code, 0, out);
  const created = JSON.parse(readFileSync(join(dir, 'fresh.json'), 'utf8'));
  assert.deepEqual(created.files, { 'views/Big.vue': 800 }, '只登记超阈文件');
});

// ── 6. 兼容旧行为：不给基线时仍按阈值判红 ───────────────────────────────
test('不给 --baseline：fail 模式按阈值判红（旧行为不变）', () => {
  const dir = sandbox({ files: { 'views/Big.vue': 500 } });
  const { code, out } = run(dir, ['--root', 'src', '--mode', 'fail']);
  assert.equal(code, 1, out);
  assert.match(out, /1 个文件超出阈值/);
});

test('不给 --baseline：warn 模式始终 exit 0', () => {
  const dir = sandbox({ files: { 'views/Big.vue': 500 } });
  const { code } = run(dir, ['--root', 'src', '--mode', 'warn']);
  assert.equal(code, 0);
});
