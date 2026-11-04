import { expect, test, type Page } from "@playwright/test";
import { injectSupabaseSession } from "./support/session";

/**
 * #980 批 B4 回归网：收益日历（`PnlCalendar`）与区间收益归因（`PnlAttribution`）拆分后，
 * 三处「拆分最容易搬坏」的行为仍在。
 *
 * 为什么钉这三处：
 * 1. **合计行**整块搬进了 `PnlCalendarSummary.vue`，而它有两处易错的口径——
 *    金额与收益率**同时**显示（不随「金额/收益率」开关变化），以及 `range_rate === null`
 *    时显示「收益率 —」而不是 0.00%。这两条以前写在 `index.vue` 的模板里，
 *    搬进子组件时最容易被顺手写成 `v-if` 或 `?? 0`。
 * 2. **空态**搬进了 `PnlCalendarPlaceholder.vue`，判空仍由父级总控。若判空挪进子组件
 *    并写错，会把「数据缺口」说成「没有估值序列」——正是 #1812 上线首日的坑。
 * 3. **归因行**搬进了 `PnlAttributionRows.vue`，贡献条的归一分母从「父级算」改成
 *    「子组件按当前行集算」。分母算错时数值不错、只有条的宽度全一样，肉眼极难发现。
 *
 * 页面：账本详情（`/#/asset/ledgers/1`）同时挂着这两个组件，且用的是**非 hostHeader**
 * 模式（组件自画标题与控件排），因此能一起回归。
 */

test.use({ viewport: { width: 1280, height: 1000 } });

const CALENDAR_URL = /\/api\/summary\/pnl-calendar\//;
const ATTRIBUTION_URL = /\/api\/summary\/pnl-attribution\//;

/** 收益日历载荷：当月有数据、区间收益率 2.34% */
function calendarOk() {
  const now = new Date();
  const y = now.getFullYear();
  const m = String(now.getMonth() + 1).padStart(2, "0");
  const today = `${y}-${m}-${String(now.getDate()).padStart(2, "0")}`;
  return {
    ledger_id: 1,
    scope: "ledger",
    start_date: `${y}-${m}-01`,
    end_date: `${y}-${m}-28`,
    month_total: 1234.56,
    range_rate: 2.34,
    granularity: "day",
    has_any_price: true,
    coverage: {
      total_positions: 2,
      priced_positions: 2,
      unpriced_positions: 0
    },
    latest_price_date: today,
    first_txn_date: "2023-03-13",
    days: [],
    periods: []
  };
}

/** 收益日历载荷：一条价都没有（数据缺口） */
function calendarGap() {
  return {
    ...calendarOk(),
    month_total: 0,
    range_rate: null,
    has_any_price: false,
    coverage: {
      total_positions: 2,
      priced_positions: 0,
      unpriced_positions: 2
    },
    latest_price_date: null
  };
}

/** 归因载荷：两只品种，|pnl| = 100 / 50（贡献条应是 100% / 50%） */
function attributionOk() {
  return {
    scope: "ledger",
    ledger_id: 1,
    portfolio_id: null,
    start_date: "2026-09-27",
    end_date: "2026-10-27",
    total_pnl: 50,
    has_any_computable: true,
    positions: [
      {
        position_id: 1,
        name: "沪深300ETF",
        symbol: "510300",
        asset_type: "etf",
        pnl: 100,
        pct: 1.5
      },
      {
        position_id: 2,
        name: "短债基金",
        symbol: "000001",
        asset_type: "fund",
        pnl: -50,
        pct: -0.5
      }
    ],
    categories: [
      { asset_type: "etf", positions_count: 2, pnl: 100, pct: 1.5 },
      { asset_type: "fund", positions_count: 1, pnl: -50, pct: -0.5 }
    ],
    unpriced_positions: [{ position_id: 9, name: "银行理财", symbol: "LC0001" }]
  };
}

/** 归因载荷：整窗算不了（has_any_computable=false）且没有任何行 */
function attributionUncomputable() {
  return {
    ...attributionOk(),
    total_pnl: null,
    has_any_computable: false,
    positions: [],
    categories: [],
    unpriced_positions: []
  };
}

type Variant = "ok" | "gap";

/**
 * 打桩。
 *
 * ⚠️ 注册顺序 = 匹配优先级（**后注册先匹配**）：兜底最宽，必须最先注册，
 * 否则它会吃掉两个具体桩，页面静默变成「什么都加载不出来」而不报错。
 *
 * `calendarFails` 是**可开关的**：错误态用例需要「先一直失败、再切回正常」，
 * 否则点重试那一刻的状态取决于先前的请求计数，用例就会时红时绿。
 */
async function mockApis(
  page: Page,
  opts: { variant: Variant; calendarFails?: boolean }
) {
  let calendarHits = 0;
  const state = { fails: opts.calendarFails === true };

  await page.route(/^https?:\/\/[^/]+\/api\//, route =>
    route.fulfill({ json: { data: null, message: "" } })
  );

  await page.route(CALENDAR_URL, route => {
    calendarHits += 1;
    if (state.fails) {
      return route.fulfill({
        status: 500,
        json: { data: null, message: "后端炸了" }
      });
    }
    return route.fulfill({
      json: {
        data: opts.variant === "gap" ? calendarGap() : calendarOk(),
        message: ""
      }
    });
  });

  await page.route(ATTRIBUTION_URL, route =>
    route.fulfill({
      json: {
        data:
          opts.variant === "gap" ? attributionUncomputable() : attributionOk(),
        message: ""
      }
    })
  );

  return {
    calendarHits: () => calendarHits,
    /** 切回正常：模拟「后端恢复后点重试」 */
    healCalendar: () => {
      state.fails = false;
    }
  };
}

async function openLedger(page: Page) {
  await page.goto("/#/asset/ledgers/1");
  // 等组件挂出来（页面上还有别的块要等，先只等日历本身）
  await expect(page.locator(".pnl-calendar").first()).toBeVisible({
    timeout: 90_000
  });
}

test.describe("收益日历 / 收益归因拆分后回归（#980 批 B4）", () => {
  test.setTimeout(180_000);

  test.beforeEach(async ({ context, baseURL }) => {
    await injectSupabaseSession(context, baseURL!);
  });

  test("合计行：金额与收益率同时显示，且带口径说明", async ({ page }) => {
    await mockApis(page, { variant: "ok" });
    await openLedger(page);

    const summary = page.locator(".pnl-calendar__summary").first();
    await expect(summary).toBeVisible({ timeout: 30_000 });

    // 合计标签带上当前区间（日视图 = 年 + 月）
    await expect(summary.locator(".pnl-calendar__summary-label")).toContainText(
      "合计"
    );
    // 金额（1234.56）与收益率（2.34%）同处一行：任一缺失都说明搬错了
    await expect(summary).toContainText("1,234.56");
    await expect(summary).toContainText("2.34");
    // 口径说明是合计行的一部分，不能丢（用户据此理解「存取款不计入」）
    await expect(summary.locator(".pnl-calendar__summary-note")).toContainText(
      "口径：当日盈亏＝总盈亏变动，存取款不计入"
    );
  });

  test("归因行：贡献条按最大 |pnl| 归一（100% / 50%），大类副标题为「N 只」", async ({
    page
  }) => {
    await mockApis(page, { variant: "ok" });
    await openLedger(page);

    const rows = page.locator(".pnl-attribution__list .pnl-attribution__row");
    await expect(rows).toHaveCount(2, { timeout: 30_000 });

    // 归一化写在子组件里（PnlAttributionRows 按当前行集算分母）：
    // 100 与 -50 对应满格与半格。写错分母时数值照旧、只有条变一样长，肉眼难查。
    await expect(rows.nth(0).locator(".pnl-attribution__bar")).toHaveAttribute(
      "style",
      /width:\s*100%/
    );
    await expect(rows.nth(1).locator(".pnl-attribution__bar")).toHaveAttribute(
      "style",
      /width:\s*50%/
    );

    // 大类维度：副标题换成「N 只」（etf 记 2 只）
    await page
      .getByRole("tablist", { name: "归因维度" })
      .getByRole("tab", { name: "大类" })
      .click();
    await expect(rows.first().locator(".pnl-attribution__sub")).toHaveText(
      "2 只"
    );

    // 无价降级：折叠块仍在（这部分没搬，但同一个 CardBlock 里，搬行时容易连根换掉）
    await expect(page.locator(".pnl-attribution__unpriced")).toContainText(
      "另有 1 个持仓因缺少价格数据未纳入归因"
    );
  });

  test("空态：数据缺口 → 图标 + 解释，且不出现「去有数据那期」的假按钮", async ({
    page
  }) => {
    await mockApis(page, { variant: "gap" });
    await openLedger(page);

    const empty = page.locator(".pnl-calendar .pnl-calendar__placeholder");
    await expect(empty).toBeVisible({ timeout: 30_000 });
    // 说清是「数据缺口」而不是「你的持仓没有估值」
    await expect(empty).toContainText("还没有每日估值数据");
    await expect(empty).toContainText("并非账户异常");
    // 图标在（`ep:info-filled` 渲染成 svg），且此时不该有跳转按钮：
    // 判据是「priced=0 且 latest_price_date 为空」⇒ 没有可跳的去处
    await expect(empty.locator("svg")).toHaveCount(1);
    await expect(empty.getByRole("button")).toHaveCount(0);

    // 归因侧：整窗算不了时说「数据不足」，不能空着也不能说「没有持仓」
    const att = page.locator(".pnl-attribution__placeholder");
    await expect(att).toContainText("数据不足，无法计算区间贡献");
  });

  test("错误态：失败给「重试」，点一次能恢复（loading 与 error 的互斥没搬反）", async ({
    page
  }) => {
    // 一直失败：错误态必须**稳定**停在「加载失败 + 重试」上。
    // 实测首次请求失败后，页面会因账本数据到达而重挂载组件、自动再取一次
    // （同一 URL 连发两次），所以「只让首请求失败」时错误态留不住——
    // 那样的用例测的是运气，不是判据。
    const stubbed = await mockApis(page, {
      variant: "ok",
      calendarFails: true
    });
    await openLedger(page);

    const placeholder = page.locator(
      ".pnl-calendar .pnl-calendar__placeholder"
    );
    await expect(placeholder).toContainText("收益日历加载失败", {
      timeout: 60_000
    });
    // 错误态不该同时挂着「加载中」，也不该有主体内容
    await expect(placeholder).not.toContainText("加载中");
    await expect(page.locator(".pnl-calendar__summary")).toHaveCount(0);
    const before = stubbed.calendarHits();

    // 后端恢复后再点重试：这一下必须真的重新发请求（不是把错误文案清掉就完事）
    stubbed.healCalendar();
    await placeholder.getByRole("button", { name: "重试" }).click();

    await expect(page.locator(".pnl-calendar__summary").first()).toBeVisible({
      timeout: 30_000
    });
    expect(stubbed.calendarHits()).toBeGreaterThan(before);
    await expect(
      page.locator(".pnl-calendar .pnl-calendar__placeholder")
    ).toHaveCount(0);
  });
});
