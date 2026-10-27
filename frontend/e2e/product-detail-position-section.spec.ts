import { expect, test } from "@playwright/test";
import { injectSupabaseSession } from "./support/session";

/**
 * 详情页「我的持仓」两种形态回归网（#980 拆分 `ProductPositionSection.vue` 后重建）。
 *
 * 拆分把渲染切成三个组件（网格 / 表格 / 账户名），父组件只剩取数与分流。
 * 这次要钉的是**形态分流的判据本身**：
 *
 * 1. **单账户不进表格**：一条持仓走指标网格——若误留表格，用户会看到
 *    表头 + 单行 + 与那一行完全重复的「合计」行（#2005 明确要去掉的三层壳）；
 * 2. **多账户不重复表头**：两账户走一张表 + 一个 `合计` 行，且`账户`列必须是
 *    链接（未归档那组例外），不是纯文本；
 * 3. **无持仓给空态而不是空白**：`v-loading` 要能挂上，整块不能凭空消失；
 * 4. **无持仓不发 XIRR 请求**：省一次无意义往返，也避免 `—` 与真实年化混淆。
 *
 * 接口全部 page.route 打桩，不依赖后端（docs/dev/frontend-e2e.md §7）。
 */

const NAME = "沪深300ETF联接A";
const SYMBOL = "000961";

/** 一笔持仓的最小自洽构造；字段名对齐后端 `positions` 行 */
function row(over: Record<string, unknown> = {}) {
  return {
    id: 1,
    symbol: SYMBOL,
    name: NAME,
    market: "CN_A",
    type: "fund",
    currency: "CNY",
    ledger_id: 7,
    account_name: "同花顺——银河",
    quantity: 1000,
    avg_price: 2,
    market_value: 2400,
    pnl: 400,
    current_price: 2.4,
    holding_days: 120,
    prev_close: 2.3,
    day_pnl: 100,
    price_date: "2026-10-09",
    trade_date: "2026-06-01",
    ...over
  };
}

interface StubOpts {
  /** 持仓行；传 `[]` 走空态 */
  rows?: ReturnType<typeof row>[];
  /** XIRR 返回；缺省给有值 */
  xirr?: { xirr: number | null; cashflow_count: number };
}

async function stubApis(
  page: import("@playwright/test").Page,
  opts: StubOpts = {}
) {
  let xirrCalls = 0;

  await page.route(/^https?:\/\/[^/]+\/api\//, route =>
    route.fulfill({
      status: 404,
      json: { data: null, message: "e2e 未打桩", error_code: 40400 }
    })
  );

  await page.route("**/api/utils/enums/**", route =>
    route.fulfill({
      status: 200,
      json: {
        data: { asset_type: { fund: "基金" }, market: { CN_A: "A股" } },
        message: "ok"
      }
    })
  );

  await page.route("**/api/products/resolve/**", route =>
    route.fulfill({
      status: 200,
      json: {
        data: {
          symbol: SYMBOL,
          asset_type: "fund",
          market: "CN_A",
          venue: null,
          display_name: NAME,
          in_watchlist: false,
          // 区块挂载门槛：False 时整块不渲染，本用例就测不到了
          has_position: true,
          source: "catalog"
        },
        message: "ok"
      }
    })
  );

  await page.route("**/api/positions/**", route =>
    route.fulfill({
      status: 200,
      json: {
        data: opts.rows ?? [row()],
        total: (opts.rows ?? [row()]).length,
        page: 1,
        per_page: 100,
        message: "ok"
      }
    })
  );

  await page.route("**/api/performance/xirr/**", route => {
    xirrCalls += 1;
    return route.fulfill({
      status: 200,
      json: {
        data: opts.xirr ?? { xirr: 0.0812, cashflow_count: 3 },
        message: "ok"
      }
    });
  });

  return {
    get xirrCalls() {
      return xirrCalls;
    }
  };
}

test.describe("详情页「我的持仓」形态分流（#980）", () => {
  test.setTimeout(120_000);

  test("单账户：走指标网格，不出现表格与合计行", async ({
    context,
    baseURL,
    page
  }) => {
    await injectSupabaseSession(context, baseURL!);
    await stubApis(page);
    await page.goto(`/#/fund/${SYMBOL}`);

    const section = page.locator(".product-position");
    await expect(section).toBeVisible({ timeout: 120_000 });

    // 区块标题与口径说明在（SectionHeader 必须是 CardBlock 直接子节点）
    await expect(section.getByText("我的持仓")).toBeVisible();
    await expect(section.getByText("持有年化")).toBeVisible();

    // 单账户形态
    const grid = section.locator(".product-position__grid");
    await expect(grid).toBeVisible();
    await expect(grid.locator(".metric")).toHaveCount(9);

    // 账户名在网格上方，且是可点的链接（ledger_id=7）
    await expect(
      section.locator(".product-position__channel a.product-position__account")
    ).toHaveText("同花顺——银河");

    // 九项指标文案一个不少
    for (const label of [
      "持有盈亏",
      "持有盈亏率",
      "当日盈亏",
      "当日盈亏率",
      "持有金额",
      "持有份额",
      "持仓成本",
      "单位成本",
      "持仓天数"
    ]) {
      await expect(
        grid.locator(".metric__label").filter({ hasText: label }).first()
      ).toBeVisible();
    }

    // 当日盈亏的基准日注脚（#2007）：年份是噪声，只留 MM-DD
    await expect(grid.getByText("截至 10-09")).toBeVisible();

    // 形态互斥：单账户不应出现表格与合计行
    await expect(section.locator(".product-position__table")).toHaveCount(0);
    await expect(section.locator(".product-position__scroll")).toHaveCount(0);
    await expect(section.getByText("合计")).toHaveCount(0);
  });

  test("多账户：一张表管全部行 + 合计行 + 基准日说明", async ({
    context,
    baseURL,
    page
  }) => {
    await injectSupabaseSession(context, baseURL!);
    await stubApis(page, {
      rows: [
        row({ id: 1, ledger_id: 7, account_name: "同花顺——银河" }),
        row({
          id: 2,
          ledger_id: null,
          account_name: "未归档持仓",
          quantity: 500,
          avg_price: 4,
          market_value: 1800,
          pnl: -200,
          prev_close: null,
          day_pnl: null,
          price_date: null
        })
      ]
    });
    await page.goto(`/#/fund/${SYMBOL}`);

    const section = page.locator(".product-position");
    await expect(section).toBeVisible({ timeout: 120_000 });

    // 多账户形态：表格在，网格不在
    const table = section.locator("table.product-position__table");
    await expect(table).toBeVisible();
    await expect(section.locator(".product-position__grid")).toHaveCount(0);

    // 表头只出现一次（#2005 去掉的正是「每组重复一遍表头」）
    await expect(table.locator("thead")).toHaveCount(1);
    await expect(table.locator("tbody tr")).toHaveCount(2);
    await expect(table.locator("tfoot tr")).toHaveCount(1);
    await expect(table.locator("tfoot").getByText("合计")).toBeVisible();

    // 已归档账户是链接；未归档只剩只读文本（没有落点，链过去是坏链）
    await expect(
      table.locator("tbody a.product-position__account")
    ).toHaveCount(1);
    await expect(
      table.locator("tbody .product-position__account--plain")
    ).toHaveText("未归档持仓");

    // 无基准的那一行显示「—」而不是 0（0 是结论，不是数据）
    await expect(table.locator(".product-position__empty").first()).toHaveText(
      "—"
    );

    // 基准日写在表格外，不额外占一列
    await expect(section.locator(".product-position__asof")).toContainText(
      "最新基准日 2026-10-09"
    );
  });

  test("无持仓：空态提示可见，且不发 XIRR 请求", async ({
    context,
    baseURL,
    page
  }) => {
    await injectSupabaseSession(context, baseURL!);
    const api = await stubApis(page, { rows: [] });
    await page.goto(`/#/fund/${SYMBOL}`);

    const section = page.locator(".product-position");
    await expect(section).toBeVisible({ timeout: 120_000 });

    await expect(section.locator(".product-position__hint")).toHaveText(
      "当前产品暂无持仓记录。"
    );
    // 空态接管后，两种形态都不渲染
    await expect(section.locator(".product-position__grid")).toHaveCount(0);
    await expect(section.locator(".product-position__table")).toHaveCount(0);

    // 正文只剩空态提示 → 不该再打年化接口（省一次无意义往返）
    expect(api.xirrCalls).toBe(0);
  });
});
