import { expect, test, type Page } from "@playwright/test";
import { injectSupabaseSession } from "./support/session";

/**
 * 编辑交易弹窗的联动与守卫（#980 拆分回归网）。
 *
 * 拆分把这页的表单状态与四组 `watch` 挪进了 `useTransactionEditForm`。其中三件事
 * 只有真机跑得出来、单测看不见：
 *
 * 1. **股票正算**：改「数量」→「金额 = 数量 × 单价 + 手续费」自动回填；
 * 2. **基金反算与只读净值**：标签切成「份额 / 净值(元)」，净值只读且 4 位小数；
 * 3. **未保存修改守卫**：脏表单点「取消」必须弹确认框——这条是 #1835 的核心，
 *    拆分时 `requestClose` 从 SFC 搬进了 composable，最容易漏接线。
 *
 * 基金的「金额 → 份额」反算由 23 条单测覆盖（`transactionEditModel.spec.ts`），
 * 这里不重复：真机上它依赖净值接口与 `nextTick` 写入窗口，断言成本高、信息量低。
 */

function dayOffset(offset: number): string {
  const d = new Date();
  d.setDate(d.getDate() - offset);
  return d.toISOString().slice(0, 10);
}

const TODAY = dayOffset(0);

const STOCK_ROW = {
  id: 1,
  ledger_id: 1,
  position_id: 11,
  position_name: "贵州茅台",
  type: "buy",
  asset_type: "stock",
  trade_date: TODAY,
  confirm_date: TODAY,
  quantity: 100,
  price: 12.5,
  fee: 5,
  amount: 1255,
  status: "success",
  account_name: "主账户",
  notes: null,
  // 手工录入的记录：弹窗里要出现「重新导入时需按新内容对账」提示
  import_hash: null,
  created_at: `${TODAY}T01:00:00Z`
};

const FUND_ROW = {
  id: 2,
  ledger_id: 1,
  position_id: 12,
  position_name: "沪深300ETF",
  type: "buy",
  asset_type: "fund",
  trade_date: TODAY,
  confirm_date: TODAY,
  quantity: 500,
  price: 1.2345,
  fee: 0,
  amount: 617.25,
  status: "success",
  account_name: "主账户",
  notes: null,
  // 导入产生的记录：不显示对账提示
  import_hash: "abc123",
  created_at: `${TODAY}T02:00:00Z`
};

async function stubTransactions(page: Page) {
  await page.route(/^https?:\/\/[^/]+\/api\//, route =>
    route.fulfill({
      status: 404,
      json: { data: null, message: "e2e 未打桩", error_code: 40400 }
    })
  );
  await page.route(/^https?:\/\/[^/]+\/api\/transactions/, route =>
    route.fulfill({
      status: 200,
      json: {
        data: [STOCK_ROW, FUND_ROW],
        total: 2,
        page: 1,
        per_page: 10,
        message: "ok"
      }
    })
  );
}

/** 打开流水页 → 点指定行的「编辑」，返回弹窗 locator */
async function openEditDialog(page: Page, positionName: string) {
  await page.goto("/#/transactions");
  const row = page
    .locator(".el-table__row")
    .filter({ hasText: positionName })
    .first();
  await expect(row).toBeVisible({ timeout: 90_000 });
  await row.getByRole("button", { name: "编辑" }).click();

  const dialog = page.locator(".el-dialog").filter({ hasText: "编辑交易" });
  await expect(dialog).toBeVisible();
  return dialog;
}

/** 取某个表单项里的数字输入框（按标签文案定位） */
function numberInput(dialog: ReturnType<Page["locator"]>, label: string) {
  return dialog
    .locator(".el-form-item")
    .filter({ hasText: label })
    .locator(".el-input-number input")
    .first();
}

test.describe("编辑交易弹窗（#980 拆分）", () => {
  test.setTimeout(180_000);

  test.beforeEach(async ({ context, baseURL, page }) => {
    await injectSupabaseSession(context, baseURL!);
    await stubTransactions(page);
  });

  test("股票：改数量后金额按「数量 × 单价 + 手续费」正算", async ({ page }) => {
    const dialog = await openEditDialog(page, "贵州茅台");

    // 股票档的标签与提示（`isFund` 判定搬进 composable 后的接线验证）
    await expect(dialog.getByText("数量为整数（股 / 张）")).toBeVisible();
    await expect(numberInput(dialog, "数量")).toHaveValue("100");
    await expect(numberInput(dialog, "金额(元)")).toHaveValue("1255.00");

    // 手工录入记录才有对账提示
    await expect(
      dialog.getByText("该记录为手工编辑，重新导入时需按新内容对账")
    ).toBeVisible();

    const quantity = numberInput(dialog, "数量");
    await quantity.fill("200");
    await quantity.blur();

    // 200 × 12.5 + 5 = 2505
    await expect(numberInput(dialog, "金额(元)")).toHaveValue("2505.00");
  });

  test("基金：标签切份额 / 净值，净值只读且保留 4 位小数", async ({ page }) => {
    const dialog = await openEditDialog(page, "沪深300ETF");

    await expect(dialog.getByText("基金份额，根据金额自动反算")).toBeVisible();
    // 基金份额按 4 位小数展示（quantityMeta 的 precision=4）
    await expect(numberInput(dialog, "份额")).toHaveValue("500.0000");

    // 净值是只读展示（`el-input` 而非 `el-input-number`），4 位小数
    const navItem = dialog.locator(".el-form-item").filter({ hasText: "净值" });
    const navInput = navItem.locator("input").first();
    await expect(navInput).toBeDisabled();
    await expect(navInput).toHaveValue("1.2345");

    // 导入产生的记录不显示对账提示
    await expect(
      dialog.getByText("该记录为手工编辑，重新导入时需按新内容对账")
    ).toHaveCount(0);
  });

  test("脏表单点「取消」弹未保存确认，选「继续编辑」不丢数据", async ({
    page
  }) => {
    const dialog = await openEditDialog(page, "贵州茅台");

    const quantity = numberInput(dialog, "数量");
    await quantity.fill("321");
    await quantity.blur();
    await expect(quantity).toHaveValue("321");

    await dialog.getByRole("button", { name: "取消" }).click();

    // 守卫接线：`requestClose` 从 SFC 搬进 composable 后仍然先问一次
    const box = page.locator(".el-message-box");
    await expect(box).toBeVisible();
    await expect(box.getByText("未保存的修改")).toBeVisible();

    // 「继续编辑」→ 弹窗不关、输入不丢
    await box.getByRole("button", { name: "继续编辑" }).click();
    await expect(box).toBeHidden();
    await expect(dialog).toBeVisible();
    await expect(quantity).toHaveValue("321");

    // 「放弃修改」→ 真的关闭
    await dialog.getByRole("button", { name: "取消" }).click();
    await expect(box).toBeVisible();
    await box.getByRole("button", { name: "放弃修改" }).click();
    await expect(dialog).toBeHidden();
  });
});
