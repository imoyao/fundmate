import { expect, test, type Page } from "@playwright/test";
import { injectSupabaseSession } from "./support/session";

/**
 * 编辑账户弹窗：账户分组必须**只读**（#2980）。
 *
 * 为什么值得一条 e2e：分组（channel_category）决定后端派生的计算口径，
 * 编辑时改了只会吃到 409「分组与派生口径不一致」。以前是「让你选、选错再拒」，
 * 现在改成不给你选。这条断言守的是「不给选」这个行为本身——一旦有人把
 * `category-readonly` 传丢，它就会失败。
 */

const BANK_LEDGER = {
  id: 1,
  name: "招商银行",
  ledger_type: "bank",
  channel_category: "bank",
  is_active: true,
  currency: "CNY",
  default_allocation: null,
  notes: "",
  portfolio_id: null,
  linked_cash_ledger_id: null,
  linked_money_fund_code: null,
  auto_purchase_money_fund: false,
  fee_config: null,
  sales_institution_id: null,
  owner_member_id: null
};

async function stubSingleBankLedger(page: Page): Promise<void> {
  // 兜底放最前（Playwright route 后注册先匹配）
  await page.route(/^https?:\/\/[^/]+\/api\//, route =>
    route.fulfill({ status: 404, json: { data: null, message: "e2e 未打桩" } })
  );
  await page.route(/^https?:\/\/[^/]+\/api\/ledgers\/(\?.*)?$/, route =>
    route.fulfill({ status: 200, json: { data: [BANK_LEDGER], total: 1 } })
  );
  await page.route(/^https?:\/\/[^/]+\/api\/portfolios\//, route =>
    route.fulfill({ status: 200, json: { data: [] } })
  );
  await page.route(
    /^https?:\/\/[^/]+\/api\/ledgers\/sales-institutions\//,
    route => route.fulfill({ status: 200, json: { data: [] } })
  );
}

test.describe("编辑账户弹窗（#2980）", () => {
  test.setTimeout(180_000);

  test.beforeEach(async ({ context, baseURL }) => {
    await injectSupabaseSession(context, baseURL!);
  });

  test("账户类型只读：无下拉，且明示不可修改", async ({ page }) => {
    await stubSingleBankLedger(page);
    await page.goto("/#/asset/ledgers/1");

    await page.getByRole("button", { name: /编辑/ }).first().click();
    const dialog = page.locator(".el-dialog").filter({ hasText: "编辑账户" });
    await expect(dialog).toBeVisible({ timeout: 90_000 });

    const typeItem = dialog
      .locator(".el-form-item")
      .filter({ hasText: "账户类型" })
      .first();
    // 只读 = 没有下拉控件
    await expect(typeItem.locator(".el-select")).toHaveCount(0);
    // 但类型本身仍要看得见（只读不是隐藏）
    await expect(typeItem).toContainText("银行");
    await expect(typeItem).toContainText("不可修改");

    await dialog.scrollIntoViewIfNeeded();
    await page.screenshot({
      path: "test-results/edit-dialog-readonly.png",
      fullPage: false
    });
  });
});
