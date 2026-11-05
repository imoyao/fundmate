/**
 * `scripts/guard_products_api.mjs` 的回归网（#2878）。
 *
 * ## WHY 有这份文件
 *
 * `api/products.ts` 拆完之后，回潮的形态不是「测试变红」，而是「有人把新端点
 * 又写回公共入口」——调用点照常编译、URL 照常通，文件悄悄长回巨型客户端。
 * 守卫必须真能拦住这件事，所以本文件钉两类证据：
 *
 * 1. **主判据真绿**：真实仓库跑下来 exit 0（不误伤存量，否则没人看它）；
 * 2. **变异探针真红**：往 barrel 里塞实现 / 断转发 / 造孤儿模块 / 撑爆子模块 /
 *    反向 import 公共入口 / 空壳 barrel，六类回潮必须逐条 exit 1 并点名规则号。
 *
 * 另有两条防「假红 / 假绿」：
 * 3. 块注释里出现 `export function` 字样**不误伤**（守卫要剥注释）；
 * 4. 拆得更细（子模块变多、barrel 行仍合规）不判红——否则谁拆谁被拦。
 */

const { test } = require("node:test");
const assert = require("node:assert/strict");
const { spawnSync } = require("node:child_process");
const { mkdtempSync, mkdirSync, writeFileSync, rmSync } = require("node:fs");
const { tmpdir } = require("node:os");
const { join } = require("node:path");

const root = join(__dirname, "..", "..");
const script = join(root, "scripts", "guard_products_api.mjs");

const MODULE_OK =
  'import { http } from "@/utils/http";\n' +
  "export function getFundProfile() { return http.request('get', '/x/'); }\n";

function makeRoot(files) {
  const dir = mkdtempSync(join(tmpdir(), "products-api-guard-"));
  const api = join(dir, "frontend", "src", "api");
  mkdirSync(join(api, "products"), { recursive: true });
  for (const [rel, content] of Object.entries(files)) {
    writeFileSync(join(api, rel), content, "utf8");
  }
  return dir;
}

function run(args = []) {
  const r = spawnSync(process.execPath, [script, ...args], {
    encoding: "utf8"
  });
  return { code: r.status, out: `${r.stdout || ""}${r.stderr || ""}` };
}

function withRoot(files, fn) {
  const dir = makeRoot(files);
  try {
    fn(dir);
  } finally {
    try {
      rmSync(dir, { recursive: true, force: true });
    } catch {
      // 临时目录清理失败不影响判据；Windows 沙箱的回收站偶尔不可用
    }
  }
}

const OK_FILES = {
  "products.ts":
    '// 公共入口（只有转发）\nexport * from "./products/fund";\n' +
    'export * from "./products/pro";\n',
  "products/fund.ts": MODULE_OK,
  "products/pro.ts": MODULE_OK
};

test("真实仓库：产品域 API 分层干净，exit 0", () => {
  const r = run(["--report"]);
  assert.equal(r.code, 0, r.out);
  assert.match(r.out, /OK: 产品域 API 分层干净/);
  assert.match(r.out, /products\/fund\.ts/);
});

test("健康样例：两条转发 + 两个子模块，exit 0", () => {
  withRoot(OK_FILES, dir => {
    const r = run(["--root", dir]);
    assert.equal(r.code, 0, r.out);
  });
});

test("探针 S1：barrel 里混入实现代码 → R1 转红", () => {
  withRoot(
    {
      ...OK_FILES,
      "products.ts":
        'export * from "./products/fund";\n' +
        'export * from "./products/pro";\n' +
        "export function newEndpoint() { return 1; }\n"
    },
    dir => {
      const r = run(["--root", dir]);
      assert.equal(r.code, 1, r.out);
      assert.match(r.out, /R1/);
      assert.match(r.out, /newEndpoint/);
    }
  );
});

test("探针 S2：转发目标不存在 → R2 转红", () => {
  withRoot(
    {
      "products.ts": 'export * from "./products/ghost";\n',
      "products/fund.ts": MODULE_OK
    },
    dir => {
      const r = run(["--root", dir]);
      assert.equal(r.code, 1, r.out);
      assert.match(r.out, /R2/);
      assert.match(r.out, /ghost\.ts/);
    }
  );
});

test("探针 S3：子模块没接回公共入口 → R2 转红", () => {
  withRoot(
    {
      ...OK_FILES,
      "products/orphan.ts": MODULE_OK
    },
    dir => {
      const r = run(["--root", dir]);
      assert.equal(r.code, 1, r.out);
      assert.match(r.out, /orphan\.ts/);
      assert.match(r.out, /未被/);
    }
  );
});

test("探针 S4：子模块长过 500 行 → R3 转红", () => {
  withRoot(
    {
      ...OK_FILES,
      "products/fund.ts": MODULE_OK + "// pad\n".repeat(501)
    },
    dir => {
      const r = run(["--root", dir]);
      assert.equal(r.code, 1, r.out);
      assert.match(r.out, /R3/);
      assert.match(r.out, /按子域再拆/);
    }
  );
});

test("探针 S5：子模块反向 import 公共入口 → R4 转红", () => {
  withRoot(
    {
      ...OK_FILES,
      "products/fund.ts":
        'import { resolveProduct } from "@/api/products";\n' + MODULE_OK
    },
    dir => {
      const r = run(["--root", dir]);
      assert.equal(r.code, 1, r.out);
      assert.match(r.out, /R4/);
      assert.match(r.out, /循环依赖/);
    }
  );
});

test("探针 S6：barrel 只剩注释（空壳）→ R1 转红", () => {
  withRoot(
    {
      "products.ts": "// 公共入口\n// 实现都在子域里\n",
      "products/fund.ts": MODULE_OK
    },
    dir => {
      const r = run(["--root", dir]);
      assert.equal(r.code, 1, r.out);
      assert.match(r.out, /R1/);
      assert.match(r.out, /空壳/);
    }
  );
});

test("防假红：块注释里出现 export function 不误伤", () => {
  withRoot(
    {
      "products.ts":
        "/*\n" +
        " * 历史：这里曾有 export function getFundProfile() { ... }\n" +
        " */\n" +
        'export * from "./products/fund";\n' +
        'export * from "./products/pro";\n',
      "products/fund.ts": MODULE_OK,
      "products/pro.ts": MODULE_OK
    },
    dir => {
      const r = run(["--root", dir]);
      assert.equal(r.code, 0, r.out);
    }
  );
});

test("防假绿：拆得更细（5 个子域）仍然绿", () => {
  const files = {
    "products.ts": ["a", "b", "c", "d", "e"]
      .map(n => `export * from "./products/${n}";\n`)
      .join("")
  };
  for (const n of ["a", "b", "c", "d", "e"]) {
    files[`products/${n}.ts`] = MODULE_OK;
  }
  withRoot(files, dir => {
    const r = run(["--root", dir]);
    assert.equal(r.code, 0, r.out);
  });
});
