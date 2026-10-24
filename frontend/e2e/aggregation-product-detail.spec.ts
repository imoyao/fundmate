import { expect, test, type Page } from "@playwright/test";
import { injectSupabaseSession } from "./support/session";

/**
 * 产品详情抽屉回归网（#980 拆分 AggregationProductDetail.vue）。
 *
 * 拆分把抽屉切成「外壳 + 大数字锚点 + 持仓信息区」，并把编辑态从父层 watch
 * 挪进了子组件的 `visible` prop。最容易静默坏掉的是四件事：
 *
 * 1. **单位换算**：份额是「份×10000」、金额是「分」，换算错一位看不出来，
 *    但「持有份额」会差 10000 倍；净值走 4 位小数。
 * 2. **分摊预览与后端同算法**：按既有市值占比 → 整数分四舍五入 → 尾差归占比最大
 *    一笔，预览合计**必须严格等于输入总价**。预览错了用户会照着它做决策。
 * 3. **资金进出提示（#1217）**：后端给 `next_trading_day` 才提示，且要把日期拼进文案。
 * 4. **关闭抽屉复位编辑态**：状态挪进子组件后靠 `visible` prop 复位，
 *    漏了就会「下次打开还停在编辑态、输入框里残留上次的数字」。
 */

const SOURCE_A = {
  ledger_id: 1,
  ledger_name: "支付宝-基金",
  institution_name: "蚂蚁（杭州）基金销售有限公司",
  institution_alias: "支付宝",
  symbol: "110011",
  name: "易方达中小盘混合",
  market_value_cents: 6000,
  quantity: 15000000,
  nav_yuan: 1.23456,
  snapshot_date: "2026-10-20",
  fund_manager: "张坤",
  dividend_preference: "红利转投"
};

const SOURCE_B = {
  ledger_id: 2,
  ledger_name: "天天基金-基金",
  institution_name: "上海天天基金销售有限公司",
  institution_alias: "天天基金",
  symbol: "110011",
  name: "易方达中小盘混合",
  market_value_cents: 4000,
  quantity: 10000000,
  nav_yuan: 1.23456,
  snapshot_date: "2026-10-20",
  fund_manager: "张坤",
  dividend_preference: "现金分红"
};

/** 多渠道：两张渠道行 + 分组级分红方式 */
const GROUP_MULTI = {
  symbol: "110011",
  name: "易方达中小盘混合",
  market_value_cents: 10000,
  quantity: 25000000,
  nav_yuan: 1.23456,
  snapshot_date: "2026-10-20",
  fund_manager: "张坤",
  dividend_preference: "红利转投",
  sources: [SOURCE_A, SOURCE_B]
};

/** 单渠道：走「扩展字段」分支（销售机构 + 别名 + 账本 + 基金/交易账户） */
const GROUP_SINGLE = {
  symbol: "000001",
  name: "华夏成长混合",
  market_value_cents: 88800,
  quantity: 20000000,
  nav_yuan: 4.44,
  snapshot_date: "2026-10-18",
  fund_manager: null,
  dividend_preference: "现金分红",
  sources: [
    {
      ledger_id: 3,
      ledger_name: "招行-基金",
      institution_name: "招商银行股份有限公司",
      institution_alias: "招行",
      symbol: "000001",
      name: "华夏成长混合",
      market_value_cents: 88800,
      quantity: 20000000,
      nav_yuan: 4.44,
      snapshot_date: "2026-10-18",
      fund_account: "6225****8888",
      trade_account: "T998877"
    }
  ]
};

/**
 * 打桩聚合接口与分摊接口，并记录调用次数。
 *
 * ⚠️ 与其它 e2e 一致用**锚定 host 的正则**而不是宽 glob：后者会把 vite 的源码
 * 模块请求（`/src/api/ledger.ts`）也匹配掉，导致模块加载失败、页面白屏。
 */
async function stubAggregation(page: Page): Promise<{
  aggregationCalls: () => number;
  allocateBodies: () => unknown[];
}> {
  let aggCalls = 0;
  const allocateBodies: unknown[] = [];

  await page.route(/^https?:\/\/[^/]+\/api\//, route =>
    route.fulfill({
      status: 404,
      json: { data: null, message: "e2e 未打桩", error_code: 40400 }
    })
  );

  await page.route(
    /^https?:\/\/[^/]+\/api\/ledgers\/fund-aggregation\//,
    async route => {
      aggCalls += 1;
      await route.fulfill({
        status: 200,
        json: {
          data: {
            total_market_value_cents: 98800,
            dimension: "product",
            groups: [GROUP_MULTI, GROUP_SINGLE],
            total: 2,
            page: 1,
            page_size: 18,
            total_pages: 1,
            snapshot_date: "2026-10-18",
            snapshot_date_latest: "2026-10-20",
            nav_date: "2026-10-21",
            message: "ok"
          }
        }
      });
    }
  );

  await page.route(
    /^https?:\/\/[^/]+\/api\/positions\/allocate-value\//,
    async route => {
      allocateBodies.push(route.request().postDataJSON());
      await route.fulfill({
        status: 200,
        json: {
          data: {
            cash_flow_detected: true,
            next_trading_day: "2026-11-02",
            allocations: []
          },
          message: "ok"
        }
      });
    }
  );

  return {
    aggregationCalls: () => aggCalls,
    allocateBodies: () => allocateBodies
  };
}

/** 打开第 n 张产品卡的详情抽屉 */
async function openDetail(page: Page, index: 0 | 1) {
  await page.goto("/#/funds");
  const cards = page.locator(".card-grid .product-card");
  await expect(cards).toHaveCount(2, { timeout: 90_000 });
  await cards.nth(index).click();
  await expect(
    page.locator(".product-detail-drawer .detail-body")
  ).toBeVisible();
}

test.describe("产品详情抽屉（#980 拆分）", () => {
  // 冷启动时 vite 首次编译整套依赖可能超过默认 60s
  test.setTimeout(180_000);

  test.beforeEach(async ({ context, baseURL }) => {
    await injectSupabaseSession(context, baseURL!);
  });

  test("多渠道：四格信息的单位换算与日期口径、渠道明细与角标", async ({
    page
  }) => {
    await stubAggregation(page);
    await openDetail(page, 0);

    const drawer = page.locator(".product-detail-drawer");

    // 头部：名称 + 代码
    await expect(drawer.locator(".detail-name")).toHaveText("易方达中小盘混合");
    await expect(drawer.locator(".detail-code")).toHaveText("110011");

    // 大数字锚点：分 → 元（10000 分 = ¥100.00）
    await expect(drawer.locator(".amount-anchor .money-display")).toContainText(
      "100.00"
    );

    // 四格：份额是「份×10000」，净值 4 位，日期截成 MM-DD
    const cells = drawer.locator(".info-cell");
    await expect(cells).toHaveCount(4);
    await expect(cells.nth(0)).toContainText("持有份额");
    await expect(cells.nth(0).locator(".cell-value")).toHaveText("2,500.00");
    await expect(cells.nth(1).locator(".cell-value")).toHaveText("10-20");
    await expect(cells.nth(2).locator(".cell-value")).toHaveText("1.2346");
    await expect(cells.nth(3).locator(".cell-value")).toHaveText("10-20");

    // 基金管理人
    await expect(drawer.getByText("基金管理人：")).toBeVisible();

    // 多渠道 ⇒ 分渠道持仓详情，两行，角标取各自分红方式
    await expect(drawer.locator(".section-title")).toHaveText("分渠道持仓详情");
    const rows = drawer.locator(".channel-row");
    await expect(rows).toHaveCount(2);
    await expect(rows.nth(0)).toContainText("蚂蚁（杭州）基金销售有限公司");
    await expect(rows.nth(0)).toContainText("支付宝-基金");
    await expect(rows.nth(0).locator(".channel-dividend")).toHaveText(
      "红利转投"
    );
    await expect(rows.nth(1).locator(".channel-dividend")).toHaveText(
      "现金分红"
    );
    // 渠道份额同样要除以 10000
    await expect(rows.nth(0).locator(".ch-shares")).toHaveText("1,500.00");

    // 多渠道不渲染单渠道扩展字段
    await expect(drawer.locator(".single-channel-info")).toHaveCount(0);
  });

  test("单渠道：销售机构别名、账本名与基金/交易账户", async ({ page }) => {
    await stubAggregation(page);
    await openDetail(page, 1);

    const drawer = page.locator(".product-detail-drawer");
    await expect(drawer.locator(".detail-name")).toHaveText("华夏成长混合");
    await expect(drawer.locator(".channel-row")).toHaveCount(0);

    const single = drawer.locator(".single-channel-info");
    await expect(single).toBeVisible();
    await expect(single.getByText("销售机构：")).toBeVisible();
    await expect(single.getByText("招商银行股份有限公司")).toBeVisible();
    await expect(single.locator(".meta-alias")).toHaveText("(招行)");
    await expect(single.getByText("账本名称：")).toBeVisible();
    await expect(single.getByText("基金账户：")).toBeVisible();
    await expect(single.getByText("6225****8888")).toBeVisible();
    await expect(single.getByText("交易账户：")).toBeVisible();
    await expect(single.getByText("T998877")).toBeVisible();
  });

  test("更新总价：预览合计等于输入、保存提示资金进出并刷新，关闭后复位编辑态", async ({
    page
  }) => {
    const stub = await stubAggregation(page);
    await openDetail(page, 0);

    const drawer = page.locator(".product-detail-drawer");
    const callsBefore = stub.aggregationCalls();

    // 进入编辑态：预填当前总价（¥100.00 → 100）
    await drawer.getByRole("button", { name: "更新总价" }).click();
    const input = drawer.locator(".total-input input");
    await expect(input).toHaveValue("100.00");

    // 改成 1000：按 6000:4000 摊成 600 / 400
    await input.fill("1000");
    const previewRows = drawer.locator(".preview-row");
    await expect(previewRows).toHaveCount(2);
    await expect(previewRows.nth(0).locator(".preview-name")).toHaveText(
      "支付宝-基金"
    );
    await expect(previewRows.nth(0).locator(".preview-ratio")).toHaveText(
      "60.0%"
    );
    await expect(previewRows.nth(1).locator(".preview-ratio")).toHaveText(
      "40.0%"
    );
    // 预览合计 = 输入总价（尾差已归集，不能出现 999.99）
    await expect(drawer.locator(".preview-sum")).toContainText("1,000.00");

    await drawer.getByRole("button", { name: "保存" }).click();

    // 请求体：只带 symbol + total_value
    await expect
      .poll(() => stub.allocateBodies().length, { timeout: 15_000 })
      .toBe(1);
    expect(stub.allocateBodies()[0]).toEqual({
      symbol: "110011",
      total_value: 1000
    });

    // 资金进出提示（#1217）带上后端给的下一开盘日
    const hint = drawer.locator(".cash-flow-hint");
    await expect(hint).toBeVisible();
    await expect(hint).toContainText("2026-11-02");

    // 保存成功后回调刷新聚合数据
    await expect
      .poll(() => stub.aggregationCalls(), { timeout: 15_000 })
      .toBeGreaterThan(callsBefore);

    // 关闭再打开：编辑态必须复位（状态在子组件里，靠 visible prop 复位）
    // ⚠️ ElDrawer 关闭后内容仍留在 DOM（只是隐藏），故断言「不可见」而非「被移除」
    await drawer.locator(".el-drawer__close-btn").click();
    await expect(page.locator(".product-detail-drawer")).toBeHidden();
    await page.locator(".card-grid .product-card").nth(0).click();
    await expect(page.locator(".product-detail-drawer")).toBeVisible();
    await expect(
      page.locator(".product-detail-drawer .total-input")
    ).toHaveCount(0);
    await expect(
      page.locator(".product-detail-drawer").getByRole("button", {
        name: "更新总价"
      })
    ).toBeVisible();
  });
});
