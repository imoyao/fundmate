/**
 * 「Python 守卫的解释器探测」回归网（源 #119）。
 *
 * ## 为什么有这份文件
 *
 * `scripts/tests/` 下有多条回归网（`guard_a11y_interaction` / `guard_control_clip` /
 * `guard_col_divider`）靠子进程跑 Python 守卫脚本。它们原先都写死
 * `process.env.PYTHON || "python"`，
 * 而 `python` 这个命令**不是处处都有**（Debian/Ubuntu 只有 `python3`；本仓 CNB 工作区、
 * WSL、多数容器皆如此）。
 *
 * 后果不是「报错」，而是**静默绿**——`execFileSync` 抛 ENOENT，被 `catch` 拼成
 * `"spawnSync python ENOENT"` 返回，里面既没有命中标记也没有 `Traceback`，于是：
 *
 *   - 「必须命中」的断言失败（19/30、9/16）；
 *   - 「必须放行」的断言**全部假通过** —— 因为它们断言的是「输出里没有某标记」，
 *     而「什么都没跑」恰好满足这一条。
 *
 * 2026-10-11 实测：同一份代码只把 `python` 换成 `python3`，18 fail → 0 fail。
 * 这 18 个红灯在 CI（ubuntu-latest 自带 python 别名）上永远不出现，在本地却成片出现，
 * 每次都要人工判断「这 18 个要不要紧」——红灯可信度就是这样被消耗掉的。
 *
 * 本文件把这套机制钉住，判据三条：
 *   1. 名单里的回归网都**不得**再写死 `PYTHON || "python"`（必须走探测函数）；
 *   2. 探测函数必须在 `$PYTHON` 无效时**回退**到 `python3` / `python`，而不是直接认栽；
 *   3. 「解释器一个都找不到」时必须**显式抛错**，绝不能把断言放过去。
 *
 * 第 3 条是核心。它用**受限 PATH** 真跑一遍子进程验证（不是静态读代码）：
 * 在 `PATH` 里放一个空目录、再显式清掉 `PYTHON`，名单里的回归网都必须以「找不到 Python」
 * 报错退出。旧代码在同条件下是 19 pass / 11 fail（假绿），新代码是 0 pass / 报错。
 *
 * ⚠️ **子进程不能再带 `--test`**：`node:test` 检测到「在测试文件里又起了一个 test runner」
 * 后会打印 `node:test run() is being called recursively within a test file. skipping running
 * files.` 并**直接退出码 0、零输出**——本探针第一版正是踩了这个，看到「退出码 0」误判成
 * 「假绿回潮」。裸跑模块文件（把断言跑在真实环境里）才是这里要的行为，判据也不会被
 * harness 的自我跳过污染。
 *
 * ## 怎么跑
 *
 *     node --test "scripts/tests/*.test.js"     # 或根目录 `pnpm test:scripts`
 *
 * 零新依赖（只用 Node 内置 node:test / node:assert）。
 */
import { spawnSync } from "node:child_process";
import { readFileSync, mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import assert from "node:assert/strict";
import test from "node:test";

const ROOT = process.cwd();
const GUARDED = [
  "scripts/tests/guard_a11y_interaction.test.js",
  "scripts/tests/guard_control_clip.test.js",
  "scripts/tests/guard_col_divider.test.js"
];

const read = (rel) => readFileSync(join(ROOT, rel), "utf8");

/* ---------- 判据 1：不得再写死 PYTHON || python ---------- */

test("名单里的回归网都走解释器探测，不得写死 PYTHON || \"python\"", () => {
  for (const rel of GUARDED) {
    const src = read(rel);
    // 注释里会讲解旧写法，故只看「活代码」：剔除行注释与块注释后再匹配。
    const code = src
      .replace(/\/\*[\s\S]*?\*\//g, "")
      .replace(/^\s*\/\/.*$/gm, "")
      .replace(/`[^`]*`/g, (m) => m); // 保留模板串（含断言文案）不动
    assert.doesNotMatch(
      code,
      /process\.env\.PYTHON\s*\|\|\s*["']python["']/,
      `${rel} 又写死了 process.env.PYTHON || "python"：` +
        `在只有 python3 的环境里会让「必须放行」的断言全部假通过。`
    );
    assert.match(code, /function findPython\(/, `${rel} 缺少 findPython() 探测函数`);
  }
});

/* ---------- 判据 2：$PYTHON 无效时必须回退，而不是直接认栽 ---------- */

test("探测函数：$PYTHON 指向不存在的命令时回退到真实解释器", () => {
  // 提取 findPython 的函数体真跑一遍（不是复刻逻辑——复刻等于抄一份，抄错的才绿）。
  const src = read(GUARDED[0]);
  const m = src.match(/function findPython\(\)\s*\{[\s\S]*?\n\}/);
  assert.ok(m, "找不到 findPython() 函数体，判据失效，请更新本探针");

  const probe = `
const { spawnSync } = require("node:child_process");
${m[0]}
const found = findPython();
console.log(JSON.stringify(found));
`;
  const r = spawnSync(process.execPath, ["-e", probe], {
    encoding: "utf8",
    env: { ...process.env, PYTHON: "definitely-not-a-real-python-xyz" }
  });
  assert.equal(r.status, 0, `探测脚本自身失败：${r.stderr}`);
  const found = JSON.parse(r.stdout.trim());
  assert.ok(
    Array.isArray(found) && found.length > 0,
    "PYTHON 无效时探测应回退到 python3/python，实际返回 null —— " +
      "这会让开发者在设错环境变量时得到「找不到解释器」的错误结论"
  );
  // 回退到手的就是真能跑的解释器
  const v = spawnSync(found[0], [...found.slice(1), "--version"], { encoding: "utf8" });
  assert.equal(v.status, 0, "回退到的解释器跑不起来");
});

/* ---------- 判据 3（核心）：一个解释器都找不到时，必须报错而非假绿 ---------- */

test("PATH 里没有 Python 时，名单里的回归网都必须显式报错（不得静默绿）", () => {
  // 造一个空目录当 PATH：既保证 `python3` / `python` 都找不到，又保留 node 自身
  // （node 用绝对路径调用，子进程 spawn 时用的是 PATH，故 node 不受影响）。
  const emptyDir = mkdtempSync(join(tmpdir(), "no-python-"));
  const env = { ...process.env, PATH: emptyDir };
  delete env.PYTHON;

  for (const rel of GUARDED) {
    // 裸跑模块文件（不带 --test）：见文件头「子进程不能再带 --test」的说明。
    // 该测试文件在模块顶层就抛错，故无需跑到用例就能判定。
    const r = spawnSync(process.execPath, [join(ROOT, rel)], {
      encoding: "utf8",
      env
    });
    const out = (r.stdout || "") + (r.stderr || "");

    assert.notEqual(r.status, 0, `${rel} 在无解释器环境下竟然退出码 0 —— 假绿回潮了`);
    assert.match(
      out,
      /找不到 Python 解释器/,
      `${rel} 没有显式报出「找不到解释器」，而是让断言自己崩：\n${out.slice(0, 800)}`
    );
    // 反向钉住：旧行为在探测不到解释器时是「跑起来但断言假通过」。
    // 新行为必须是**模块加载期就失败**，一个用例都不执行。
    assert.doesNotMatch(
      out,
      /^ℹ pass [1-9]/m,
      `${rel} 在无解释器时仍有用例「通过」——那些正是假绿：\n${out.slice(0, 800)}`
    );
  }
});
