/**
 * `scripts/guard_smart_fill_parity.mjs` 的回归用例（#2903）。
 *
 * ## 为什么有这份文件
 *
 * 本卡的问题不是「算错了」，而是**同一条规则写了两份**：OCR 通道无守卫、文件通道
 * 4 条件，且后者的 `!isRowBlocked` 与「缺单价」互斥（方向写反，该补的一个没补、
 * 不该补的全补了）。修完代码，最可能的回潮是下一个人再内联一份补价计算式——
 * 它**不会报错**，只让两条通道的结果重新不一致。
 *
 * 所以这里不只验证「真仓过」，更要验证「回潮会红」：
 *
 * 1. 真仓跑 ⇒ exit 0（存量不误伤，否则没人看它）；
 * 2. 另起一份 `smartFilled = true` ⇒ exit 1 并点名文件；
 * 3. 某条通道没接线（只剩 1 处使用）⇒ exit 1；
 * 4. `smartFillPrice.ts` 缺失 ⇒ **exit 2**（拿不到输入不得退化成绿）；
 * 5. `__tests__` 下构造回退探针不误伤（那里写 `smartFilled` 是合法的）。
 */

const { test } = require('node:test');
const assert = require('node:assert/strict');
const { spawnSync } = require('node:child_process');
const { mkdtempSync, mkdirSync, writeFileSync, rmSync } = require('node:fs');
const { tmpdir } = require('node:os');
const { join } = require('node:path');

const root = join(__dirname, '..', '..');
const script = join(root, 'scripts', 'guard_smart_fill_parity.mjs');

/** 跑守卫；返回 { code, out }（失败不抛，交给断言判断）。 */
function run(args = []) {
  const r = spawnSync(process.execPath, [script, ...args], {
    cwd: root,
    encoding: 'utf8'
  });
  return { code: r.status, out: `${r.stdout ?? ''}${r.stderr ?? ''}` };
}

const COMPOSABLES = join(
  'frontend',
  'src',
  'views',
  'asset',
  'investment',
  'import',
  'composables'
);

const WIZARD_OK = `import { fillSmartPrice } from "./smartFillPrice";

export function ocr(rows) {
  rows.forEach(fillSmartPrice);
}

export function upload(rows) {
  rows.forEach(row => fillSmartPrice(row));
}
`;

const SMART_FILL_OK = `export function fillSmartPrice(row) {
  row.price = 1;
  row.smartFilled = true;
  return true;
}
`;

const CELL_EDIT_OK = `export function smartFill(row) {
  row.price = 1;
  row.smartFilled = true;
}
`;

/** 造一个最小仓：三个文件都可按需覆盖 / 删除。 */
function fixture(overrides = {}) {
  const dir = mkdtempSync(join(tmpdir(), "guard-smart-fill-"));
  const comp = join(dir, COMPOSABLES);
  mkdirSync(comp, { recursive: true });
  const files = {
    "useImportWizard.ts": WIZARD_OK,
    "smartFillPrice.ts": SMART_FILL_OK,
    "cellEditLogic.ts": CELL_EDIT_OK,
    ...overrides
  };
  for (const [name, content] of Object.entries(files)) {
    if (content === null) continue; // null = 该文件不存在
    writeFileSync(join(comp, name), content, "utf8");
  }
  return dir;
}

function withFixture(overrides, fn) {
  const dir = fixture(overrides);
  try {
    return fn(dir);
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
}

test("真实仓库：补价已是单一实现，两条通道都接线 → exit 0", () => {
  const { code, out } = run();
  assert.equal(code, 0, out);
  assert.match(out, /两条通道均已接线/);
});

test("合法最小仓 → exit 0（不误伤别处同形的 smartFilled 写法）", () => {
  withFixture({}, dir => {
    const { code, out } = run(["--root", dir]);
    assert.equal(code, 0, out);
  });
});

test("另起一份补价并打 smartFilled 标记 → exit 1 且点名文件", () => {
  const wizard = `${WIZARD_OK}
export function legacy(rows) {
  rows.forEach(row => {
    row.price = parseFloat((parseFloat(row.amount) / parseFloat(row.quantity)).toFixed(4));
    row.smartFilled = true;
  });
}
`;
  withFixture({ "useImportWizard.ts": wizard }, dir => {
    const { code, out } = run(["--root", dir]);
    assert.equal(code, 1, out);
    assert.match(out, /useImportWizard\.ts:\d+/);
    assert.match(out, /手写补价标记/);
  });
});

test("某条通道没接线（只剩 1 处使用）→ exit 1", () => {
  const wizard = `import { fillSmartPrice } from "./smartFillPrice";

export function ocr(rows) {
  rows.forEach(fillSmartPrice);
}
`;
  withFixture({ "useImportWizard.ts": wizard }, dir => {
    const { code, out } = run(["--root", dir]);
    assert.equal(code, 1, out);
    assert.match(out, /只找到 1 处 fillSmartPrice 使用/);
  });
});

test("smartFillPrice.ts 缺失 → exit 2（拿不到输入不得读成通过）", () => {
  withFixture({ "smartFillPrice.ts": null }, dir => {
    const { code, out } = run(["--root", dir]);
    assert.equal(code, 2, out);
    assert.match(out, /结论不可信/);
  });
});

test("__tests__ 下构造回退探针（smartFilled 赋值）不误伤 → exit 0", () => {
  withFixture({}, dir => {
    const testDir = join(dir, COMPOSABLES, "__tests__");
    mkdirSync(testDir, { recursive: true });
    writeFileSync(
      join(testDir, "probe.spec.ts"),
      "const row: any = {};\nrow.smartFilled = true;\n",
      "utf8"
    );
    const { code, out } = run(["--root", dir]);
    assert.equal(code, 0, out);
  });
});
