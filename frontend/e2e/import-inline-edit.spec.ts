import { expect, test, type Locator, type Page } from "@playwright/test";
import { injectSupabaseSession } from "./support/session";

/**
 * #1790 预览表格行内就地编辑（弹层改就地 + Enter/Esc/Tab 键盘 + 金额自动重算 + 11 列收敛）。
 *
 * 覆盖验收：
 * - ① 无浮层：页面 `.el-popover` 为 0，输入框出现在被点单元格内部；
 *   （`rg -e 'el-popover'` 目录 0 命中由提交前静态检查承担）
 * - ② 三个可编辑列均支持 Enter / Esc / Tab，且页面有交互说明（.edit-hint）；
 * - ③ 表格总列数 = 11（勾选 + 9 数据列 + 操作），退场列（手续费/合同编号/发生金额）不出现；
 * - ④ 自动计算与行/格高亮回归：改数量→重算金额、Enter 停留 / Esc 还原、
 *   缺数量行 row-blocked + cell-blocked + 补全入口 + 解禁、缺金额 cell-missing、
 *   改金额→反算单价。
 *
 * 打桩策略同 #1791/#1792：真实走「选账户 → 上传 → 解析」链路，
 * 仅把 /api/importers/parse/ 换成固定数据集。
 */

const LEDGER = {
  id: 1,
  name: "E2E 演示账户",
  ledger_type: "stock",
  default_allocation: "longterm"
};

const baseRow = {
  display_type: "股票",
  op_type: "buy",
  op_type_label: "买入",
  fee: 5,
  trade_date: "2026-09-01",
  account_name: "",
  ledger_id: LEDGER.id,
  contract_id: "",
  is_cash_transfer: false,
  error: null as string | null,
  is_duplicate: false,
  allocation: null,
  link_group_id: null,
  trade_amount: 0,
  net_amount: 0,
  notes: "",
  source: "e2e",
  is_calculated: false
};

/** 完整行：数量/单价/金额齐全，用于 Enter/Esc/Tab 与重算断言 */
const completeA = {
  ...baseRow,
  symbol: "600519",
  name: "贵州茅台",
  type: "stock",
  quantity: 100,
  price: 10,
  amount: 1000
};

/** 缺数量行（数量为空、单价与金额在）→ row-blocked + cell-blocked，可经「补全」修复 */
const blockedB = {
  ...baseRow,
  symbol: "600000",
  name: "浦发银行",
  type: "stock",
  quantity: null as unknown as number,
  price: 10,
  amount: 100
};

/** 缺金额行（数量/单价在）→ 金额格 cell-missing，可就地补金额 */
const missingAmountC = {
  ...baseRow,
  symbol: "000002",
  name: "万科A",
  type: "stock",
  quantity: 10,
  price: 10,
  amount: null as unknown as number
};

const ROWS = [completeA, blockedB, missingAmountC];

async function openPreview(page: Page, rows: typeof ROWS) {
  await page.route(
    url => /\/api\/ledgers\/?$/.test(url.pathname),
    route =>
      route.fulfill({ json: { data: [LEDGER], message: "ok", error_code: 0 } })
  );
  await page.route(
    url => url.pathname.includes("/api/ledgers/sales-institutions"),
    route => route.fulfill({ json: { data: [], message: "ok", error_code: 0 } })
  );
  await page.route(
    url => url.pathname.includes("/api/importers/parse"),
    route =>
      route.fulfill({
        json: {
          data: rows,
          total: rows.length,
          error_count: rows.filter(r => r.error).length,
          duplicate_count: 0,
          cash_transfer_count: 0,
          message: "ok",
          error_code: 0
        }
      })
  );

  await page.goto("/#/inventory/investment/import");

  await page.locator(".account-select").click();
  await page
    .locator(".el-select-dropdown:visible .el-select-dropdown__item", {
      hasText: LEDGER.name
    })
    .first()
    .click();

  await page.locator(".golden-upload input[type=file]").setInputFiles({
    name: "trades.csv",
    mimeType: "text/csv",
    buffer: Buffer.from("交易日期,证券代码,数量\n2026-09-01,600519,100\n")
  });

  await expect(page.locator(".step3-container")).toBeVisible({
    timeout: 30_000
  });

  // 表格默认展开（showFullTable 初值 true），断言可见即可
  await expect(page.locator(".table-wrapper")).toBeVisible();
}

/** 当前处于编辑态的输入框（一格编辑、其余为展示态，唯一匹配） */
function editingInput(row: Locator) {
  return row.locator(".edit-cell input");
}

test.describe("行内就地编辑（#1790）", () => {
  test.setTimeout(180_000);

  test.beforeEach(async ({ context, baseURL }) => {
    await injectSupabaseSession(context, baseURL!);
  });

  test("点击就地进入无浮层，Enter 提交停留并重算金额，Esc 取消还原", async ({
    page
  }) => {
    const pageErrors: string[] = [];
    page.on("pageerror", e => pageErrors.push(e.message));

    await openPreview(page, ROWS);

    // 验收②：页面有交互说明
    await expect(page.locator(".edit-hint")).toContainText("Enter");
    await expect(page.locator(".edit-hint")).toContainText("Esc");

    // 验收①：整页无任何浮层
    await expect(page.locator(".el-popover")).toHaveCount(0);

    const rowA = page.locator("tbody tr", { hasText: "贵州茅台" });

    // 单击展示态 → 同一单元格内出现输入框（就地，非浮层）
    await rowA.locator('[data-edit-cell="quantity"]').click();
    await expect(editingInput(rowA)).toBeFocused();
    await expect(page.locator(".el-popover")).toHaveCount(0);

    // Enter 提交并停留当前格；改数量 → 金额 = 数量 × 单价
    await editingInput(rowA).fill("150");
    await page.keyboard.press("Enter");
    await expect(rowA.locator('[data-edit-cell="quantity"]')).toContainText(
      "150"
    );
    await expect(rowA.locator('[data-edit-cell="amount"]')).toContainText(
      "1500"
    );
    await expect(rowA.locator('[data-edit-cell="quantity"]')).toBeFocused();

    // 停留后 Enter 再次进入 → Esc 取消还原到上次提交值
    await page.keyboard.press("Enter");
    await expect(editingInput(rowA)).toBeVisible();
    await editingInput(rowA).fill("999");
    await page.keyboard.press("Escape");
    await expect(rowA.locator('[data-edit-cell="quantity"]')).toContainText(
      "150"
    );
    await expect(rowA.locator('[data-edit-cell="amount"]')).toContainText(
      "1500"
    );

    expect(pageErrors).toEqual([]);
  });

  test("Tab 提交并跳下一可编辑格，改金额反算单价", async ({ page }) => {
    const pageErrors: string[] = [];
    page.on("pageerror", e => pageErrors.push(e.message));

    await openPreview(page, ROWS);
    const rowA = page.locator("tbody tr", { hasText: "贵州茅台" });

    // 数量 →（Tab）→ 单价：提交 200 并落进单价编辑
    await rowA.locator('[data-edit-cell="quantity"]').click();
    await editingInput(rowA).fill("200");
    await page.keyboard.press("Tab");
    await expect(editingInput(rowA)).toBeFocused();

    await editingInput(rowA).fill("5");
    await page.keyboard.press("Enter");
    await expect(rowA.locator('[data-edit-cell="amount"]')).toContainText(
      "1000"
    ); // 200 × 5

    // 改金额 → 反算单价 = 500 ÷ 200 = 2.5（§6.2 / #1790 要做的事 5）
    await rowA.locator('[data-edit-cell="amount"]').click();
    await editingInput(rowA).fill("500");
    await page.keyboard.press("Enter");
    await expect(rowA.locator('[data-edit-cell="price"]')).toContainText("2.5");
    await expect(rowA.locator('[data-edit-cell="amount"]')).toContainText(
      "500"
    );

    expect(pageErrors).toEqual([]);
  });

  test("行/格高亮与补全回归：row-blocked/cell-blocked 解禁、cell-missing 消除", async ({
    page
  }) => {
    const pageErrors: string[] = [];
    page.on("pageerror", e => pageErrors.push(e.message));

    await openPreview(page, ROWS);

    // ── 缺数量行：row-blocked + 数量/单价两格 cell-blocked，复选框禁用 ──
    const rowB = page.locator("tbody tr", { hasText: "浦发银行" });
    await expect(rowB).toHaveClass(/row-blocked/);
    await expect(rowB.locator("td.cell-blocked")).toHaveCount(2);
    await expect(rowB.locator(".el-checkbox")).toBeDisabled();

    // 操作列「补全」→ 就地进入数量编辑 → 修复后高亮与禁用全部解除
    await rowB.getByRole("button", { name: "补全" }).click();
    await expect(editingInput(rowB)).toBeFocused();
    await editingInput(rowB).fill("10");
    await page.keyboard.press("Enter");
    await expect(rowB).not.toHaveClass(/row-blocked/);
    await expect(rowB.locator("td.cell-blocked")).toHaveCount(0);
    await expect(rowB.locator(".el-checkbox")).not.toBeDisabled();
    // 重算金额 = 10 × 10 = 100（与原值一致，断言无副作用漂移）
    await expect(rowB.locator('[data-edit-cell="amount"]')).toContainText(
      "100"
    );

    // ── 缺金额行：金额格 cell-missing → 就地补金额后消除，单价被反算维持一致 ──
    const rowC = page.locator("tbody tr", { hasText: "万科A" });
    await expect(rowC.locator("td.cell-missing")).toHaveCount(1);
    await rowC.locator('[data-edit-cell="amount"]').click();
    await editingInput(rowC).fill("100");
    await page.keyboard.press("Enter");
    await expect(rowC.locator("td.cell-missing")).toHaveCount(0);
    await expect(rowC.locator('[data-edit-cell="price"]')).toContainText("10");
    await expect(rowC.locator('[data-edit-cell="amount"]')).toContainText(
      "100"
    );

    expect(pageErrors).toEqual([]);
  });

  test("列收敛：总列数 11，退场列（手续费/合同编号/发生金额）不出现", async ({
    page
  }) => {
    const pageErrors: string[] = [];
    page.on("pageerror", e => pageErrors.push(e.message));

    await openPreview(page, ROWS);

    // 11 列 = 勾选 + 9 数据列（状态/产品/操作类型/日期/数量/单价/金额/配置/备注）+ 操作
    await expect(page.locator(".el-table__header th")).toHaveCount(11);
    await expect(page.locator(".el-table__header")).not.toContainText("手续费");
    await expect(page.locator(".el-table__header")).not.toContainText(
      "合同编号"
    );
    await expect(page.locator(".el-table__header")).not.toContainText(
      "发生金额"
    );

    expect(pageErrors).toEqual([]);
  });
});
