import { expect, test, type Page, type Locator } from "@playwright/test";

import { injectSupabaseSession } from "./support/session";

/**
 * 「记录交易」买入 / 卖出表单回归网（#980 拆分后补的行为判据）。
 *
 * 这两个表单是**资金写入口**，本轮各自被拆成 3~4 个组件 + 4~6 个 composable
 * （买入 1272 → 400 行、卖出 901 → 397 行）。模板与样式逐单元比对能证明「长得一样」，
 * 却证明不了接线——拆组件最容易断的恰恰是 props / v-model / emit：
 *
 * 1. **账户下拉 → 表单态**：选哪个账户决定「搜基金还是搜证券」、是否有 15:00 切换、
 *    手续费按哪套预设算。这条链现在跨 BuyAccountField → 父层 → BuySecuritySearchField；
 * 2. **持仓下拉 → 数量/价格/费用**：卖出侧的可用份额、步长、最小单位、预估金额全来自
 *    useSellPositions 的一条 computed 链，断一环就只剩空壳；
 * 3. **抽屉 ↔ 表单的 ref 契约**：TransactionDrawer 通过 ref 调 handleSubmit / resetForm
 *    并读 isDirty（未保存离开保护）——拆完 expose 漏一个，提交按钮就静默失效。
 *
 * 因此断言只落在「选完能看到什么」：标签、可用份额、预估金额、提示文案，不测样式值。
 */

const LEDGERS = [
  {
    id: 1,
    name: "天天基金",
    ledger_type: "fund",
    currency: "CNY",
    is_active: true,
    fee_config: { subscription_discount: 0.1 }
  },
  {
    id: 2,
    name: "华泰证券",
    ledger_type: "stock",
    currency: "CNY",
    is_active: true,
    fee_config: { commission: { rate: 0.00025, min: 5 } }
  },
  {
    // 没有持仓的账户：卖出侧必须被过滤掉（只列「有持仓」的账户）
    id: 3,
    name: "空仓账户",
    ledger_type: "stock",
    currency: "CNY",
    is_active: true,
    fee_config: null
  }
];

const POSITIONS_BY_ACCOUNT = {
  "2": [
    {
      id: 88,
      ledger_id: 2,
      symbol: "600519",
      name: "贵州茅台",
      market: "CN_A",
      type: "stock",
      quantity: 200,
      current_price: 1500,
      avg_price: 1400,
      currency: "CNY",
      confirm_date: "2026-01-05"
    }
  ]
};

/** 只桩本轮关心的两个接口，其余 API 一律空响应（与既有 e2e 同一手法） */
async function mockApis(page: Page) {
  await page.route(/^https?:\/\/[^/]+\/api\//, async route => {
    const url = new URL(route.request().url());
    if (url.pathname.startsWith("/api/ledgers/")) {
      return route.fulfill({ json: { data: LEDGERS, message: "" } });
    }
    if (url.pathname.startsWith("/api/positions/")) {
      return route.fulfill({
        json: { data: POSITIONS_BY_ACCOUNT, message: "" }
      });
    }
    return route.fulfill({ json: { data: [], message: "" } });
  });
}

async function openDrawer(page: Page, tab: "买入" | "卖出") {
  // 用 /welcome：自选、盘点等页面的路由 meta 带 hideQuickEntry，FAB 是 display:none
  await page.goto("/#/welcome", { waitUntil: "commit" });
  const fab = page.getByLabel("记一笔");
  await expect(fab).toBeVisible({ timeout: 150_000 });
  await fab.click();

  const drawer = page.locator(".el-drawer").first();
  await expect(drawer.getByText("记录交易")).toBeVisible();
  if (tab === "卖出") {
    await drawer.getByRole("tab", { name: "卖出" }).click();
  }
  return drawer;
}

/** 按表单项标签定位（同一抽屉里有多个 el-select，不能只按 .el-select 取第一个） */
function formItem(scope: Locator, label: string) {
  return scope.locator(".el-form-item").filter({ hasText: label }).first();
}

async function pickSelectOption(
  page: Page,
  selectRoot: Locator,
  optionText: string
) {
  await selectRoot.click();
  const option = page
    .locator(".el-select-dropdown__item:visible")
    .filter({ hasText: optionText })
    .first();
  await expect(option).toBeVisible({ timeout: 30_000 });
  await option.click();
}

test.describe("记录交易表单（#980 拆分后的接线判据）", () => {
  test.beforeEach(async ({ context, baseURL }) => {
    await injectSupabaseSession(context, baseURL!);
  });

  test("买入：选基金账户后搜索口径变「基金」，核心三兄弟齐全", async ({
    page
  }) => {
    test.setTimeout(240_000);
    await mockApis(page);
    const drawer = await openDrawer(page, "买入");

    // 账户下拉来自子组件（BuyAccountField），选完要回传父层
    const accountItem = formItem(drawer, "选择账户");
    await pickSelectOption(
      page,
      accountItem.locator(".el-select").first(),
      "天天基金"
    );

    // 搜索标签由账户品类派生：基金账户 → 「基金」
    await expect(
      drawer.locator(".el-form-item__label").filter({ hasText: "基金" }).first()
    ).toBeVisible();
    await expect(formItem(drawer, "买入金额")).toBeVisible();
    await expect(formItem(drawer, "确认份额")).toBeVisible();
    await expect(formItem(drawer, "配置目标")).toBeVisible();

    // 换到证券账户：标签必须跟着变，且不能残留基金专属字段
    await pickSelectOption(
      page,
      accountItem.locator(".el-select").first(),
      "华泰证券"
    );
    await expect(
      drawer.locator(".el-form-item__label").filter({ hasText: "证券" }).first()
    ).toBeVisible();
    // 未选标的时手续费区块不出现（v-if 挂在 selectedSecurityOption.type 上）。
    // 注意按 label 精确匹配：金额/份额的辅助文案里也有「手续费」三个字。
    await expect(
      drawer.locator(".el-form-item__label").filter({ hasText: /^手续费$/ })
    ).toHaveCount(0);
  });

  test("卖出：只列有持仓的账户，选中持仓后数量/价格/预估金额接线正常", async ({
    page
  }) => {
    test.setTimeout(240_000);
    await mockApis(page);
    const drawer = await openDrawer(page, "卖出");

    const accountItem = formItem(drawer, "选择账户");
    await accountItem.locator(".el-select").first().click();
    const dropdownOptions = page.locator(".el-select-dropdown__item:visible");
    // 空仓账户不在列表里（useSellPositions.availableAccounts 的过滤）
    await expect(
      dropdownOptions.filter({ hasText: "华泰证券" }).first()
    ).toBeVisible({ timeout: 30_000 });
    await expect(dropdownOptions.filter({ hasText: "空仓账户" })).toHaveCount(
      0
    );
    await dropdownOptions.filter({ hasText: "华泰证券" }).first().click();

    // 选完账户才出现持仓下拉（子组件的 ledgerId 分支）
    const positionItem = formItem(drawer, "选择持仓");
    await positionItem.locator(".el-select").first().click();
    const positionOption = page
      .locator(".el-select-dropdown__item:visible")
      .filter({ hasText: "贵州茅台" })
      .first();
    await expect(positionOption).toContainText("可用 200.00 份");
    await positionOption.click();

    // 持仓回填后：数量/价格/预估金额三件套（SellQuantityField 的 props 全链路）
    await expect(
      drawer.locator(".el-form-item__label").filter({ hasText: "卖出数量" })
    ).toBeVisible();
    await expect(formItem(drawer, "卖出价格")).toBeVisible();
    await expect(formItem(drawer, "预估金额")).toBeVisible();
    // 价格默认取现价（useSellPositions 的 onPositionSelect 回填口径），precision=2 显示两位
    await expect(
      formItem(drawer, "卖出价格").locator("input").first()
    ).toHaveValue("1500.00");
  });
});
