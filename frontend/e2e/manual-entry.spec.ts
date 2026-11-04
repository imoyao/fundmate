import { expect, test, type Page } from "@playwright/test";

import { injectSupabaseSession } from "./support/session";

/**
 * 完整记账页回归网（#980 拆分 `manual/index.vue` 后补的接线判据）。
 *
 * 710 行的页面拆成 `manualView/`（账户栏 / 操作类型 / 空态 / 底部操作条 + 纯函数层）。
 * 纯函数已有单测（`manualEntryModel.spec.ts`），这里钉的是**拆组件最容易断的接线**：
 *
 * 1. **账户栏 → 父页（defineModel 回流）**：账户选在子组件里，但「操作类型 / 表单 /
 *    底部按钮」三块的显隐由父页的 `selectedLedgerId` 决定。断一环的表现是
 *    选完账户页面毫无反应——不报错，最容易被漏掉；
 * 2. **新建账户 → 回写选中**：`useManualQuickAdd` 建完账要 `emit('reload')` 刷新列表，
 *    再把新 id 写回 v-model。断一环的表现是「提示创建成功、下拉里却没有它」；
 * 3. **底部操作条的显隐**：转换走自己的向导，父页 `v-if` 要把它整条藏掉。
 *
 * 断言只落在「选完能看到什么、请求里发了什么」，不测样式值。
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
    fee_config: { commission: { rate: 0.00025, min: null } }
  }
];

/** 极简建账的返回体：id 必须非 0，否则父页不会写回选中 */
const CREATED_LEDGER = {
  id: 99,
  name: "招商银行",
  ledger_type: "bank",
  currency: "CNY",
  is_active: true,
  fee_config: {}
};

type Call = { method: string; path: string; body: Record<string, unknown> };

/** 只打桩 /api/：vite 源码模块请求不能碰，否则整页白屏 */
async function mockApis(page: Page): Promise<Call[]> {
  const calls: Call[] = [];
  let created = false;
  await page.route(/^https?:\/\/[^/]+\/api\//, async route => {
    const url = new URL(route.request().url());
    const method = route.request().method();

    if (url.pathname.startsWith("/api/ledgers")) {
      if (method === "POST") {
        const body = (route.request().postDataJSON() ?? {}) as Record<
          string,
          unknown
        >;
        calls.push({ method, path: url.pathname, body });
        created = true;
        return route.fulfill({
          json: { data: CREATED_LEDGER, message: "" }
        });
      }
      // 建账成功后父页会 emit('reload') 重新拉列表，这份要带上新建的账户
      return route.fulfill({
        json: {
          data: created ? [...LEDGERS, CREATED_LEDGER] : LEDGERS,
          message: ""
        }
      });
    }
    if (url.pathname.startsWith("/api/positions")) {
      return route.fulfill({ json: { data: [], message: "" } });
    }
    return route.fulfill({ json: { data: [], message: "" } });
  });
  return calls;
}

async function openManualPage(page: Page) {
  await page.goto("/#/investment/manual", { waitUntil: "commit" });
  await expect(page.locator(".account-bar").first()).toBeVisible({
    timeout: 150_000
  });
}

/**
 * 切换操作类型会先问一次「放弃修改」（#1891）：BuyForm 拿到 default-ledger-id 后
 * 就被判脏。这一段只负责关闭弹窗，不参与断言（未保存守卫另有 e2e 覆盖）。
 */
async function dismissDiscard(page: Page) {
  await page
    .getByRole("button", { name: "放弃修改" })
    .click({ timeout: 3_000 })
    .catch(() => undefined);
}

async function pickAccount(page: Page, name: string) {
  const select = page.locator(".account-select").first();
  await select.click();
  const option = page
    .locator(".el-select-dropdown__item:visible")
    .filter({ hasText: name })
    .first();
  await expect(option).toBeVisible({ timeout: 30_000 });
  await option.click();
}

test.describe("完整记账页（#980 拆分后的接线判据）", () => {
  test.beforeEach(async ({ context, baseURL }) => {
    await injectSupabaseSession(context, baseURL!);
  });

  test("选中账户后操作类型与底部操作条才出现（defineModel 回流到父页）", async ({
    page
  }) => {
    test.setTimeout(240_000);
    await mockApis(page);
    await openManualPage(page);

    // 判据 1：未选账户 = 空态，操作类型与底部按钮都不该存在
    await expect(page.getByText("请先从上方选择交易账户")).toBeVisible();
    await expect(page.locator(".op-switch")).toHaveCount(0);
    await expect(page.getByRole("button", { name: "确认记账" })).toHaveCount(0);

    // 判据 1（续）：选基金账户 → 6 颗胶囊（申购/赎回/红利再投/送股拆分/转换/定投）
    await pickAccount(page, "天天基金");
    const opSwitch = page.locator(".op-switch").first();
    await expect(opSwitch).toBeVisible();
    await expect(opSwitch.locator(".el-radio-button")).toHaveCount(6);
    await expect(page.getByRole("button", { name: "确认记账" })).toBeVisible();

    // 证券账户只有 4 颗（买入/卖出/现金分红/送股拆分）
    await pickAccount(page, "华泰证券");
    await expect(opSwitch.locator(".el-radio-button")).toHaveCount(4);
  });

  test("切换操作类型：切到「转换」隐藏底部操作条，切回「申购」恢复", async ({
    page
  }) => {
    test.setTimeout(240_000);
    await mockApis(page);
    await openManualPage(page);
    await pickAccount(page, "天天基金");

    const confirmBtn = page.getByRole("button", { name: "确认记账" });
    await expect(confirmBtn).toBeVisible();

    // 判据 3：转换的提交发生在向导第 3 步，全局按钮没有可提交对象 → 整条隐藏
    await page.locator(".op-switch").getByText("转换", { exact: true }).click();
    await dismissDiscard(page);
    await expect(confirmBtn).toHaveCount(0);

    // 切回申购：底部操作条要回来（父页 v-if 只认 fundOpType === 'convert'）
    await page.locator(".op-switch").getByText("申购", { exact: true }).click();
    await dismissDiscard(page);
    await expect(confirmBtn).toBeVisible();
  });

  test("极简建账：下发 channel_category，建完自动选中该账户", async ({
    page
  }) => {
    test.setTimeout(240_000);
    const calls = await mockApis(page);
    await openManualPage(page);

    // 面板默认收起，点「新建账户」才展开
    await page.getByRole("button", { name: "新建账户" }).click();
    const nameInput = page.getByPlaceholder("输入账户名称，如：华泰证券");
    await expect(nameInput).toBeVisible();

    await nameInput.fill("招商银行");
    const typeSelect = page
      .locator(".el-select")
      .filter({ hasText: "选择账户类型" })
      .first();
    await typeSelect.click();
    await page
      .locator(".el-select-dropdown__item:visible")
      .filter({ hasText: "证券" })
      .first()
      .click();

    await page.getByRole("button", { name: "创建并选择" }).click();

    // 判据 2：账户栏回显新账户名（id 经 v-model 回流到父页，再由父页下发）
    await expect(page.locator(".account-select").first()).toContainText(
      "招商银行",
      { timeout: 30_000 }
    );

    // 判据 2（续）：payload 必须是 channel_category（不是 ledger_type，见 #1101）
    // 且带证券渠道的费率初值（佣金万 2.5、免五）
    const createCall = calls.find(c => c.method === "POST");
    expect(createCall, "未发出建账请求").toBeTruthy();
    expect(createCall!.body).toMatchObject({
      name: "招商银行",
      channel_category: expect.any(String),
      fee_config: { commission: { rate: 0.00025, min: null } }
    });
    expect(createCall!.body).not.toHaveProperty("ledger_type");
  });
});
