/**
 * `scripts/guard_ts_any.mjs` 的回归网（node:test，跟随 scripts/tests 既有 *.test.js 风格）。
 *
 * ## WHY
 *
 * 「只减不增」闸门最贵的失效形态是**永远绿**；更隐蔽的一种是**口径不同的假绿**：
 * 依赖缺失时降级正则曾数出 539 处（AST 是 540），却仍与同一份 AST 基线比对并
 * 返回 0「只减不增」。本网钉住四件事：
 *   1. 依赖缺失时 main() 必须返回 2、不得返回 0（防「降级静默绿」回潮）；
 *   2. 加一个 any 真转红 / 删一个 any 真放行并提示收紧（灵敏度正/反例）；
 *   3. 空输入、坏基线、--write 上调等失败态必须显式失败；
 *   4. 带 any 的新文件**未纳入基线**必须转红，且 --write 后能转绿（#2935）。
 *      旧实现只提示、exit 0，与「基线覆盖」用例口径相反 ⇒ 两个 PR 各自绿、
 *      合进 dev 才红，#2934 / #2936 都是事后补数据的止血卡。
 *
 * ## 怎么跑
 *
 *   node --test scripts/tests/guard_ts_any.test.js
 *
 * CI：由 `scripts_test` job 的 `node --test "scripts/tests/*.test.js"` 自动收；
 * 另在 frontend job 有一处显式 step（那里装了前端依赖）。
 *
 * ## 口径纪律（重要，别再把差异藏起来）
 *
 * 依赖 AST 的用例一律用 `{ skip: !AST_OK }` 跳过并写明原因——正式判据只在装了
 * typescript + @vue/compiler-sfc 的环境跑（frontend job / 本地 NODE_PATH）。
 * 沙箱基线是**显式钉死**的 AST 口径值（a.ts=4 / sub/b.vue=2 / clean.ts=0），
 * 不让守卫自己 --write 算一份「两种口径都自洽」的动态基线：那会把口径差异藏起来，
 * 而不是验证它。降级计数函数只在本网里作解析层纯函数测试，绝不参与结论。
 */

const { test } = require("node:test");
const assert = require("node:assert/strict");
const { spawnSync } = require("node:child_process");
const {
  existsSync,
  mkdirSync,
  mkdtempSync,
  readFileSync,
  rmSync,
  writeFileSync,
} = require("node:fs");
const { createRequire } = require("node:module");
const { tmpdir } = require("node:os");
const { join } = require("node:path");
const { pathToFileURL } = require("node:url");

const root = join(__dirname, "..", "..");
const script = join(root, "scripts", "guard_ts_any.mjs");
const realBaseline = join(root, "scripts", "ts-any-baseline.json");

// 与守卫同样的依赖解析链，判定本进程能不能走 AST。
const requireFrontend = createRequire(join(root, "frontend", "package.json"));
const requireSelf = createRequire(__filename);
function detectAst() {
  for (const req of [requireFrontend, requireSelf]) {
    try {
      const ts = req("typescript");
      const sfc = req("@vue/compiler-sfc");
      if (
        ts &&
        sfc &&
        typeof ts.createSourceFile === "function" &&
        typeof ts.forEachChild === "function" &&
        typeof sfc.parse === "function"
      )
        return true;
    } catch (e) {
      if (e.code !== "MODULE_NOT_FOUND") throw e;
    }
  }
  return false;
}
const AST_OK = detectAst();
const SKIP_NO_AST = AST_OK
  ? false
  : "需要 typescript + @vue/compiler-sfc（frontend job 已装依赖；本地可设 NODE_PATH）";

/** 跑守卫；返回 { code, out, err }（spawnSync 不抛错，退出码直接读 status）。 */
function run(args = [], env = {}) {
  const childEnv = { ...process.env };
  // 默认总是跑真实仓库；只有显式传沙箱 env 才切到临时目录。
  delete childEnv.GUARD_TS_ANY_SRC;
  delete childEnv.GUARD_TS_ANY_BASELINE;
  Object.assign(childEnv, env);
  const r = spawnSync(process.execPath, [script, ...args], {
    cwd: root,
    env: childEnv,
    encoding: "utf8",
    // shell 必须为 false：Windows 下交给 cmd 解析会静默吃掉参数（历史坑）。
    shell: false,
  });
  return {
    code: r.status,
    out: String(r.stdout || ""),
    err: String(r.stderr || ""),
  };
}

/**
 * 样本：a.ts 4 处 any、sub/b.vue 2 处 any、clean.ts 0 处。
 * 注释 / 字符串 / <template> 里的 "any" 都是刻意放的噪声——它们绝不该被计入。
 */
const SAMPLE = {
  "a.ts": [
    "const a: any = 1;",
    "const b = foo as any;",
    "// any any  ← 注释里的 any 不算",
    'const s = "any";  // 字符串里的 any 不算',
    "export const f = (x: any): any => x;",
  ].join("\n"),
  "sub/b.vue": [
    "<template><div>{{ any }}</div></template>",
    '<script setup lang="ts">',
    "const p: any = 1;",
    "const q: Array<any> = [];",
    "</script>",
  ].join("\n"),
  "clean.ts": "export const n: number = 1;",
};

/** 样本在 AST 口径下的实测计数——显式钉死，不让守卫 --write 自己算。 */
const AST_COUNTS = { "a.ts": 4, "sub/b.vue": 2, "clean.ts": 0 };

/** 造沙箱 + 显式写入 AST 口径基线，返回 { src, baseline, env }。 */
function withSandbox(files = SAMPLE, baseFiles = AST_COUNTS) {
  const dir = mkdtempSync(join(tmpdir(), "ts-any-guard-"));
  const src = join(dir, "src");
  mkdirSync(src, { recursive: true });
  for (const [rel, content] of Object.entries(files)) {
    const p = join(src, rel);
    mkdirSync(join(p, ".."), { recursive: true });
    writeFileSync(p, content, "utf8");
  }
  const baseline = join(dir, "baseline.json");
  writeFileSync(
    baseline,
    `${JSON.stringify({ issue: 2879, newFileAnyLimit: 0, files: baseFiles }, null, 2)}\n`,
    "utf8",
  );
  return {
    src,
    baseline,
    env: { GUARD_TS_ANY_SRC: src, GUARD_TS_ANY_BASELINE: baseline },
  };
}

test("真实基线 JSON 结构合法、键按路径字典序、计数为非负整数", () => {
  assert.ok(existsSync(realBaseline), "scripts/ts-any-baseline.json 必须存在");
  const b = JSON.parse(readFileSync(realBaseline, "utf8"));
  assert.equal(b.issue, 2879);
  assert.equal(b.newFileAnyLimit, 0);
  assert.ok(b.files && typeof b.files === "object" && !Array.isArray(b.files));
  const keys = Object.keys(b.files);
  assert.ok(keys.length > 0, "基线不应为空");
  assert.deepEqual(keys, [...keys].sort(), "基线条目必须按路径字典序");
  for (const [k, v] of Object.entries(b.files)) {
    assert.ok(
      Number.isInteger(v) && v >= 0,
      `${k} = ${JSON.stringify(v)} 须为非负整数`,
    );
  }
});

test("无 AST 依赖时 main() 必须返回 2，且不得返回 0（防降级静默绿回潮）", async () => {
  const guard = await import(pathToFileURL(script).href);
  // 注入 astOk:false 模拟依赖缺失——即便本进程已装依赖（CI frontend job）也能
  // 测到这条失败路径，防「降级又悄悄变回静默绿」。
  const errors = [];
  const origError = console.error;
  console.error = (...args) => errors.push(args.join(" "));
  let rc;
  try {
    rc = guard.main([], { astOk: false });
  } finally {
    console.error = origError;
  }
  assert.equal(rc, 2, "依赖缺失必须判 2，不产出结论");
  assert.notEqual(rc, 0, "绝不能返回 0（假绿）");
  const msg = errors.join("\n");
  assert.match(msg, /typescript/);
  assert.match(msg, /@vue\/compiler-sfc/);
  assert.doesNotMatch(msg, /\bOK\b/, "降级时不得打印 OK");
  assert.doesNotMatch(msg, /收紧基线/, "降级时不得产生 loose 提示");
  assert.doesNotMatch(msg, /只减不增/, "降级时不得宣布通过");

  // 本进程若确实没装依赖，再用 CLI 层坐实：裸跑守卫必须 exit 2、输出不含 OK。
  if (!AST_OK) {
    const r = run();
    assert.equal(r.code, 2, "依赖缺失时 CLI 必须显式失败");
    assert.doesNotMatch(`${r.out}${r.err}`, /\bOK\b/);
    assert.doesNotMatch(`${r.out}${r.err}`, /收紧基线|只减不增/);
  }
});

test("降级计数函数仅作解析层测试：注释 / 字符串里的 any 不计，类型位置的 any 计入", async () => {
  const guard = await import(pathToFileURL(script).href);
  assert.equal(
    guard.countFallback(
      'const a: any = 1; // any any\nconst s = "any";',
      "x.ts",
    ),
    1,
  );
  assert.equal(guard.countFallback("const b = foo as any;", "y.ts"), 1);
  assert.equal(
    guard.countFallback(
      '<template>{{ any }}</template>\n<script setup lang="ts">const p: any = 1;</script>',
      "z.vue",
    ),
    1,
  );
  // 纯函数只做解析，不产出「通过 / 拦截」结论，也不碰任何基线。
});

test(
  "真实仓库：存量已冻结为基线，守卫应通过（绿）",
  { skip: SKIP_NO_AST },
  () => {
    const r = run();
    assert.equal(r.code, 0, `守卫不该红：${r.out}\n${r.err}`);
    assert.match(r.out, /只减不增/);
  },
);

test(
  "灵敏度正例：往样本文件加一个 any → 守卫必须返回 1（防永远绿）",
  { skip: SKIP_NO_AST },
  () => {
    const sb = withSandbox();
    const p = join(sb.src, "a.ts");
    writeFileSync(p, `${readFileSync(p, "utf8")}\nconst extra: any = 1;\n`);
    const r = run([], sb.env);
    assert.equal(r.code, 1, "新增一个 any 应当判红（回潮拦截）");
    assert.match(`${r.out}${r.err}`, /回潮/);
  },
);

test(
  "灵敏度反例：删掉一个 any → 返回 0 并提示收紧基线",
  { skip: SKIP_NO_AST },
  () => {
    const sb = withSandbox();
    const p = join(sb.src, "a.ts");
    writeFileSync(
      p,
      readFileSync(p, "utf8").replace(
        "const b = foo as any;",
        "const b = foo;",
      ),
    );
    const r = run([], sb.env);
    assert.equal(r.code, 0, "正常收敛不该红掉校验");
    assert.match(r.out, /--report 收紧基线/);
  },
);

test(
  "基线覆盖：真实仓库里每个含 any 的文件都在基线里",
  { skip: SKIP_NO_AST },
  async () => {
    const guard = await import(pathToFileURL(script).href);
    const counts = guard.collectCounts();
    const b = JSON.parse(readFileSync(realBaseline, "utf8"));
    for (const [k, n] of Object.entries(counts)) {
      if (n > 0) assert.ok(k in b.files, `${k} 有 ${n} 处 any 却不在基线里`);
    }
  },
);

test(
  "空输入返回 2（拿不到输入必须显式失败，不许静默绿）",
  { skip: SKIP_NO_AST },
  () => {
    const dir = mkdtempSync(join(tmpdir(), "ts-any-empty-"));
    const src = join(dir, "src");
    mkdirSync(src, { recursive: true }); // 目录存在，但没有任何 .ts / .vue
    const r = run([], {
      GUARD_TS_ANY_SRC: src,
      GUARD_TS_ANY_BASELINE: join(dir, "baseline.json"),
    });
    assert.equal(r.code, 2);
    assert.match(`${r.out}${r.err}`, /扫到任何/);
  },
);

test(
  "--write 试图上调已有基线条目必须拒绝（exit 1），且基线不被改写",
  { skip: SKIP_NO_AST },
  () => {
    const sb = withSandbox();
    const before = readFileSync(sb.baseline, "utf8");
    const p = join(sb.src, "a.ts");
    writeFileSync(p, `${readFileSync(p, "utf8")}\nconst extra: any = 1;\n`);
    const r = run(["--write"], sb.env);
    assert.equal(r.code, 1);
    assert.match(`${r.out}${r.err}`, /拒绝 --write/);
    assert.equal(
      readFileSync(sb.baseline, "utf8"),
      before,
      "基线不得被回写洗掉",
    );
  },
);

test(
  "基线格式非法返回 2（不许把坏基线当成通过）",
  { skip: SKIP_NO_AST },
  () => {
    const dir = mkdtempSync(join(tmpdir(), "ts-any-badb-"));
    const src = join(dir, "src");
    mkdirSync(src, { recursive: true });
    writeFileSync(join(src, "a.ts"), "const a: any = 1;\n");
    const baseline = join(dir, "baseline.json");
    writeFileSync(baseline, "{ this is not json", "utf8");
    const r = run([], {
      GUARD_TS_ANY_SRC: src,
      GUARD_TS_ANY_BASELINE: baseline,
    });
    assert.equal(r.code, 2);
  },
);

test("新增文件含 any 必须转红（零容忍，上限 0）", { skip: SKIP_NO_AST }, () => {
  const sb = withSandbox();
  writeFileSync(
    join(sb.src, "brand-new.ts"),
    ["a", "b", "c", "d"].map((v) => `const ${v}: any = 1;`).join("\n"),
  );
  const r = run([], sb.env);
  assert.equal(r.code, 1);
  assert.match(`${r.out}${r.err}`, /超过新增文件上限 0/);
});

test(
  "1 处 any 的新文件同样转红，且 --write 不得把它洗进基线",
  { skip: SKIP_NO_AST },
  () => {
    const sb = withSandbox();
    writeFileSync(join(sb.src, "small-new.ts"), "const x: any = 1;\n");
    const r = run([], sb.env);
    assert.equal(r.code, 1, "新文件含 any 不得静默放行");
    assert.match(`${r.out}${r.err}`, /small-new\.ts/);
    assert.match(`${r.out}${r.err}`, /超过新增文件上限 0/);
    assert.doesNotMatch(r.out, /只减不增/, "转红时不得同时宣布通过");

    const w = run(["--write"], sb.env);
    assert.equal(w.code, 1, "--write 不得把新文件的 any 登记进基线");
    const after = JSON.parse(readFileSync(sb.baseline, "utf8"));
    assert.equal(after.files["small-new.ts"], undefined, "基线里不得出现该文件");
    assert.equal(after.files["a.ts"], AST_COUNTS["a.ts"], "已有条目不得被改写");
  },
);

test(
  "防误伤：0 any 的新文件仍静默放行，不刷提示",
  { skip: SKIP_NO_AST },
  () => {
    const sb = withSandbox();
    writeFileSync(join(sb.src, "brand-clean.ts"), "export const n: number = 2;\n");
    const r = run([], sb.env);
    assert.equal(r.code, 0, "新增纯类型文件不该红掉校验");
    assert.doesNotMatch(r.out, /未纳入基线|--write 纳入基线/);
  },
);

test("基线里文件已删：打印 stale 提示但不报错", { skip: SKIP_NO_AST }, () => {
  const sb = withSandbox();
  rmSync(join(sb.src, "clean.ts"));
  const r = run([], sb.env);
  assert.equal(r.code, 0);
  assert.match(r.out, /stale|已不在基线/);
});

test("--report 打印可直接写回的基线 JSON", { skip: SKIP_NO_AST }, () => {
  const sb = withSandbox();
  const r = run(["--report"], sb.env);
  assert.equal(r.code, 0);
  const parsed = JSON.parse(r.out);
  assert.equal(parsed.issue, 2879);
  assert.equal(parsed.newFileAnyLimit, 0);
  assert.equal(parsed.files["a.ts"], AST_COUNTS["a.ts"]);
  assert.equal(parsed.files["sub/b.vue"], AST_COUNTS["sub/b.vue"]);
});
