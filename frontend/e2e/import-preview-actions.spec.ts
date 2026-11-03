import { expect, test, type Page } from "@playwright/test";
import { injectSupabaseSession } from "./support/session";

/**
 * 预览页两处「透明底主色按钮」与转账行批量入口（#2838）。
 *
 * 为什么需要真 DOM：`theme.scss` 里 `.el-button.el-button--primary` 把
 * `--el-button-text-color` 设成白色，与 Element Plus 的 `.el-button--primary.is-link`
 * 同权重且后加载 —— 结果所有 `link type="primary"` 按钮都是**白字透明底**，
 * 在页面上等于隐身（「补全」「恢复」「全部勾选」全中）。颜色算错的按钮不会被
 * 任何存在性断言发现，所以这里直接钉 computed color。
 */

const SEC_LEDGER = {
  id: 1,
  name: "华泰证券",
  ledger_type: "stock",
  default_allocation: "longterm",
  linked_cash_ledger_id: 2
};
const CASH_LEDGER = { id: 2, name: "招行储蓄卡", ledger_type: "bank" };

const baseRow = {
  display_type: "股票",
  op_type: "buy",
  op_type_label: "买入",
  fee: 0,
  trade_date: "2026-06-02",
  account_name: "",
  ledger_id: SEC_LEDGER.id,
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

const ROWS = [
  {
    ...baseRow,
    symbol: "563530",
    name: "卫星E",
    type: "etf",
    display_type: "ETF",
    quantity: 1000,
    price: 1.3,
    amount: 1300,
    notes: "证券买入"
  },
  {
    ...baseRow,
    symbol: "600036",
    name: "招商银行",
    type: "stock",
    quantity: null,
    price: null,
    amount: 6600,
    notes: "证券买入"
  },
  {
    ...baseRow,
    symbol: "113649",
    name: "丰山转债",
    type: "bond",
    display_type: "可转债",
    op_type: "dividend_cash",
    op_type_label: "现金分红",
    quantity: 90,
    price: 1,
    amount: 90,
    notes: "债券兑息",
    trade_date: "2026-06-05"
  },
  {
    ...baseRow,
    symbol: "__CASH__",
    name: "银行转证券",
    type: "cash",
    display_type: "现金",
    op_type: "deposit",
    op_type_label: "存入",
    quantity: 0,
    price: 0,
    amount: 8420.5,
    is_cash_transfer: true,
    trade_date: "2026-06-03"
  },
  {
    ...baseRow,
    symbol: "__CASH__",
    name: "OTC现金宝交",
    type: "cash",
    display_type: "现金",
    op_type: "withdraw",
    op_type_label: "取出",
    quantity: 0,
    price: 0,
    amount: 6501.2,
    is_cash_transfer: true,
    trade_date: "2026-06-04"
  }
];

async function openPreview(page: Page) {
  await page.route(
    url => /\/api\/ledgers\/?$/.test(url.pathname),
    route =>
      route.fulfill({
        json: { data: [SEC_LEDGER, CASH_LEDGER], message: "ok", error_code: 0 }
      })
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
          error_count: 0,
          duplicate_count: 0,
          cash_transfer_count: 2,
          message: "ok",
          error_code: 0
        }
      })
  );

  await page.goto("/#/inventory/investment/import");
  await page.locator(".account-select").click();
  await page
    .locator(".el-select-dropdown:visible .el-select-dropdown__item", {
      hasText: SEC_LEDGER.name
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

/** 白字在浅底上肉眼不可见；只断言「不是白色」即可覆盖这个失效模式 */
async function colorOf(locator: ReturnType<Page["locator"]>) {
  return locator.evaluate(el => getComputedStyle(el).color as string);
}

test.describe("预览页按钮可见性与转账行批量勾选（#2838）", () => {
  test.setTimeout(180_000);

  test.beforeEach(async ({ context, baseURL }) => {
    await injectSupabaseSession(context, baseURL!);
  });

  test("步骤条：当前步高亮、已完成打勾，且不再有填充色横条", async ({
    page
  }) => {
    await openPreview(page);

    const steps = page.locator(".import-steps .step");
    await expect(steps).toHaveCount(4);
    await expect(steps.nth(0)).toHaveClass(/is-done/);
    await expect(steps.nth(1)).toHaveClass(/is-done/);
    await expect(steps.nth(2)).toHaveClass(/is-current/);
    await expect(steps.nth(2)).toContainText("预览与修正");
    await expect(steps.nth(3)).toHaveClass(/is-todo/);

    // 旧版 el-steps 的 simple 横条：有背景色、有左右 8% 内边距，像贴在页头下的膏药
    const bg = await page
      .locator(".import-steps")
      .evaluate(el => getComputedStyle(el).backgroundColor);
    expect(bg).toBe("rgba(0, 0, 0, 0)");
  });

  test("「全部勾选」可见且能用：两条转账行一次勾上，再点一次清掉", async ({
    page
  }) => {
    await openPreview(page);

    const btn = page.locator(".ov-note-action");
    await expect(btn).toBeVisible();
    await expect(btn).toHaveText("全部勾选");
    // 守 theme.scss：透明底主色按钮若拿到白字，这个按钮在页面上等于不存在
    expect(await colorOf(btn)).not.toBe("rgb(255, 255, 255)");

    const transferChecks = page
      .locator(".table-wrapper .el-table__row:visible")
      .filter({ hasText: "__CASH__" })
      .locator("input[type=checkbox]");

    await btn.click();
    await expect(btn).toHaveText("全部取消");
    await expect(page.locator(".summary-primary")).toContainText("已选择");
    for (const box of await transferChecks.all()) {
      await expect(box).toBeChecked();
    }

    await btn.click();
    await expect(btn).toHaveText("全部勾选");
    for (const box of await transferChecks.all()) {
      await expect(box).not.toBeChecked();
    }
  });

  test("操作列「补全」不是白字：缺数量/价格的行要能看见这个入口", async ({
    page
  }) => {
    await openPreview(page);

    const row = page
      .locator(".table-wrapper .el-table__row:visible")
      .filter({ hasText: "招商银行" });
    const fill = row.getByRole("button", { name: "补全" });
    await expect(fill).toHaveCount(1);
    expect(await colorOf(fill)).not.toBe("rgb(255, 255, 255)");
  });

  test("产品列不再重复操作列：证券买入不显示，债券兑息要显示", async ({
    page
  }) => {
    await openPreview(page);

    const table = page.locator(".table-wrapper");
    await expect(table).toContainText("债券兑息");

    // 「证券买入」与操作列的「买入」是同义重复，只按原文判据隐藏；这里直接数出现次数
    const dup = await table.evaluate(
      el => (el.textContent || "").split("证券买入").length - 1
    );
    expect(dup).toBe(0);
  });
});
