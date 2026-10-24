/**
 * `scripts/check_font_assets.py` 的回归网（node:test，零新依赖）。
 *
 * ## 为什么字体需要这道门
 *
 * 字体是**本机产物依赖**（MiSans 中文子集由本机子集化脚本产出，Inter 是裁剪产物）。
 * 它们提交进仓库，但**前端构建不校验它们**——`public/` 下的静态文件由 Vite 原样拷贝：
 * 字体缺失或被截断时 `pnpm build` 照样成功，页面照常渲染，只是静默 fallback 到系统字体。
 * CI 与本地长得不一样，却没有任何红灯（AGENTS.md 三之二：假绿比红灯贵）。
 *
 * ## 覆盖三件事，缺一条判据就不成立
 *
 * 1. **真实仓库零违规**——产物确实完好，且判据在真实文件上跑得通（不是空扫描假绿）；
 * 2. **变异探针**——把临时副本里的字体删掉 / 截断 / 改坏魔数 / 塞一个孤儿文件，
 *    喂守卫必须 exit 1 并报出**对应**原因（判据不能只认「有问题」，还得说清是什么问题）；
 * 3. **失败态探针**——根目录不存在时必须 exit 1 并明说「前端目录不存在」，
 *    **不得**退化成「零命中 = 通过」。
 *
 * ⚠️ 探针只动临时目录里的副本，**绝不改真实文件**。
 */
import { test } from "node:test";
import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { mkdirSync, mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { pythonOrFail } from "./_python-interpreter.mjs";

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "..", "..");
const GUARD = join(ROOT, "scripts", "check_font_assets.py");

// 解释器探测只此一份（`_python-interpreter.mjs`）。找不到就抛错，不许 skip——
// skip 的用例退出码仍是 0，「必须放行」的断言会因「什么都没跑」而恒真（#119 的教训）。
const PY = pythonOrFail();

/** 跑守卫，返回退出码 + 两路输出（中文一律按 utf8 读）。 */
function runGuard(args = []) {
  const r = spawnSync(PY[0], [...PY.slice(1), GUARD, ...args], { encoding: "utf8" });
  return { code: r.status, stdout: r.stdout ?? "", stderr: r.stderr ?? "" };
}

/** 造一个最小可用的字体仓库：public/fonts/x.woff2 + src/style/fonts.css 引用它。 */
function makeTmpRepo() {
  const dir = mkdtempSync(join(tmpdir(), "guard-font-"));
  const fontsDir = join(dir, "frontend", "public", "fonts");
  const styleDir = join(dir, "frontend", "src", "style");
  mkdirSync(fontsDir, { recursive: true });
  mkdirSync(styleDir, { recursive: true });
  // 合法 woff2：头 4 字节是 wOF2，后面垫够体积（守卫还查最小字节数）
  writeFileSync(join(fontsDir, "x.woff2"), Buffer.concat([Buffer.from("wOF2"), Buffer.alloc(2000)]));
  writeFileSync(
    join(styleDir, "fonts.css"),
    '@font-face { font-family: "X"; src: url("/fonts/x.woff2") format("woff2"); }\n'
  );
  return dir;
}

/** 临时仓库用完即删。 */
function cleanup(dir) {
  rmSync(dir, { recursive: true, force: true });
}

test("真实仓库：字体产物零违规（且确实扫到了产物，不是空扫描）", () => {
  const r = runGuard();
  assert.equal(r.code, 0, `守卫应通过，实际 stderr：${r.stderr}`);
  assert.match(r.stdout, /OK: 字体产物完整/);
  // 空扫描假绿防护：产物数必须 > 0
  const m = r.stdout.match(/完整（(\d+) 个产物/);
  assert.ok(m, `输出里应带产物数，实际：${r.stdout}`);
  assert.ok(Number(m[1]) > 0, "产物数为 0 = 扫描没扫到东西，属假绿");
});

test("变异探针①：删掉被引用的字体 → 必须报「不存在的文件」", () => {
  const dir = makeTmpRepo();
  try {
    rmSync(join(dir, "frontend", "public", "fonts", "x.woff2"));
    const r = runGuard(["--root", dir]);
    assert.equal(r.code, 1, "缺失字体必须 exit 1");
    assert.match(r.stderr, /不存在的文件/);
  } finally {
    cleanup(dir);
  }
});

test("变异探针②：字体被截断成 0 字节 → 必须报「截断」", () => {
  const dir = makeTmpRepo();
  try {
    writeFileSync(join(dir, "frontend", "public", "fonts", "x.woff2"), Buffer.alloc(0));
    const r = runGuard(["--root", dir]);
    assert.equal(r.code, 1, "截断字体必须 exit 1");
    assert.match(r.stderr, /截断|清空/);
  } finally {
    cleanup(dir);
  }
});

test("变异探针③：体积够但文件头不对 → 必须报「文件头不对」", () => {
  const dir = makeTmpRepo();
  try {
    // 头不是 wOF2（模拟被占位符替换 / 被写坏），体积仍过下限
    writeFileSync(join(dir, "frontend", "public", "fonts", "x.woff2"), Buffer.alloc(2000, 0x41));
    const r = runGuard(["--root", dir]);
    assert.equal(r.code, 1, "坏魔数必须 exit 1");
    assert.match(r.stderr, /文件头不对/);
  } finally {
    cleanup(dir);
  }
});

test("变异探针④：塞一个没人引用的孤儿字体 → 必须报「孤儿」", () => {
  const dir = makeTmpRepo();
  try {
    writeFileSync(
      join(dir, "frontend", "public", "fonts", "orphan.woff2"),
      Buffer.concat([Buffer.from("wOF2"), Buffer.alloc(2000)])
    );
    const r = runGuard(["--root", dir]);
    assert.equal(r.code, 1, "孤儿产物必须 exit 1");
    assert.match(r.stderr, /孤儿/);
  } finally {
    cleanup(dir);
  }
});

test("失败态：根目录不存在 → 必须 exit 1，不得退化成「零命中 = 通过」", () => {
  const dir = join(tmpdir(), "guard-font-missing-root-does-not-exist");
  const r = runGuard(["--root", dir]);
  assert.equal(r.code, 1, "根目录不存在必须 exit 1（假绿比红灯贵）");
  assert.match(r.stderr, /前端目录不存在/);
});
