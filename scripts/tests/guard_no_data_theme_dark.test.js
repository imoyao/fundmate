/**
 * `scripts/guard_no_data_theme_dark.mjs` 的回归网（node:test，零新依赖）。
 *
 * 覆盖三件事，缺一条这个判据就不成立（AGENTS.md「守门通过 ≠ 守门有效」）：
 *
 * 1. **真实全仓扫描零命中** —— 死代码确实删干净了，且判据在真实代码上跑得通；
 * 2. **注入探针** —— 把死选择器注进**临时副本**喂守卫，必须 exit 1 并报出行号。
 *    三种写法（双引号 / 单引号 / 无引号）各一条：判据不能只拟合当初那一种长相。
 *    ⚠️ 探针只动临时目录里的副本，**绝不改真实文件**。
 * 3. **失败态探针** —— 目录不存在 / 目录里一个可扫文件都没有，必须 exit 2 并明说
 *    「结论不可信」，**不得**退化成「零命中 = 通过」（AGENTS.md 三之二：假绿比红灯贵）。
 *
 * 另有两条防「判据扩宽」的反向探针：正经的配色主题选择器（showbuy）必须**不**被判红，
 * 否则守卫会天天误伤，红灯随之失去可信度。
 */
import { test } from "node:test";
import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "..", "..");
const GUARD = join(ROOT, "scripts", "guard_no_data_theme_dark.mjs");

/** 跑守卫，返回退出码 + 两路输出（中文一律按 utf8 读）。 */
function runGuard(args = []) {
  const r = spawnSync(process.execPath, [GUARD, ...args], { encoding: "utf8" });
  return { code: r.status, stdout: r.stdout ?? "", stderr: r.stderr ?? "" };
}

/** 建一个临时扫描根，写入若干相对路径文件；返回目录，用完请 rmSync。 */
function makeTmpRoot(files) {
  const dir = mkdtempSync(join(tmpdir(), "guard-data-theme-dark-"));
  for (const [rel, content] of Object.entries(files)) {
    const p = join(dir, rel);
    mkdirSync(dirname(p), { recursive: true });
    writeFileSync(p, content, "utf8");
  }
  return dir;
}

/** 构造一段「命中在第 hitLine 行」的样式文本，便于断言行号。 */
function withHitAt(hitLine, selector) {
  const before = Array.from({ length: hitLine - 1 }, (_, i) => `/* filler ${i + 1} */`);
  return [...before, `${selector} .money-display.is-rise {`, "  color: red;", "}"].join("\n");
}

test("真实仓库扫描：零命中，且确实扫到了源码（不是空扫描）", () => {
  const { code, stdout, stderr } = runGuard();
  assert.equal(code, 0, `真实扫描应通过，实际 exit ${code}；stderr=${stderr}`);

  const m = stdout.match(/扫描 (\d+) 个文件/);
  assert.ok(m, `输出里应报出扫描文件数，实际 stdout=${stdout}`);
  assert.ok(Number(m[1]) > 100, `扫描文件数 ${m[1]} 太少，判据的输入疑似写错了`);
  // 真实扫描里既不该有命中，也不该有「不可信」的失败态话术
  assert.ok(!stderr.includes("不可信"), `通过时不应出现失败态话术：${stderr}`);
});

test("注入探针：拿真实组件文件的副本注入死选择器，必被咬住（exit 1 + file:line）", () => {
  // 用**真实文件**的副本而不是手捏的样本：真实文件带 CRLF / scoped 块 / 多段样式，
  // 判据在样本上绿不算数，得在真实长相上绿。
  const real = join(ROOT, "frontend", "src", "components", "MoneyDisplay", "index.vue");
  const original = readFileSync(real, "utf8");
  const injected = original.replace(
    "</style>",
    '\n[data-theme="dark"] .money-display.is-rise {\n  color: var(--color-rise-ink);\n}\n</style>'
  );
  assert.notEqual(injected, original, "注入未生效（真实文件里找不到 </style>），探针本身失效");
  const expectedLine = injected.slice(0, injected.indexOf('[data-theme="dark"]')).split("\n").length;

  const dir = makeTmpRoot({ "components/MoneyDisplay/index.vue": injected });
  try {
    const { code, stdout, stderr } = runGuard(["--root", dir]);
    assert.equal(code, 1, `注入死选择器应 exit 1，实际 ${code}；stdout=${stdout}${stderr}`);
    const out = `${stdout}${stderr}`;
    assert.match(out, /components\/MoneyDisplay\/index\.vue/);
    assert.ok(
      out.includes(`:${expectedLine}`),
      `应报出行号 ${expectedLine}，实际输出：${out}`
    );
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
});

test("注入探针：单引号写法同样被咬住", () => {
  const dir = makeTmpRoot({
    "components/RiseFallText/index.vue": `<style scoped>\n${withHitAt(5, "[data-theme='dark']")}\n</style>\n`
  });
  try {
    const { code, stderr } = runGuard(["--root", dir]);
    assert.equal(code, 1, `单引号写法应 exit 1，实际 ${code}；stderr=${stderr}`);
    assert.match(stderr, /RiseFallText\/index\.vue:6/);
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
});

test("注入探针：无引号 / 大小写变体同样被咬住", () => {
  const dir = makeTmpRoot({
    "style/theme.scss": `${withHitAt(3, "[ data-theme = DARK ]")}\n`
  });
  try {
    const { code, stderr } = runGuard(["--root", dir]);
    assert.equal(code, 1, `无引号写法应 exit 1，实际 ${code}；stderr=${stderr}`);
    assert.match(stderr, /style\/theme\.scss:3/);
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
});

test("反向探针：正经的配色主题选择器不得误伤（showbuy / 带 .dark 类的组合）", () => {
  const dir = makeTmpRoot({
    "style/theme.scss": [
      'html[data-theme="showbuy"] {',
      "  --brand-700: #c0341f;",
      "}",
      ':root.dark[data-theme="showbuy"] {',
      "  --brand-700: #ef8a78;",
      "}",
      'html[data-theme="light"] {',
      "  --brand-700: #c0341f;",
      "}"
    ].join("\n")
  });
  try {
    const { code, stderr } = runGuard(["--root", dir]);
    assert.equal(code, 0, `配色主题选择器不应判红，实际 exit ${code}；stderr=${stderr}`);
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
});

test("失败态探针：目录不存在 → exit 2 且不得宣称通过", () => {
  const missing = join(tmpdir(), "guard-data-theme-dark-does-not-exist-2407");
  const { code, stdout, stderr } = runGuard(["--root", missing]);
  assert.equal(code, 2, `目录不存在应 exit 2，实际 ${code}；stdout=${stdout}`);
  assert.match(stderr, /不可信/);
  assert.doesNotMatch(stdout, /✓/, `失败态下不得打印通过标记，实际 stdout=${stdout}`);
});

test("失败态探针：目录存在但扫不到任何源码 → exit 2（零命中 ≠ 通过）", () => {
  const dir = makeTmpRoot({ "notes.txt": "no source here\n" });
  try {
    const { code, stdout, stderr } = runGuard(["--root", dir]);
    assert.equal(code, 2, `空扫描应 exit 2，实际 ${code}；stdout=${stdout}`);
    assert.match(stderr, /没有扫到任何/);
    assert.match(stderr, /不可信/);
    assert.doesNotMatch(stdout, /✓/, `失败态下不得打印通过标记，实际 stdout=${stdout}`);
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
});
