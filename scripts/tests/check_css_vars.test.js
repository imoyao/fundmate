/**
 * `scripts/check_css_vars.mjs` 的回归网（#1602）
 *
 * 为什么需要：这个守卫决定 CI 红/绿，而它的第一版**抓不到自引用**
 * （`--x: var(--x)` 在旧实现里既是「定义」又是「使用」，天然自洽），
 * 于是 `design-tokens.css` 里 14 个令牌被自引用覆盖成无效值，
 * 仅靠 `main.ts` 二次导入 colors.css 才侥幸生效 —— 没有任何机制能发现。
 *
 * 做法：临时目录造 `scripts/` + `frontend/src/`，把真脚本复制进去
 * （脚本以自身位置的上一级为 ROOT），子进程跑真入口，断言退出码与输出。
 * 零新依赖（只用 node:test / node:assert）。
 */
const { test } = require("node:test");
const assert = require("node:assert/strict");
const { execFileSync } = require("node:child_process");
const { mkdtempSync, mkdirSync, writeFileSync, copyFileSync } = require("node:fs");
const { tmpdir } = require("node:os");
const { join } = require("node:path");

const REAL_SCRIPT = join(__dirname, "..", "check_css_vars.mjs");

/** 造一个隔离仓：<tmp>/scripts/check_css_vars.mjs + <tmp>/frontend/src/style/ 下的夹具。 */
function makeRepo(fixture) {
  const root = mkdtempSync(join(tmpdir(), "cvars-"));
  mkdirSync(join(root, "scripts"), { recursive: true });
  mkdirSync(join(root, "frontend", "src", "style"), { recursive: true });
  copyFileSync(REAL_SCRIPT, join(root, "scripts", "check_css_vars.mjs"));
  writeFileSync(join(root, "frontend", "src", "style", "fixture.css"), fixture);
  return root;
}

/** 跑真脚本，返回 { code, out }（不抛异常）。 */
function run(root) {
  try {
    const out = execFileSync(process.execPath, [join(root, "scripts", "check_css_vars.mjs")], {
      cwd: root,
      encoding: "utf8",
      stdio: ["ignore", "pipe", "pipe"]
    });
    return { code: 0, out };
  } catch (e) {
    return { code: e.status ?? 1, out: `${e.stdout ?? ""}${e.stderr ?? ""}` };
  }
}

/* ── 正向：全是正常别名，必须通过 ─────────────────────────────── */
test("正向：换名别名（左右不同名）与普通声明不报错", () => {
  const root = makeRepo(`
:root {
  --bg-page: #fdfbf7;
  --text-primary: #2d2a24;
  --brand: var(--brand-700);
  --brand-700: #e34f38;
  --shadow-card: var(--shadow-raised);
  --shadow-raised: 0 1px 2px rgb(0 0 0 / 10%);
}
`);
  const { code, out } = run(root);
  assert.equal(code, 0, `应通过，实际输出：\n${out}`);
  assert.match(out, /CSS 令牌引用检查通过/);
});

/* ── 反向①：单行自引用 ──────────────────────────────────────── */
test("反向①：单行 `--x: var(--x)` 必须报错", () => {
  const root = makeRepo(`
:root {
  --bg-page: #fdfbf7;
  --bg-card: var(--bg-card);
}
`);
  const { code, out } = run(root);
  assert.equal(code, 1, `应红灯，实际 exit=${code}\n${out}`);
  assert.match(out, /自引用/);
  assert.match(out, /--bg-card/);
  assert.match(out, /fixture\.css:4/, "应给出准确行号");
});

/* ── 反向②：跨行声明的自引用（rgba 换行写法）──────────────────── */
test("反向②：跨行声明里的自引用也要被抓到", () => {
  const root = makeRepo(`
:root {
  --tint: #ffffff;
  --overlay: rgba(
    10,
    20,
    30,
    var(--overlay)
  );
}
`);
  const { code, out } = run(root);
  assert.equal(code, 1, `应红灯，实际 exit=${code}\n${out}`);
  assert.match(out, /--overlay/);
});

/* ── 反向③：带 fallback 的自引用同样是循环 ──────────────────── */
test("反向③：`var(--x, fallback)` 形式的自引用同样算循环", () => {
  const root = makeRepo(`
:root {
  --safe: #123456;
  --danger: var(--danger, #ff0000);
}
`);
  const { code, out } = run(root);
  assert.equal(code, 1, `应红灯，实际 exit=${code}\n${out}`);
  assert.match(out, /--danger/);
});

/* ── 防过度抑制①：引用同族但不同名的令牌，不得误报 ────────────── */
test("防过度抑制①：`--spacing-md: var(--space-3)` 这类近似名不得误报", () => {
  const root = makeRepo(`
:root {
  --space-3: 12px;
  --spacing-md: var(--space-3);
  --radius-button: var(--radius-sm);
  --radius-sm: 6px;
  --text-mono: 16px;
}
`);
  const { code, out } = run(root);
  assert.equal(code, 0, `不得误报，实际 exit=${code}\n${out}`);
  assert.ok(!/自引用/.test(out), "不应出现自引用告警");
});

/* ── 防过度抑制②：豁免指令必须有效（带理由）─────────────────── */
test("防过度抑制②：带 `css-vars-ok:` 的显式豁免应被尊重", () => {
  const root = makeRepo(`
:root {
  --el-bg-color: #ffffff;
}
.el-divider__text {
  /* css-vars-ok: 有意让本元素该变量失效，使背景回退透明（既有行为） */
  --el-bg-color: var(--el-bg-color);
}
`);
  const { code, out } = run(root);
  assert.equal(code, 0, `豁免应生效，实际 exit=${code}\n${out}`);
  assert.ok(!/自引用/.test(out));
});

/* ── 防过度抑制③：豁免不得跨声明泄漏 ───────────────────────── */
test("防过度抑制③：豁免指令只作用于紧邻的那条声明", () => {
  const root = makeRepo(`
:root {
  --a: #111111;
  /* css-vars-ok: 只豁免紧随其后的那一条 */
  --b: var(--b);
  --c: var(--c);
}
`);
  const { code, out } = run(root);
  assert.equal(code, 1, `--c 无豁免应被报出，实际 exit=${code}\n${out}`);
  assert.ok(!/  --b  /.test(out), `--b 已豁免，不应出现：\n${out}`);
  assert.match(out, /--c/);
});

/* ── 防过度抑制④：幽灵令牌检测没被新逻辑破坏 ───────────────── */
test("防过度抑制④：幽灵令牌（引用未定义）仍然报错", () => {
  const root = makeRepo(`
:root {
  --known: #ffffff;
}
.foo {
  color: var(--not-defined-anywhere);
}
`);
  const { code, out } = run(root);
  assert.equal(code, 1, `幽灵令牌应红灯，实际 exit=${code}\n${out}`);
  assert.match(out, /--not-defined-anywhere/);
});

/* ── 防过度抑制⑤：el-/pure-/tw- 白名单仍生效（幽灵检测）─────── */
test("防过度抑制⑤：外部库前缀不被当作幽灵令牌", () => {
  const root = makeRepo(`
:root {
  --known: #ffffff;
}
.foo {
  color: var(--el-text-color-primary);
  background: var(--pure-border-color);
}
`);
  const { code, out } = run(root);
  assert.equal(code, 0, `外部前缀应白名单，实际 exit=${code}\n${out}`);
});
