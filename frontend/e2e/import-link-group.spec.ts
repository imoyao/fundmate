import { expect, test, type Page } from "@playwright/test";
import { injectSupabaseSession } from "./support/session";

/**
 * 配对组在预览页的呈现（#2836）。
 *
 * 单测（linkGroup.spec.ts）钉的是 composable 里的判据与计数；这里钉的是**渲染结果**——
 * 两处曾经对不上：判据说折成一行，表格却把明细也画出来（el-table 的 tree-props 吃
 * `children` 字段 + default-expand-all 默认展开，等于没折）。这类偏差只有走真 DOM 才看得见。
 *
 * 数据集 10 条，覆盖四件事：
 * - 一组「债券兑息 + 债券兑息兑付」（丰山 90 / −18）→ 折成 1 行净额 72；
 * - 一组「债券兑付 + 股份转出」（龙大）→ 转出行被消费、不可勾选；
 * - 三类问题行各 1（解析错误 / 代码未匹配 / 金额不一致）；
 * - 1 条疑似重复。
 *
 * 折叠后表格应为 9 行：complete 5 + duplicate 1 + fix 3。
 */

const LEDGER = {
  id: 1,
  name: "华泰证券",
  ledger_type: "stock",
  default_allocation: "longterm"
};

const baseRow = {
  display_type: "股票",
  op_type: "buy",
  op_type_label: "买入",
  fee: 0,
  trade_date: "2026-09-01",
  account_name: "",
  ledger_id: LEDGER.id,
  contract_id: "",
  is_cash_transfer: false,
  error: null as string | null,
  is_duplicate: false,
  allocation: null,
  link_group_id: null,
  link_warning: "",
  consumed_by: "",
  trade_amount: 0,
  net_amount: 0,
  notes: "",
  source: "e2e",
  is_calculated: false
};

const GROUP = "bond_interest_tax:SH113649:2026-06-26";

const ROWS = [
  {
    ...baseRow,
    symbol: "600519",
    name: "贵州茅台",
    type: "stock",
    quantity: 100,
    price: 1700,
    amount: 170000
  },
  {
    ...baseRow,
    symbol: "000001",
    name: "平安银行",
    type: "stock",
    quantity: 1000,
    price: 10.5,
    amount: 10500
  },
  {
    ...baseRow,
    symbol: "113649",
    name: "丰山转债",
    type: "bond",
    op_type: "dividend_cash",
    op_type_label: "现金分红",
    quantity: 60,
    price: 1.5,
    amount: 90,
    notes: "债券兑息",
    link_group_id: GROUP
  },
  {
    ...baseRow,
    symbol: "113649",
    name: "丰山转债",
    type: "bond",
    op_type: "tax",
    op_type_label: "扣税",
    quantity: 60,
    price: 1.5,
    amount: -18,
    notes: "债券兑息兑付",
    link_group_id: GROUP
  },
  {
    ...baseRow,
    symbol: "128119",
    name: "龙大转债",
    type: "bond",
    op_type: "bond_redeem",
    op_type_label: "债券兑付",
    amount: 12430,
    notes: "债券兑付"
  },
  {
    ...baseRow,
    symbol: "128119",
    name: "龙大转债",
    type: "bond",
    op_type: "withdraw",
    op_type_label: "取出",
    quantity: 110,
    notes: "股份转出",
    consumed_by: "redeem_share_clearing"
  },
  {
    ...baseRow,
    symbol: "000002",
    name: "万科A",
    type: "stock",
    quantity: 500,
    price: 8,
    amount: 4000,
    error: "交易日期无法解析"
  },
  {
    ...baseRow,
    symbol: "UNKNOWN",
    name: "华夏成长混合",
    type: "fund",
    quantity: 1000,
    price: 1,
    amount: 1000
  },
  {
    ...baseRow,
    symbol: "600000",
    name: "浦发银行",
    type: "stock",
    quantity: 100,
    price: 10,
    amount: 900
  },
  {
    ...baseRow,
    symbol: "600519",
    name: "贵州茅台",
    type: "stock",
    quantity: 100,
    price: 1710,
    amount: 171000,
    is_duplicate: true
  }
];

async function openPreview(page: Page) {
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
          data: ROWS,
          total: ROWS.length,
          error_count: 1,
          duplicate_count: 1,
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
    name: "ths.csv",
    mimeType: "text/csv",
    buffer: Buffer.from("x")
  });
  await expect(page.locator(".step3-container")).toBeVisible({
    timeout: 30_000
  });
}

test.describe("配对组在预览页的呈现（#2836）", () => {
  test.setTimeout(180_000);

  test.beforeEach(async ({ context, baseURL }) => {
    await injectSupabaseSession(context, baseURL!);
  });

  test("息+税折成一行净额，明细默认收起；概览条与修正按钮同一口径", async ({
    page
  }) => {
    const pageErrors: string[] = [];
    page.on("pageerror", e => pageErrors.push(e.message));

    await openPreview(page);

    // 10 条原始行 - 一组息+税折掉 1 条 = 9 行。
    // 必须按**可见**行数：Element Plus 的树形表格在折叠时仍把子行留在 DOM 里
    // 只是隐藏起来，`.el-table__row` 会把它们一起数进去（11 而不是 9）。
    const rows = page.locator(".table-wrapper .el-table__row:visible");
    await expect(rows).toHaveCount(9);

    // 概览条：complete 5 / duplicate 1 / fix 3，合计 9
    await expect(page.locator('.ov-all[data-category="all"]')).toContainText(
      "9"
    );
    await expect(
      page.locator('.ov-chip[data-category="complete"] .ov-count')
    ).toHaveText("5");
    await expect(
      page.locator('.ov-chip[data-category="duplicate"] .ov-count')
    ).toHaveText("1");
    await expect(
      page.locator('.ov-chip[data-category="fix"] .ov-count')
    ).toHaveText("3");

    // 修正按钮的数字与概览条同一个（曾经是「智能修正 1」对「需要修正 3」）
    await expect(page.getByRole("button", { name: /修正问题/ })).toContainText(
      "3"
    );

    // 合并行：操作类型显示「利息收入」，金额是净额 72 而不是 90 / −18
    const merged = page
      .locator(".table-wrapper .el-table__row:visible")
      .filter({ hasText: "利息收入" });
    await expect(merged).toHaveCount(1);
    await expect(merged).toContainText("72");

    // 明细默认收起——否则等于没折（3 行照样占着）
    await expect(
      page
        .locator(".table-wrapper .el-table__row")
        .filter({ hasText: "债券兑息兑付" })
    ).toBeHidden();

    // 展开后能看到税前 / 扣税两行明细
    await merged.locator(".el-table__expand-icon").click();
    await expect(
      page.locator(".table-wrapper .el-table__row:visible")
    ).toHaveCount(11);

    expect(pageErrors).toEqual([]);
  });

  test("被消费的股份转出行：显示「已随兑付清仓」，复选框禁用", async ({
    page
  }) => {
    await openPreview(page);

    const consumedRow = page
      .locator(".table-wrapper .el-table__row:visible")
      .filter({ hasText: "股份转出" });
    await expect(consumedRow).toHaveCount(1);
    await expect(consumedRow).toContainText("已随兑付清仓");

    // 不可勾选：勾了后端也会跳过，让复选框说谎不如直接禁掉
    await expect(consumedRow.locator("input[type=checkbox]")).toBeDisabled();

    // 且不计入「需要修正」（它不是问题行，是「不用你管」）：筛 fix 后只剩 3 行
    await page.locator('.ov-chip[data-category="fix"] .ov-chip-btn').click();
    const fixRows = page.locator(".table-wrapper .el-table__row:visible");
    await expect(fixRows).toHaveCount(3);
    const texts = await fixRows.allInnerTexts();
    expect(texts.join("|")).not.toContain("股份转出");
  });
});
