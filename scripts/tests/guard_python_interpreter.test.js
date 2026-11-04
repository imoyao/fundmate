/**
 * 「Python 守卫的解释器探测」回归网（源 #119；2026-10-24 改为推导式名单 + 单一实现）。
 *
 * ## 为什么有这份文件
 *
 * `scripts/tests/` 下有多条回归网靠子进程跑 Python 守卫脚本。它们原先都写死
 * `process.env.PYTHON || "python"`，而 `python` 这个命令**不是处处都有**
 * （Debian/Ubuntu 只有 `python3`；本仓 CNB 工作区、WSL、多数容器皆如此）。
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
 * ## 2026-10-24：为什么把「手写名单 + 必须本地定义 findPython」换掉
 *
 * 上一版判据是「名单里的文件**各自**定义一个 `findPython()`」，名单还手写在 `GUARDED`
 * 数组里。两条都错，且错得互补，正好让漏点长期不可见：
 *
 *   - **判据本身在鼓励复制粘贴**：它要求每个文件本地有一份 `findPython`，于是同一段
 *     探测逻辑被抄了 6 份，改一处只修到一处（修不齐 = 剩下的继续假绿）；
 *   - **名单外的文件它完全看不见**：当时另有 4 个文件干脆硬写 `spawnSync("python3")`，
 *     名单里没有 ⇒ 判据绿着，而它们在本机（Windows，只有 `python`）上全红。
 *
 * 现在：解释器探测只有 `_python-interpreter.mjs` 一份实现，**名单从源码推导**
 * （扫 `scripts/tests/*.test.js`，看谁真的在拉 Python 子进程），判据改成
 * 「必须接线到共享 helper、不得本地再定义、不得硬写解释器名」。
 *
 * ## 判据（五条 + 一条自检）
 *
 *   1. 推导式名单**不得为空**——空名单等于「零命中 = 通过」，是最容易假绿的一种写法；
 *   2. 名单文件都必须 `import` 共享 helper，且**不得**本地再定义探测函数；
 *   3. 名单文件**不得**出现 `spawnSync("python3"` / `spawnSync("python"` 这类硬写字面量；
 *   4. 探测函数在 `$PYTHON` 无效时必须**回退**到 `python3` / `python`，而不是直接认栽；
 *   5. 「解释器一个都找不到」时名单文件必须**显式抛错**，绝不能把断言放过去。
 *
 * 判据 5 是核心。它用**受限 PATH** 真跑一遍子进程验证（不是静态读代码）：
 * 在 `PATH` 里放一个空目录、再显式清掉 `PYTHON`，名单里的回归网都必须以「找不到 Python」
 * 报错退出。旧代码在同条件下是 19 pass / 11 fail（假绿），新代码是 0 pass / 报错。
 *
 * 外加一条**自检**（判据 6）：把「硬写解释器名」的文件塞进临时目录，推导器必须认出它、
 * 判据必须报出它。没有这条，「推导正则被改坏 ⇒ 名单空转」就只会表现为一片绿。
 *
 * ⚠️ **子进程不能再带 `--test`**：`node:test` 检测到「在测试文件里又起了一个 test runner」
 * 后会打印 `node:test run() is being called recursively within a test file. skipping running
 * files.` 并**直接退出码 0、零输出**——本探针第一版正是踩了这个，看到「退出码 0」误判成
 * 「假绿回潮」。裸跑模块文件（把断言跑在真实环境里）才是这里要的行为，判据也不会被
 * harness 的自我跳过污染。
 *
 * ⚠️ **本文件把自己排除在名单外**：它只 `spawnSync(node)` 起子进程 + 读源码，从不拉 Python，
 * 且它的判据 5 正是「跑同类文件」。若把自身也列进名单，判据 5 会去裸跑自己 ——
 * 那是一份「自己验自己」的恒真探针（它在空 PATH 下不会抛「找不到解释器」，因为它的
 * 顶层并不调用 `pythonOrFail()`），除了自欺没有别的作用。
 *
 * ## 怎么跑
 *
 *     node --test "scripts/tests/*.test.js"     # 或根目录 `pnpm test:scripts`
 *
 * 零新依赖（只用 Node 内置 node:test / node:assert）。
 */
import { spawnSync } from "node:child_process";
import { existsSync, mkdtempSync, readdirSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { basename, join, relative } from "node:path";
import assert from "node:assert/strict";
import test from "node:test";

const ROOT = process.cwd();
const TESTS_DIR = join(ROOT, "scripts", "tests");
const SELF_NAME = "guard_python_interpreter.test.js";
const HELPER = join(TESTS_DIR, "_python-interpreter.mjs");

const read = (abs) => readFileSync(abs, "utf8");

/**
 * 剔除注释后再判判据。
 *
 * 为什么必须剔：本文件、以及各回归网的文件头都在**讲**旧写法（`process.env.PYTHON || "python"`、
 * `spawnSync("python3"`），不剔注释就会把这些讲解当成活代码，判据立刻自咬
 * （AGENTS「正则/字符串类判据的两个常见错」：先 stripComments 再匹配）。
 * 只剔块注释与整行行注释，字符串字面量**不动**（硬写的解释器名正是字符串）。
 */
function stripComments(src) {
  return src.replace(/\/\*[\s\S]*?\*\//g, "").replace(/^\s*\/\/.*$/gm, "");
}

/** 真的起子进程（否则「拉 Python」无从谈起）。 */
const SPAWN = /spawnSync\(|execFileSync\(/;

/**
 * 「这一行/这一段确实在拉 Python」的证据。四条取其一，宁宽勿窄——窄了就是漏点：
 *
 *   a. 引用了共享 helper 本身（改造过的文件）；
 *   b. 出现了探测结果变量 / 探测函数名（`PY_BIN` / `PY_ARGS` / `PYTHON` / `pythonOrFail` …）；
 *   c. 解释器名就写在 spawn 的第一个参数上（这正是要抓的硬写形态）；
 *   d. 出现了 `.py` 路径字面量（`"scripts/check_cnb_events.py"`）。
 *
 * 判据宁可宽：误收一个文件，成本只是「它必须接上 helper」；漏掉一个，成本是一整片假绿。
 */
const PY_EVIDENCE = new RegExp(
  [
    String.raw`_python-interpreter\.mjs`,
    String.raw`\b(?:pythonOrFail|findPython|PY_BIN|PY_ARGS|PYTHON)\b`,
    String.raw`(?:spawnSync|execFileSync)\s*\(\s*["'\`](?:python3?|py)["'\`]`,
    String.raw`["'\`][^"'\`\n]*\.py["'\`]`,
  ].join("|")
);

/** 谓词：这份源码是不是「会拉 Python 子进程」（注释已剔除）。 */
function looksLikePythonRunner(code) {
  return SPAWN.test(code) && PY_EVIDENCE.test(code);
}

/**
 * 从源码推导名单（**不手写**：手写的名单会自动与新增文件脱节，这正是上一版的漏点）。
 *
 * @param {string} dir 扫描目录（默认 `scripts/tests`；自检用例会传临时目录）。
 * @returns {string[]} 绝对路径，升序。
 * @throws 目录读不到 / 推导为空时**必须抛**——「拿不到输入」和「输入为空」都不能
 *   退化成「零命中 = 通过」（AGENTS 三之二：判据必须有失败态）。
 */
function deriveGuarded(dir = TESTS_DIR) {
  if (!existsSync(dir)) {
    throw new Error(
      `读不到目录 ${dir}：推导名单的输入都拿不到，本次结论不可信。` +
        "（不得因此把名单当成空、更不能据此报「通过」）"
    );
  }
  const files = readdirSync(dir)
    .filter((f) => f.endsWith(".test.js"))
    .sort();

  const out = [];
  for (const f of files) {
    // 自身排除的理由见文件头「本文件把自己排除在名单外」。
    if (f === SELF_NAME) continue;
    const abs = join(dir, f);
    if (looksLikePythonRunner(stripComments(read(abs)))) out.push(abs);
  }

  if (out.length === 0) {
    throw new Error(
      `推导结果为空（扫了 ${dir}）——一个「会拉 Python 子进程」的回归网都没认出来。\n` +
        "要么推导规则被改坏了，要么这些文件全被删了；两种都不该报「通过」。\n" +
        "若确实已无 Python 回归网，请连同本文件一起删掉，别留一个恒绿的空判据。"
    );
  }
  return out;
}

const GUARDED = deriveGuarded();
const rel = (abs) => relative(ROOT, abs).replace(/\\/g, "/");

/** 判据 2/3 的公共实现：返回「接线问题」清单（空数组 = 合格）。 */
function wiringProblems(src) {
  const code = stripComments(src);
  const problems = [];

  const imp = code.match(/import\s*\{([^}]*)\}\s*from\s*["']\.\/_python-interpreter\.mjs["']/);
  if (!imp) {
    problems.push("没有 import 共享 helper（./_python-interpreter.mjs）——探测逻辑只许有一份");
  } else if (!/\b(?:findPython|pythonOrFail)\b/.test(imp[1])) {
    problems.push(`import 了 helper 却没取探测函数（实际取了：{${imp[1].trim()}}）`);
  }
  if (/function\s+(?:findPython|pythonOrFail)\s*\(/.test(code)) {
    problems.push("又本地定义了一份探测函数——这是第 2~N 份拷贝的起点");
  }
  if (/(?:spawnSync|execFileSync)\s*\(\s*["'`](?:python3?|py)["'`]/.test(code)) {
    problems.push(
      '硬写了解释器名（spawnSync("python3" / spawnSync("python"）——' +
        "在另一类环境里必然 ENOENT，放行断言会因「什么都没跑」全部假通过"
    );
  }
  if (/process\.env\.PYTHON\s*\|\|\s*["']python3?["']/.test(code)) {
    problems.push('又写死了 process.env.PYTHON || "python"');
  }
  return problems;
}

/* ---------- 判据 1（推导） + 判据 2/3（接线）：不得硬写、不得各写一份 ---------- */

test("名单从源码推导，且名单里的回归网都接线到唯一的探测模块", () => {
  // 推导非空由 deriveGuarded 自己保证（空即抛），这里再钉一次「确实认出了一些东西」。
  assert.ok(GUARDED.length > 0, "推导名单为空 —— 判据等于空转");

  const bad = [];
  for (const abs of GUARDED) {
    const problems = wiringProblems(read(abs));
    if (problems.length > 0) bad.push(`${rel(abs)}：\n  - ${problems.join("\n  - ")}`);
  }
  assert.deepEqual(bad, [], `以下回归网没有接线到共享探测模块：\n${bad.join("\n")}`);
});

/* ---------- 判据 4：$PYTHON 无效时必须回退，而不是直接认栽 ---------- */

test("探测函数：$PYTHON 指向不存在的命令时回退到真实解释器", () => {
  // 从**共享实现**里把函数体抠出来真跑一遍（不是复刻逻辑——复刻等于抄一份，抄错的才绿）。
  const src = read(HELPER);
  const body = extractFunction(src, "findPython");
  assert.ok(body, `在 ${rel(HELPER)} 里找不到 findPython() 的函数体，判据失效，请更新本探针`);

  // 探针跑在 `node -e`（CJS）里，故用 helper 的「底部统一 export」形态：
  // 抠出来的正文是纯 `function …{}`，不带 `export` 前缀，可直接求值。
  const probe = `
const { spawnSync } = require("node:child_process");
${body}
const found = findPython();
console.log(JSON.stringify(found));
`;
  const r = spawnSync(process.execPath, ["-e", probe], {
    encoding: "utf8",
    env: { ...process.env, PYTHON: "definitely-not-a-real-python-xyz" },
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

/* ---------- 判据 5（核心）：一个解释器都找不到时，必须报错而非假绿 ---------- */

test("PATH 里没有 Python 时，名单里的回归网都必须显式报错（不得静默绿）", () => {
  // 造一个空目录当 PATH：既保证 `python3` / `python` 都找不到，又保留 node 自身
  // （node 用绝对路径调用，子进程 spawn 时用的是 PATH，故 node 不受影响）。
  const emptyDir = mkdtempSync(join(tmpdir(), "no-python-"));
  const env = { ...process.env, PATH: emptyDir };
  delete env.PYTHON;

  for (const abs of GUARDED) {
    // 裸跑模块文件（不带 --test）：见文件头「子进程不能再带 --test」的说明。
    // 该测试文件在模块加载期就抛错，故无需跑到用例就能判定。
    const r = spawnSync(process.execPath, [abs], { encoding: "utf8", env });
    const out = (r.stdout || "") + (r.stderr || "");

    assert.notEqual(r.status, 0, `${rel(abs)} 在无解释器环境下竟然退出码 0 —— 假绿回潮了`);
    assert.match(
      out,
      /找不到 Python 解释器/,
      `${rel(abs)} 没有显式报出「找不到解释器」，而是让断言自己崩：\n${out.slice(0, 800)}`
    );
    // 反向钉住：旧行为在探测不到解释器时是「跑起来但断言假通过」。
    // 新行为必须是**模块加载期就失败**，一个用例都不执行。
    assert.doesNotMatch(
      out,
      /^ℹ pass [1-9]/m,
      `${rel(abs)} 在无解释器时仍有用例「通过」——那些正是假绿：\n${out.slice(0, 800)}`
    );
  }
});

/* ---------- 判据 6：推导器自身的失败态 ---------- */

test("推导器的失败态：输入拿不到 / 推导为空时必须报错，不得当成「零命中 = 通过」", () => {
  const emptyDir = mkdtempSync(join(tmpdir(), "no-tests-"));
  assert.throws(
    () => deriveGuarded(emptyDir),
    /推导结果为空/,
    "目录里一个候选都没有时，推导器没有报错 —— 它会把「名单为空」当成「全部合格」"
  );
  assert.throws(
    () => deriveGuarded(join(emptyDir, "does-not-exist")),
    /读不到目录/,
    "目录读不到时，推导器没有报错 —— 「拿不到输入」被静默降级成了「没有要检查的东西」"
  );
});

/* ---------- 判据 7：自检——把硬写形态塞进临时目录，推导与判据都必须咬住 ---------- */

test("自检：硬写解释器名 / 本地再抄一份探测函数的文件，必须被认出并报出问题", () => {
  const dir = mkdtempSync(join(tmpdir(), "hardcoded-py-"));
  writeFileSync(
    join(dir, "hardcoded.test.js"),
    [
      'import { spawnSync } from "node:child_process";',
      'const r = spawnSync("python3", ["scripts/check_cnb_events.py"]);',
      "",
    ].join("\n"),
    "utf8"
  );
  const derived = deriveGuarded(dir);
  assert.equal(derived.length, 1, "硬写 spawnSync(\"python3\") 的文件没被推导器认出来 —— 漏点回来了");

  const problems = wiringProblems(read(derived[0]));
  assert.ok(
    problems.some((p) => p.includes("硬写了解释器名")),
    `推导器认出了文件，但判据没报「硬写解释器名」：${JSON.stringify(problems)}`
  );
  assert.ok(
    problems.some((p) => p.includes("没有 import 共享 helper")),
    `判据没报「没接线到共享 helper」：${JSON.stringify(problems)}`
  );

  // 另一条独立的漏点：本地又抄一份探测函数（上一版判据**要求**这样做，所以必须反向钉住）。
  writeFileSync(
    join(dir, "copycat.test.js"),
    [
      'import { spawnSync } from "node:child_process";',
      "function findPython() { return null; }",
      'const r = spawnSync("scripts/check_cnb_events.py");',
      "",
    ].join("\n"),
    "utf8"
  );
  const withCopy = deriveGuarded(dir).find((p) => basename(p) === "copycat.test.js");
  assert.ok(withCopy, "本地抄了一份 findPython 的文件没被推导器认出来");
  assert.ok(
    wiringProblems(read(withCopy)).some((p) => p.includes("又本地定义了一份探测函数")),
    "判据没报「本地又定义了一份探测函数」——复制粘贴这条回潮路又通了"
  );
});

/* ---------- 工具：按**花括号配对**抠函数体（不按缩进，AGENTS 记着这个坑） ---------- */

/**
 * 从源码里取出 `function <name>(` 起、到配对花括号为止的整段。
 *
 * 为什么不用 `/function findPython\(\)\s*\{[\s\S]*?\n\}/`：那按缩进猜结尾，
 * 函数体里只要出现一行顶格就截错（AGENTS「正则/字符串类判据的两个常见错」第一错）。
 * 这里数花括号，字符串 / 注释里的括号先遮掉再数。
 */
function extractFunction(src, name) {
  const start = src.indexOf(`function ${name}(`);
  if (start === -1) return null;
  const open = src.indexOf("{", start);
  if (open === -1) return null;

  // 遮掉字符串与注释中的花括号，避免把 `"{"` 当成结构。
  const masked = src
    .slice(open)
    .replace(/\/\*[\s\S]*?\*\//g, (m) => m.replace(/[{}]/g, "_"))
    .replace(/^\s*\/\/.*$/gm, (m) => m.replace(/[{}]/g, "_"))
    .replace(/(["'`])(?:\\.|(?!\1)[^\\])*\1/g, (m) => m.replace(/[{}]/g, "_"));

  let depth = 0;
  for (let i = 0; i < masked.length; i++) {
    if (masked[i] === "{") depth++;
    else if (masked[i] === "}") {
      depth--;
      if (depth === 0) return src.slice(start, open + i + 1);
    }
  }
  return null;
}
