import { expect, test, type Locator, type Page } from "@playwright/test";

import { injectSupabaseSession } from "./support/session";

/**
 * 基金转换三步向导回归网（#980 拆分 ConversionForm.vue 后补的行为判据）。
 *
 * 1702 行的「上帝表单」本轮被拆成 4 个步骤级组件 + 6 个 composable + 3 个纯函数模块
 * （`manual/conversion/`）。纯函数已有单测（payload 口径 / 幂等回执），
 * 但**拆组件最容易断的是接线**，而这条链上每一环错了都不会报错、只会算错钱：
 *
 * 1. **两栏 → 父层 form**：转出基金 / 份额 / 转入代码全部经由 `v-model:*` 回到父页，
 *    断一环则「下一步」永远禁用（`inputValid` 依赖它们）；
 * 2. **父层 → 试算请求**：`inMode` 决定发 `in_amount` 还是 `in_quantity`，
 *    「全部转出」决定 `out_quantity` 是否为 `null`——两者都是静默错；
 * 3. **试算结果 → 三个数 + 差额去向**：转出 / 费用 / 净转入来自 `estimate`，
 *    差额选项来自 `estimate.refund.options`（SegmentedControl 的 props）；
 * 4. **提交 → 结果回执**：净转入从「净额」换成「转入金额」，差额从「可改」降级为「已回到」。
 *
 * 断言只落在「填完能看到什么、请求里发了什么」，不测样式值。
 */

const LEDGERS = [
  {
    id: 1,
    name: "天天基金",
    ledger_type: "fund",
    currency: "CNY",
    is_active: true,
    fee_config: { subscription_discount: 0.1 }
  }
];

/** 分组接口的键是 ledger_id 字符串（#2372），不是账户名 */
const POSITIONS_BY_ACCOUNT = {
  "1": [
    {
      id: 11,
      ledger_id: 1,
      symbol: "000001",
      name: "华夏成长",
      market: "CN_A",
      type: "fund",
      quantity: 1234.5678,
      current_price: 2.1,
      avg_price: 1.9,
      currency: "CNY",
      confirm_date: "2026-01-05"
    }
  ]
};

const FUND_SEARCH_RESULT = [
  {
    code: "110011",
    name: "易方达中小盘",
    type: "fund",
    is_money_fund: false,
    subscription_rate: 0.015
  }
];

const ESTIMATE = {
  out: {
    symbol: "000001",
    name: "华夏成长",
    quantity: 500,
    nav: 2.1,
    amount: 1050,
    fee: 5.25,
    fee_breakdown: { redeem: 5.25, compensate: 0 },
    fee_estimated: { redeem: 5.25, compensate: 0 },
    realized_pnl_estimate: 100
  },
  in: {
    symbol: "110011",
    name: "易方达中小盘",
    nav: 3.5,
    amount: 1040,
    quantity: 297.14
  },
  net_amount: 1044.75,
  refund: {
    amount: 4.75,
    options: [
      { type: "money_fund", symbol: "000198", name: "余额宝" },
      { type: "account_cash", symbol: null, name: "账户现金" }
    ]
  },
  supplement: { amount: 0, required: false },
  trade_date: "2026-10-24",
  warnings: []
};

const SUBMIT_RESULT = {
  link_group_id: "GRP-20261024-001",
  group_no: "GRP-20261024-001",
  status: "pending",
  trade_date: "2026-10-24",
  confirm_date: "2026-10-27",
  out: ESTIMATE.out,
  in: { ...ESTIMATE.in, position_id: 99 },
  refund: { amount: 4.75, mode: "money_fund", txn_id: 7 },
  warnings: []
};

type Call = { path: string; body: Record<string, unknown> };

/** 记录转换相关的请求体，供「发了什么」类断言使用 */
async function mockApis(page: Page): Promise<Call[]> {
  const calls: Call[] = [];
  await page.route(/^https?:\/\/[^/]+\/api\//, async route => {
    const url = new URL(route.request().url());
    const body = () =>
      (route.request().postDataJSON() ?? {}) as Record<string, unknown>;

    if (url.pathname.startsWith("/api/positions/conversion")) {
      calls.push({ path: url.pathname, body: body() });
      if (url.pathname.endsWith("/estimate/")) {
        return route.fulfill({ json: { data: ESTIMATE, message: "" } });
      }
      return route.fulfill({ json: { data: SUBMIT_RESULT, message: "" } });
    }
    if (url.pathname.startsWith("/api/funds/search")) {
      return route.fulfill({ json: { data: FUND_SEARCH_RESULT, message: "" } });
    }
    if (url.pathname.startsWith("/api/positions")) {
      // group_by=account 与普通列表共用路径，一律回同一份分组数据
      return route.fulfill({
        json: { data: POSITIONS_BY_ACCOUNT, message: "" }
      });
    }
    if (url.pathname.startsWith("/api/ledgers")) {
      return route.fulfill({ json: { data: LEDGERS, message: "" } });
    }
    return route.fulfill({ json: { data: [], message: "" } });
  });
  return calls;
}

/** 按表单项标签精确定位（「转入」与「转入基金」必须分开） */
function formItem(page: Page, label: string): Locator {
  return page
    .locator(".el-form-item")
    .filter({
      has: page.locator(".el-form-item__label", {
        hasText: new RegExp(`^${label}$`)
      })
    })
    .first();
}

async function pickSelectOption(page: Page, root: Locator, optionText: string) {
  await root.click();
  const option = page
    .locator(".el-select-dropdown__item:visible")
    .filter({ hasText: optionText })
    .first();
  await expect(option).toBeVisible({ timeout: 30_000 });
  await option.click();
}

/** 记账页 → 选基金账户 → 切到「转换」→ 选转出基金 */
async function openConversionForm(page: Page) {
  await page.goto("/#/investment/manual", { waitUntil: "commit" });
  const accountSelect = page.locator(".account-select").first();
  await expect(accountSelect).toBeVisible({ timeout: 150_000 });
  await pickSelectOption(page, accountSelect, "天天基金");

  // 操作类型是 D13 果冻胶囊（el-radio-button），不是 SegmentedControl
  await page.locator(".op-switch").getByText("转换", { exact: true }).click();

  // 默认落在「申购」（BuyForm），切走时未保存守卫会拦一次：确认放弃。
  // 这一段只关弹窗，不参与断言（未保存守卫另有 e2e 覆盖）。
  await page
    .getByRole("button", { name: "放弃修改" })
    .click({ timeout: 3_000 })
    .catch(() => undefined);

  await expect(page.getByRole("heading", { name: "转出（赎回）" })).toBeVisible(
    { timeout: 30_000 }
  );
  await pickSelectOption(
    page,
    formItem(page, "转出基金").locator(".el-select").first(),
    "华夏成长"
  );
}

/** 转入基金：remote 搜索 → 点选项（子组件 @search 回到父页的 remoteSearchFunds） */
async function pickInFund(page: Page) {
  const select = formItem(page, "转入基金").locator(".el-select").first();
  await select.click();
  await page.keyboard.type("110011");
  await page
    .locator(".el-select-dropdown__item:visible")
    .filter({ hasText: "易方达中小盘" })
    .first()
    .click();
}

test.describe("基金转换三步向导（#980 拆分后的接线判据）", () => {
  test.beforeEach(async ({ context, baseURL }) => {
    await injectSupabaseSession(context, baseURL!);
  });

  test("两栏填写：字段齐全、两条腿都填完才放行、全部转出发 null 份额", async ({
    page
  }) => {
    test.setTimeout(240_000);
    const calls = await mockApis(page);
    await openConversionForm(page);

    // 两栏并置 + 卡头进度（步骤语义只留一行字）
    await expect(
      page.getByRole("heading", { name: "转入（申购）" })
    ).toBeVisible();
    await expect(page.getByText("· 第 1 步 / 共 3 步")).toBeVisible();
    for (const label of [
      "转出基金",
      "交易日期",
      "转出份额",
      "转入基金",
      "转入"
    ]) {
      await expect(formItem(page, label)).toBeVisible();
    }

    // 选完转出基金：份额区解禁（maxQuantity 由父页 computed 传入）
    await expect(
      formItem(page, "转出份额").getByText(/持有 1234\.5678 份/)
    ).toBeVisible();
    await expect(
      formItem(page, "转入").getByText(/留空表示净额/)
    ).toBeVisible();

    // 转出腿单独填完不放行：转入基金还没选
    const next = page.getByRole("button", { name: "下一步" });
    await expect(next).toBeDisabled();

    // 快捷档位「全部」⇒ transferAll = true（payload 里 out_quantity 必须为 null）
    await formItem(page, "转出份额")
      .getByRole("tab", { name: "全部", exact: true })
      .click();
    await expect(next).toBeDisabled();

    // 转入腿：搜索 → 选中 → 两条腿齐了
    await pickInFund(page);
    await expect(next).toBeEnabled({ timeout: 30_000 });

    await next.click();
    await expect(page.getByText("· 第 2 步 / 共 3 步")).toBeVisible();

    const estimate = calls.find(c => c.path.endsWith("/estimate/"));
    expect(estimate, "进入确认页必须发起一次试算").toBeTruthy();
    expect(estimate!.body.out_position_id).toBe(11);
    // 全部转出：null（后端按持仓 4 位精确值清算），不是 1234.57 也不是 undefined
    expect(estimate!.body.out_quantity).toBeNull();
    expect(estimate!.body.in_symbol).toBe("110011");
    // 金额口径留空 ⇒ 两个口径字段都显式 null，未改费用 ⇒ fee_override null
    expect(estimate!.body.in_amount).toBeNull();
    expect(estimate!.body.in_quantity).toBeNull();
    expect(estimate!.body.fee_override).toBeNull();
    expect(estimate!.body.ledger_id).toBe(1);
  });

  test("确认页 → 改费用重算 → 提交 → 回执：三条链路全程贯通", async ({
    page
  }) => {
    test.setTimeout(240_000);
    const calls = await mockApis(page);
    await openConversionForm(page);

    // 用 1/2 档位填份额（同时覆盖「非全部」分支：out_quantity 是数字）
    await formItem(page, "转出份额")
      .getByRole("tab", { name: "1/2", exact: true })
      .click();
    await pickInFund(page);

    const next = page.getByRole("button", { name: "下一步" });
    await expect(next).toBeEnabled({ timeout: 30_000 });
    await next.click();
    await expect(page.getByText("· 第 2 步 / 共 3 步")).toBeVisible();

    const estimate = calls.find(c => c.path.endsWith("/estimate/"));
    expect(estimate).toBeTruthy();
    // 1/2 × 1234.5678 = 617.2839 → 份额最多 2 位 ⇒ 617.28
    expect(Number(estimate!.body.out_quantity)).toBeCloseTo(617.28, 1);

    // ── 三个数（ConversionFigures）──
    await expect(page.getByText(/用「华夏成长」的/)).toBeVisible();
    await expect(page.getByText("¥1050.00").first()).toBeVisible();
    await expect(page.getByText(/¥5\.25/).first()).toBeVisible();
    await expect(page.getByText("¥1044.75").first()).toBeVisible();
    // 净值走 formatPrice 契约：基金 4 位（原模板写死 toFixed(4)，拆分时改契约）
    await expect(page.getByText(/净值 2\.1000/).first()).toBeVisible();

    // ── 差额去向：SegmentedControl 拿到 estimate.refund.options ──
    await expect(page.getByText(/差额/).first()).toBeVisible();
    await expect(page.getByText("¥4.75").first()).toBeVisible();
    await expect(page.getByRole("tab", { name: "余额宝" })).toBeVisible();
    await expect(page.getByRole("tab", { name: "账户现金" })).toBeVisible();

    // ── 费用明细：默认收起（v-show，元素在 DOM 里但不可见），点开带出试算值 ──
    await expect(page.getByText("份额换算")).toBeHidden();
    await page.getByRole("button", { name: /费用明细，可修正/ }).click();
    await expect(page.getByText("份额换算")).toBeVisible();
    const redeemInput = page.locator('input[aria-label="赎回费（可修正）"]');
    await expect(redeemInput).toHaveValue("5.25");

    // 改一次费用 ⇒ dirty + 按新费用重算（fee_override 非 null）
    await redeemInput.fill("6");
    await redeemInput.blur();
    await expect(page.getByText("已修正").first()).toBeVisible();
    await expect
      .poll(() => calls.filter(c => c.path.endsWith("/estimate/")).length, {
        timeout: 30_000
      })
      .toBeGreaterThanOrEqual(2);
    const overridden = calls.filter(c => c.path.endsWith("/estimate/")).at(-1)!;
    expect(overridden.body.fee_override).toEqual({ redeem: 6, compensate: 0 });

    // 「还原」撤回人工修正
    await page.getByRole("button", { name: "还原" }).click();
    await expect(page.getByText("已修正")).toHaveCount(0);

    // ── 提交 ──
    const submitBtn = page.getByRole("button", { name: "确认转换" });
    await expect(submitBtn).toBeEnabled({ timeout: 30_000 });
    await submitBtn.click();

    const submit = calls.find(c => c.path === "/api/positions/conversion/");
    expect(submit, "点确认转换必须发起提交").toBeTruthy();
    expect(submit!.body.refund_mode).toBe("money_fund");
    expect(typeof submit!.body.idempotency_key).toBe("string");
    expect((submit!.body.idempotency_key as string).length).toBeGreaterThan(8);

    // ── 第 3 步：结果回执 ──
    await expect(page.getByText("转换已提交")).toBeVisible();
    await expect(page.getByText("申请单号 GRP-20261024-001")).toBeVisible();
    await expect(page.getByText("· 第 3 步 / 共 3 步")).toBeVisible();
    // 差额从「可改」降级为「已回到」
    await expect(page.getByText("已回到")).toBeVisible();
    await expect(page.getByText("类现金产品")).toBeVisible();
    // 净转入取 result.in.amount（1040），不是确认页的净额（1044.75）
    await expect(page.getByText("¥1040.00").first()).toBeVisible();
    await expect(
      page.getByRole("button", { name: "继续记一笔" })
    ).toBeVisible();
    await expect(
      page.getByRole("button", { name: "查看交易流水" })
    ).toBeVisible();
  });
});
