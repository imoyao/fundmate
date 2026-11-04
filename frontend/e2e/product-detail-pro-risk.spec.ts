import { expect, test } from "@playwright/test";
import { injectSupabaseSession } from "./support/session";

/**
 * 详情页 Pro 模块二「偏离与风险控制」回归网（#994 Phase 2：BIAS + 波动率 + VaR 接线）。
 *
 * 钉四条不变式：
 * 1. **状态位驱动挂载**：`risk.available=true` → 模块内容渲染（#2523 两态拆分后
 *    已开通态无介绍卡，徽标信号并入「模块进度」行）；
 *    allocation 已翻真（#994 Phase 2 模块三提前落地），report 仍为 Phase 4 占位；
 * 2. **风险指标诚实渲染**：BIAS 带符号（正=高于均线）+ 引擎信号标签 + |BIAS|≥5 的
 *    克制提示（只讲波动风险、不做买卖建议）；年化波动率 / VaR 95% / 日收益样本
 *    逐项对齐打桩数据；账户级并示行 = 持仓市值 × VaR%；
 * 3. **块级自治**：三块全不可用且无持仓 → 引导文案（不是错误态），不编数字；
 * 4. **独立降级**：pro-risk 接口失败 → 内容块降级文案，Pro 卡与模块占位照常渲染。
 *
 * 接口全部 page.route 打桩，不依赖后端（docs/dev/frontend-e2e.md §7）。
 * playwright.config 的 webServer env 里 VITE_PRO_PAYWALL_ENABLED=false：
 * e2e 专注内容渲染，付费墙遮罩是纯 CSS 视觉件（#2272 已验收）。
 */

const NAME = "沪深300ETF联接A";
const SYMBOL = "000961";

const PRO_RISK_STUB = {
  symbol: SYMBOL,
  asset_type: "fund",
  bias: {
    available: true,
    bias: 6.2,
    label: "高位区(绿卖)",
    position: 62,
    close: 1.2345,
    data_date: "2026-10-16",
    stale: false,
    reason: null
  },
  risk: {
    available: true,
    annual_volatility: 18.35,
    var_95: -2.4,
    sample_returns: 243,
    window: "1Y",
    as_of: "2026-10-16",
    basis: "累计净值（分红不再投近似复权，缺失回退单位净值）",
    reason: null,
    caveats: ["VaR 为历史模拟法：假设过去一年的日收益分布重现，分布漂移时失效"]
  },
  account: {
    has_position: true,
    position_value: 11820,
    // 11820 × −2.40% = −283.68（前端按同式渲染，桩值必须自洽）
    var_95_yuan: -283.68
  }
};

interface RiskOpts {
  riskStatus?: number;
  empty?: boolean;
}

async function stubProApis(
  page: import("@playwright/test").Page,
  opts?: RiskOpts
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
  await page.route("**/api/products/pro-insight/**", route =>
    route.fulfill({
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
            caveats: []
          }
        },
        message: "ok"
      }
    })
  );
  await page.route("**/api/products/pro-risk/**", route => {
    if (opts?.riskStatus) {
      return route.fulfill({
        status: opts.riskStatus,
        json: { data: null }
      });
    }
    if (opts?.empty) {
      return route.fulfill({
        status: 200,
        json: {
          data: {
            symbol: SYMBOL,
            asset_type: "fund",
            bias: {
              available: false,
              bias: null,
              label: null,
              position: null,
              close: null,
              data_date: null,
              stale: false,
              reason:
                "乖离率取数失败（行情源暂不可用或历史不足 20 日），稍后再试"
            },
            risk: {
              available: false,
              annual_volatility: null,
              var_95: null,
              sample_returns: 0,
              window: "1Y",
              as_of: null,
              basis: null,
              reason:
                "该标的近一年无净值/价格序列（未同步或品类不适用），不出风险指标",
              caveats: []
            },
            account: {
              has_position: false,
              position_value: 0,
              var_95_yuan: null
            }
          },
          message: "ok"
        }
      });
    }
    return route.fulfill({
      status: 200,
      json: { data: PRO_RISK_STUB, message: "ok" }
    });
  });
  await page.route("**/api/positions/**", route =>
    route.fulfill({
      status: 200,
      json: { data: [], total: 0, page: 1, per_page: 100, message: "ok" }
    })
  );
}

test.describe("详情页 Pro 模块二风险指标（#994 Phase 2）", () => {
  test.setTimeout(120_000);

  test("状态位翻真 + BIAS/波动率/VaR 全渲染", async ({
    context,
    baseURL,
    page
  }) => {
    await injectSupabaseSession(context, baseURL!);
    await stubProApis(page);
    await page.goto(`/#/fund/${SYMBOL}`);

    const pro = page.locator(".pro-section");
    // 状态位驱动（#2523 两态拆分后）：已开通态无介绍卡，徽标信号并入「模块进度」行
    await expect(pro.locator(".pro-section__progress-text")).toHaveText(
      "已上线 3/4 · 智能报告与自动化 Phase 4 建设中"
    );

    // BIAS：带符号（正 = 高于均线）+ 引擎信号标签 + 数据日期 + 克制提示
    const risk = page.locator(".pro-risk");
    await expect(risk.getByText("净值乖离率（BIAS）")).toBeVisible();
    await expect(risk.getByText("+6.20%")).toBeVisible();
    await expect(risk.getByText("高位区(绿卖)")).toBeVisible();
    await expect(risk.getByText(/数据日期 2026-10-16/)).toBeVisible();
    await expect(
      risk.getByText(/净值明显偏离均线，短期波动风险偏高/)
    ).toBeVisible();

    // 波动率 / VaR / 样本量
    await expect(risk.getByText("年化波动率")).toBeVisible();
    await expect(risk.getByText("18.35%")).toBeVisible();
    await expect(risk.getByText("VaR 95%（单日）")).toBeVisible();
    await expect(risk.getByText("-2.40%")).toBeVisible();
    await expect(risk.getByText("243 个", { exact: true })).toBeVisible();

    // 账户级并示：持仓市值 × VaR%（11820 × −2.40% = −283.68）
    await expect(
      risk.getByText("按你的持仓市值 ¥11,820.00，95% 置信下最坏单日约 -¥283.68")
    ).toBeVisible();

    // 口径脚注：序列口径 + 数据截至 + 窗口样本 + caveat
    await expect(
      risk.getByText(/累计净值.*数据截至 2026-10-16.*近1Y窗口 · 243 个日收益/)
    ).toBeVisible();
  });

  test("三块全不可用渲染引导文案（不编数字）", async ({
    context,
    baseURL,
    page
  }) => {
    await injectSupabaseSession(context, baseURL!);
    await stubProApis(page, { empty: true });
    await page.goto(`/#/fund/${SYMBOL}`);

    const risk = page.locator(".pro-risk");
    await expect(
      risk.getByText("这里将展示乖离率、波动率与 VaR")
    ).toBeVisible();
    await expect(
      risk.getByText(/基于该标的历史净值计算价格乖离率/)
    ).toBeVisible();
    // 空数据形态下不应出现任何金额指标（引导文案自身不含 ¥）
    await expect(risk.getByText("¥")).toHaveCount(0);
  });

  test("pro-risk 接口失败独立降级", async ({ context, baseURL, page }) => {
    await injectSupabaseSession(context, baseURL!);
    await stubProApis(page, { riskStatus: 500 });
    await page.goto(`/#/fund/${SYMBOL}`);

    const risk = page.locator(".pro-risk");
    await expect(
      risk.getByText("风险指标暂时取不到，稍后再来看看")
    ).toBeVisible();

    // 独立降级：兄弟模块的状态位与内容不受影响。riskStatus=500 只打桩内容端点
    // pro-risk，状态位 pro/** 仍回三模块已上线（report Phase 4）
    const pro = page.locator(".pro-section");
    await expect(pro.locator(".pro-section__progress-text")).toHaveText(
      "已上线 3/4 · 智能报告与自动化 Phase 4 建设中"
    );
  });
});
