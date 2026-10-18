import { expect, test } from "@playwright/test";
import { injectSupabaseSession } from "./support/session";

/**
 * 详情页 Pro 模块一「深度绩效与归因」回归网（#994 Phase 2：账户级指标接线）。
 *
 * 钉四条不变式：
 * 1. **状态位驱动挂载**：`performance.available=true` → 模块徽标「已上线」+
 *    risk / allocation 同批翻真（#994 Phase 2 模块二、三），report 仍为占位；
 *    保持「Phase N 建设中」占位；
 * 2. **账户级指标诚实渲染**：XIRR 百分比带符号、金额千分位、平仓胜率/盈亏比/
 *    持有天数逐项对齐打桩数据，脚注带 FIFO 口径与样本量；
 * 3. **「可用」≠「有数据」**：`has_account_data=false` → 引导文案（不是错误态），
 *    不编造任何数字；
 * 4. **独立降级**：pro-insight 接口失败 → 内容块降级文案，Pro 卡与模块占位
 *    照常渲染，详情页可用。
 *
 * 接口全部 page.route 打桩，不依赖后端（docs/dev/frontend-e2e.md §7）。
 * playwright.config 的 webServer env 里 VITE_PRO_PAYWALL_ENABLED=false：
 * e2e 专注内容渲染，付费墙遮罩是纯 CSS 视觉件（#2272 已验收）。
 */

const NAME = "沪深300ETF联接A";
const SYMBOL = "000961";

interface InsightOpts {
  insightStatus?: number;
  hasAccountData?: boolean;
}

async function stubProApis(
  page: import("@playwright/test").Page,
  opts?: InsightOpts
) {
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
          has_position: true,
          source: "catalog"
        },
        message: "ok"
      }
    })
  );
  await page.route("**/api/products/pro/**", route =>
    route.fulfill({
      status: 200,
      json: {
        data: {
          symbol: SYMBOL,
          asset_type: "fund",
          pro_enabled: true,
          paywall_required: false,
          modules: {
            performance: { available: true, phase: 2 },
            risk: { available: true, phase: 2 },
            allocation: { available: true, phase: 3 },
            report: { available: false, phase: 4 }
          }
        },
        message: "ok"
      }
    })
  );
  await page.route("**/api/products/pro-insight/**", route => {
    if (opts?.insightStatus) {
      return route.fulfill({
        status: opts.insightStatus,
        json: { data: null }
      });
    }
    if (opts?.hasAccountData === false) {
      return route.fulfill({
        status: 200,
        json: {
          data: {
            symbol: SYMBOL,
            asset_type: "fund",
            has_account_data: false,
            xirr: {
              xirr: 0,
              total_invested: 0,
              current_value: 0,
              total_withdrawn: 0,
              total_return: 0,
              cashflow_count: 0
            },
            behavior: {
              closed_count: 0,
              win_rate: null,
              avg_win: null,
              avg_loss: null,
              profit_loss_ratio: null,
              avg_holding_days: null,
              realized_pnl_total: null,
              cash_dividend_total: null,
              buy_count: 0,
              sell_count: 0,
              unmatched_sell_count: 0,
              unmatched_sell_shares: 0,
              caveats: []
            }
          },
          message: "ok"
        }
      });
    }
    return route.fulfill({
      status: 200,
      json: {
        data: {
          symbol: SYMBOL,
          asset_type: "fund",
          has_account_data: true,
          xirr: {
            xirr: 0.182,
            total_invested: 10000,
            current_value: 11820,
            total_withdrawn: 0,
            total_return: 1820,
            cashflow_count: 2
          },
          behavior: {
            closed_count: 3,
            win_rate: 66.67,
            avg_win: 4,
            avg_loss: -2,
            profit_loss_ratio: 2,
            avg_holding_days: 546.5,
            realized_pnl_total: 6,
            cash_dividend_total: 80,
            buy_count: 3,
            sell_count: 3,
            unmatched_sell_count: 0,
            unmatched_sell_shares: 0,
            caveats: ["部分配对的卖出不进盈亏样本"]
          }
        },
        message: "ok"
      }
    });
  });
  await page.route("**/api/positions/**", route =>
    route.fulfill({
      status: 200,
      json: { data: [], total: 0, page: 1, per_page: 100, message: "ok" }
    })
  );
}

test.describe("详情页 Pro 模块一账户级指标（#994 Phase 2）", () => {
  test.setTimeout(120_000);

  test("状态位翻真 + XIRR/行为画像全渲染", async ({
    context,
    baseURL,
    page
  }) => {
    await injectSupabaseSession(context, baseURL!);
    await stubProApis(page);
    await page.goto(`/#/fund/${SYMBOL}`);

    const pro = page.locator(".pro-section");
    // 状态位驱动：模块一/二徽标翻「已上线」，其余保持建设中占位
    await expect(pro.getByText("已上线")).toHaveCount(3);
    await expect(pro.getByText("Phase 4 建设中")).toBeVisible(); // report

    // 内容区：XIRR 小数转百分比 + 符号；金额千分位
    const perf = page.locator(".pro-perf");
    await expect(perf.getByText("持有年化（XIRR）")).toBeVisible();
    await expect(perf.getByText("+18.20%")).toBeVisible();
    await expect(perf.getByText("资金加权 · 含你的加减仓时点")).toBeVisible();
    await expect(perf.getByText("¥10,000.00")).toBeVisible(); // 总投入
    await expect(perf.getByText("¥11,820.00")).toBeVisible(); // 当前市值
    await expect(perf.getByText("+¥1,820.00")).toBeVisible(); // 累计收益
    await expect(perf.getByText("+¥6.00")).toBeVisible(); // 已实现盈亏
    await expect(perf.getByText("¥80.00")).toBeVisible(); // 现金分红

    // 行为画像四项 + 口径脚注（FIFO + 样本量）
    await expect(perf.getByText("66.67%")).toBeVisible();
    await expect(perf.getByText("2.00 倍")).toBeVisible();
    await expect(perf.getByText("547 天")).toBeVisible(); // 546.5 四舍五入
    await expect(perf.getByText("3", { exact: true })).toBeVisible(); // 平仓笔数
    await expect(
      perf.getByText(
        /账户级口径 · 基于你自己的持仓与流水 · 盈亏按 FIFO 配对自算/
      )
    ).toBeVisible();
  });

  test("无账户数据渲染引导文案（不编数字）", async ({
    context,
    baseURL,
    page
  }) => {
    await injectSupabaseSession(context, baseURL!);
    await stubProApis(page, { hasAccountData: false });
    await page.goto(`/#/fund/${SYMBOL}`);

    const perf = page.locator(".pro-perf");
    await expect(perf.getByText("这里将展示你的账户级指标")).toBeVisible();
    await expect(
      perf.getByText(/买入这只标的后，持有年化（XIRR）、平仓胜率/)
    ).toBeVisible();
    // 空数据形态下不应出现任何金额/百分比指标
    await expect(perf.getByText("¥")).toHaveCount(0);
  });

  test("pro-insight 接口失败独立降级", async ({ context, baseURL, page }) => {
    await injectSupabaseSession(context, baseURL!);
    await stubProApis(page, { insightStatus: 500 });
    await page.goto(`/#/fund/${SYMBOL}`);

    const perf = page.locator(".pro-perf");
    await expect(
      perf.getByText("账户级指标暂时取不到，稍后再来看看")
    ).toBeVisible();

    // 独立降级：模块占位卡照常渲染（断网/接口失败不拖垮 Pro 卡）
    const pro = page.locator(".pro-section");
    await expect(pro.getByText("已上线")).toHaveCount(3);
  });
});
