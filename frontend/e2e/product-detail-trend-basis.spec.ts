import { expect, test, type Page } from "@playwright/test";
import { injectSupabaseSession } from "./support/session";

/**
 * 走势卡口径切换回归网（#2454）：净值/价格 ↔ 业绩（区间累计收益率）。
 *
 * 钉六条不变式：
 * 1. **场外也有口径切换器**——「现在多少钱」与「这段时间赚了多少」是两个问题，
 *    场外没有 K 线但有收益（曾经的缺口：只有净值一条线）；
 * 2. 业绩序列 = 窗口内归一化（首日 0、末日 = 区间总收益）——断言方式是**读 tooltip**：
 *    ECharts 把 series 数据画在 canvas 上，轴标签读不到，但 tooltip 是 DOM，
 *    「业绩：+10.00%（净值 1.1000）」这行字出现 ⟺ 收益率序列真进了 option；
 * 3. tooltip 双给：% 与当日原价都要有（只看 % 不知道当时多少钱）；
 * 4. 脚注口径说明：业绩以**区间首日**为基准（不是成立以来，后者归业绩卡）；
 * 5. **业绩与 K 线互斥**（场内）：勾上业绩时视图切换器隐藏——K 线没有收益率画法，
 *    留一个点了没反应的选项是假可操作性（#2453 同款纪律）；切回净值即恢复；
 * 6. **成本线 null 行不进 tooltip**：首笔交易前没有持仓成本，那一行必须整行消失——
 *    旧代码 Number(null)=0 会显示「成本线：0.0000」，把「没有数据」伪装成「成本为 0」。
 *
 * 反向验证：
 * - 把 basis 切换器删掉 → 用例 1 / 2 红（找不到「业绩」）；
 * - 业绩序列改回原始 values（忘记换算）→ 用例 2 的 tooltip 断言红
 *   （出现「净值：1.1000」而非「业绩：+10.00%」；已实测：注入缺陷后 exit=1）；
 * - useCandle 去掉 basis 合取 → 用例 3 红（业绩下 K 线切换器还在 / 或 K 线照画）；
 * - 脚注基准说明删掉 → 用例 2 的脚注断言红；
 * - tooltip 恢复 Number(null)=0（不跳 null 行）→ 用例 4 红
 *   （首笔前出现「成本线：0.00%」）。
 */

const NAME = "永赢北证50成份指数发起C";
const SYMBOL = "023887";

/** 30 个自然日、净值 1.0000 → 1.1000（区间总收益恰为 +10.00%，便于精确断言） */
const TREND_DATES: string[] = [];
const TREND_VALUES: number[] = [];
for (let i = 0; i < 30; i++) {
  const d = new Date(Date.UTC(2026, 8, 22 + i)); // 2026-09-22 起
  TREND_DATES.push(d.toISOString().slice(0, 10));
  TREND_VALUES.push(+(1 + (0.1 * i) / 29).toFixed(4));
}

/** 场内 OHLC（3 根即可画 K 线：MIN_OHLC_FOR_CANDLE = 2） */
const OHLC = [
  {
    date: TREND_DATES[0],
    open: 1.0,
    close: 1.01,
    low: 0.99,
    high: 1.02,
    volume: 1000
  },
  {
    date: TREND_DATES[1],
    open: 1.01,
    close: 1.05,
    low: 1.0,
    high: 1.06,
    volume: 1200
  },
  {
    date: TREND_DATES[2],
    open: 1.05,
    close: 1.1,
    low: 1.04,
    high: 1.11,
    volume: 1500
  }
];

async function stubApis(
  page: Page,
  opts?: { withOhlc?: boolean; withTimeline?: boolean }
) {
  // 未打桩的一律 404（组件走降级），后注册的 route 优先
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
        data: {
          asset_type: { fund: "基金", etf: "ETF" },
          market: { CN_A: "A股" },
          venue: { OTC: "场外", EXCHANGE: "场内" }
        },
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
          venue: "OTC",
          display_name: NAME,
          in_watchlist: true,
          has_position: opts?.withTimeline ? true : false,
          source: "position"
        },
        message: "ok"
      }
    })
  );
  await page.route("**/api/products/fund-profile/**", route =>
    route.fulfill({
      status: 200,
      json: {
        data: {
          fund_code: SYMBOL,
          name: NAME,
          fund_type: "指数型-股票",
          company: "永赢基金管理有限公司",
          unit_nav: 1.1,
          nav_date: "2026-10-21",
          change_pct: 0.5,
          source: "天天基金"
        },
        message: "ok"
      }
    })
  );
  await page.route("**/api/products/trend/**", route =>
    route.fulfill({
      status: 200,
      json: {
        data: {
          symbol: SYMBOL,
          kind: opts?.withOhlc ? "close" : "nav",
          dates: TREND_DATES,
          values: TREND_VALUES,
          source: "天天基金",
          basis: opts?.withOhlc ? "前复权收盘价" : "累计净值",
          range: "3M",
          requested_days: 90,
          available_days: 90,
          ohlc: opts?.withOhlc ? OHLC : []
        },
        message: "ok"
      }
    })
  );
  // 交易时间线（#2454 回归）：窗口中段（2026-10-05）有一笔买入——
  // 首笔前的日期成本线为 null，tooltip **不得**出现「成本线」行
  // （旧缺陷：Number(null)=0 把「没有数据」显示成「成本线：0.0000」）
  if (opts?.withTimeline) {
    await page.route("**/api/products/trade-timeline/**", route =>
      route.fulfill({
        status: 200,
        json: {
          data: {
            symbol: SYMBOL,
            points: [
              {
                txn_id: 1,
                date: "2026-10-05",
                side: "buy",
                amount_yuan: 1000,
                quantity: 1000,
                closed: false,
                confirm_date: null,
                account_name: "测试账户",
                cost_before_avg_yuan: null
              }
            ],
            cost_line: [
              { date: "2026-10-05", avg_cost_yuan: 1.0, cost_yuan: 1000 }
            ],
            contributions: [],
            profit_line: [],
            summary: {
              buy_count: 1,
              sell_count: 0,
              dividend_count: 0,
              total_buy_amount_yuan: 1000,
              total_sell_amount_yuan: 0,
              total_fee_yuan: 0,
              total_dividend_yuan: 0,
              total_invested_yuan: 1000,
              realized_pnl_yuan: 0,
              first_trade_date: "2026-10-05",
              last_trade_date: "2026-10-05",
              current_quantity: 1000,
              current_cost_yuan: 1000,
              current_avg_cost_yuan: 1.0
            }
          },
          message: "ok"
        }
      })
    );
  }
}

/** 把鼠标送到图区指定横向比例处，返回图区内可见文本（tooltip 是 DOM）。
    `fromPlotLeft` 给出相对**绘图区左缘**的像素偏移（grid left 固定 52px，
    比例模式在窄图区会落到 y 轴刻度区之外，axisPointer 不触发）。 */
async function tooltipTextAt(
  page: Page,
  ratio: number,
  fromPlotLeft?: number
): Promise<string> {
  const box = await page.locator(".trend-section__chart").boundingBox();
  expect(box).not.toBeNull();
  const x =
    fromPlotLeft === undefined
      ? box!.x + box!.width * ratio
      : box!.x + 52 + fromPlotLeft;
  const y = box!.y + box!.height * 0.5;
  for (let i = 0; i < 12; i++) {
    await page.mouse.move(x + i * 0.5, y); // 微移触发 axisPointer 刷新
    await page.waitForTimeout(80);
    const text = await page.evaluate(() => {
      const root = document.querySelector(".trend-section__chart");
      return root ? (root as HTMLElement).innerText : "";
    });
    if (text.includes("业绩") || text.includes("净值")) return text;
  }
  return page.evaluate(() => {
    const root = document.querySelector(".trend-section__chart");
    return root ? (root as HTMLElement).innerText : "";
  });
}

test.describe("走势卡口径切换：净值 / 业绩（#2454）", () => {
  test.setTimeout(180_000);

  test.beforeEach(async ({ context, baseURL }) => {
    await injectSupabaseSession(context, baseURL!);
  });

  test("场外：默认净值口径，tooltip 给四位小数净值（精度契约）", async ({
    page
  }) => {
    await stubApis(page);
    await page.goto(`/#/fund/${SYMBOL}`);
    await expect(page.locator(".trend-section__chart canvas")).toBeVisible({
      timeout: 60_000
    });

    // 口径切换器在场外也存在（曾经的缺口：只有净值一条线）
    const basis = page.getByRole("tablist", { name: "切换走势口径" });
    await expect(basis).toBeVisible();
    await expect(basis.getByText("净值")).toBeVisible();
    await expect(basis.getByText("业绩")).toBeVisible();

    // 默认净值：tooltip 给净值（4 位，pricePrecision 契约），脚注无基准说明
    const text = await tooltipTextAt(page, 0.97);
    expect(text).toContain("净值：1.1000");
    await expect(page.locator(".trend-section__footnote")).not.toContainText(
      "业绩以区间首日"
    );
  });

  test("业绩口径：tooltip 双给（收益率% + 当日净值）+ 脚注基准说明", async ({
    page
  }) => {
    await stubApis(page);
    await page.goto(`/#/fund/${SYMBOL}`);
    await expect(page.locator(".trend-section__chart canvas")).toBeVisible({
      timeout: 60_000
    });

    await page
      .getByRole("tablist", { name: "切换走势口径" })
      .getByText("业绩")
      .click();

    // ① tooltip：序列真换成了收益率（末日 = 区间总收益 +10.00%），
    //    且括号附当日净值——只看 % 不知道当时多少钱
    const text = await tooltipTextAt(page, 0.97);
    expect(text).toContain("业绩：+10.00%（净值 1.1000）");
    // 首日方向：区间起点收益恒 0（归一化基准）。从绘图区左缘内偏 12px 进——
    // 用比例会落到 y 轴刻度区（grid left 固定 52px），axisPointer 不触发。
    // 0 不带 + 号：formatReturnPercent 钉住的纪律（无符号天然表达「不赚不亏」）
    const head = await tooltipTextAt(page, 0, 12);
    expect(head).toContain("业绩：0.00%（净值 1.0000）");

    // ② 脚注口径说明：基准是区间首日，不是成立以来
    await expect(page.locator(".trend-section__footnote")).toContainText(
      "业绩以区间首日净值为基准"
    );
  });

  test("场内：业绩与 K 线互斥——业绩口径隐藏视图切换器，切回净值即恢复", async ({
    page
  }) => {
    await stubApis(page, { withOhlc: true });
    await page.goto(`/#/fund/${SYMBOL}`);
    await expect(page.locator(".trend-section__chart canvas")).toBeVisible({
      timeout: 60_000
    });

    const viewToggle = page.getByRole("tablist", { name: "切换走势视图" });
    // 净值口径 + 有 OHLCV → 视图切换器在（K 线默认）
    await expect(viewToggle).toBeVisible();

    // 勾上业绩 → K 线没有收益率画法，切换器必须隐藏（假可操作性）
    await page
      .getByRole("tablist", { name: "切换走势口径" })
      .getByText("业绩")
      .click();
    await expect(viewToggle).toHaveCount(0);

    // 画的是折线（不是崩掉的 K 线）：tooltip 出现收益率序列。
    // 原价标签是「收盘价」不是「净值」——场内画的是收盘价，#2171 后续纪律
    const text = await tooltipTextAt(page, 0.97);
    expect(text).toContain("业绩：+10.00%（收盘价 1.1000）");

    // 切回净值 → 切换器恢复（K 线默认视图不变）。
    // 场内第一项标签是「价格」不是「净值」——折线画的是收盘价，#2171 后续纪律
    await page
      .getByRole("tablist", { name: "切换走势口径" })
      .getByText("价格")
      .click();
    await expect(viewToggle).toBeVisible();
  });

  test("成本线 null 行不进 tooltip：首笔交易前不得出现「成本线：0」（#2454 实测缺陷）", async ({
    page
  }) => {
    await stubApis(page, { withTimeline: true });
    await page.goto(`/#/fund/${SYMBOL}`);
    await expect(page.locator(".trend-section__chart canvas")).toBeVisible({
      timeout: 60_000
    });
    await page
      .getByRole("tablist", { name: "切换走势口径" })
      .getByText("业绩")
      .click();

    // 首笔买入在窗口中段（2026-10-05）：悬停其之前的日期（绘图区左缘），
    // tooltip 有业绩行、**没有**成本线行——null 被 Number() 压成 0 的旧缺陷
    // 会显示「成本线：0.00%」，把「没有数据」伪装成「成本为 0」
    const before = await tooltipTextAt(page, 0, 12);
    expect(before).toContain("业绩：");
    expect(before).not.toContain("成本线");

    // 买入日之后：成本线行正常出现（换算成同基准收益率）
    const after = await tooltipTextAt(page, 0.97);
    expect(after).toContain("成本线：");
    expect(after).toMatch(/成本线：[+-]?\d+\.\d{2}%/);
  });
});
