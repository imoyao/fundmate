import { expect, test } from "@playwright/test";
import { injectSupabaseSession } from "./support/session";

/**
 * 详情页区块瘦身回归网（#980 批量拆分）。
 *
 * 这一批把 `views/product/components/` 下六个区块拆成「主文件 + 子组件」，
 * 样式按「纯搬移」处理（样式声明 0 缺失 / 0 新增）。等价性脚本只能证明
 * **代码里的字符串没丢**，证明不了「拆完还渲染得出」。所以这里钉两条最深路径：
 *
 * 1. **业绩与风险**的两个分支（`perfSection/PerfFundBlock` 与 `PerfMoneyBlock`）：
 *    - 场外基金：区间收益 / 回撤 / 风险比三块齐全，0 回撤说「正在新高」；
 *    - 货币基金：只显七日年化 + 万份收益，**不显回撤类指标**（货币没有回撤口径，
 *      显了会被读成「货币也跌了」）。
 * 2. **交易记录的渐进披露**（`transactionSection/TransactionCountLine` +
 *    `TransactionMoreControls`）：
 *    - 折叠态明确写出「当前显示最近 10 条」——首版的静默截断是 #2160 的病灶；
 *    - 展开后就地变「收起」，取满上限仍看不全时给「查看全部流水」出口。
 *
 * 接口全部 page.route 打桩，不依赖后端（docs/dev/frontend-e2e.md §7）。
 */

const SYMBOL = "000961";
const NAME = "沪深300ETF联接A";

/**
 * 所有桩都锚定到「真·后端接口」这一层。
 *
 * 不能用 `/\/api\/transactions/` 这种宽松正则：dev server 下 vite 的源码模块
 * 也是走同源 HTTP 的（`/src/api/transactions.ts`），宽松正则会把它一起拦掉并
 * 返回假 JSON ⇒ 模块加载失败 ⇒ **整页白屏**，而且报错只出现在浏览器控制台里，
 * Playwright 只报「元素找不到」，非常难查。
 */
const HOST_API = /^https?:\/\/[^/]+\/api\//;

const PERF_FUND_STUB = {
  fund_kind: "fund",
  applicable: true,
  basis: "acc_nav",
  intervals: [
    { key: "1m", label: "近 1 月", value: 2.31 },
    { key: "3m", label: "近 3 月", value: -1.42 },
    { key: "1y", label: "近 1 年", value: 12.08 }
  ],
  max_drawdown: -18.52,
  max_drawdown_basis: "fixed_3y",
  max_drawdown_window: "近3年",
  max_drawdown_as_of: "2026-10-23",
  volatility_1y: 22.14,
  as_of: "2026-10-24",
  source: "天天基金",
  // 本轮回撤 0 ⇒ 文案必须是「正在新高」，而不是「0.00%」
  current_drawdown: 0,
  current_drawdown_peak_date: "2026-10-23",
  current_drawdown_days: 0,
  max_drawdown_peak_date: "2024-02-05",
  max_drawdown_trough_date: "2024-09-13",
  sharpe: 0.87,
  sortino: 1.12,
  calmar: 0.65,
  ulcer_index: 6.81,
  upi: 1.77,
  return_drawdown_ratio: 0.65,
  win_rate: 55.6,
  win_rate_period: "month",
  risk_window: "近3年",
  risk_sample_points: 731,
  risk_free_rate: 0.0215,
  risk_caveats: [],
  shape_gain2: { shape_gain2: 9.42 },
  peer_percentiles: null,
  benchmark: null
};

const PERF_MONEY_STUB = {
  fund_kind: "money",
  applicable: true,
  basis: "money_fund",
  intervals: [],
  max_drawdown: null,
  max_drawdown_basis: "insufficient",
  max_drawdown_window: null,
  max_drawdown_as_of: null,
  volatility_1y: null,
  as_of: "2026-10-24",
  source: "天天基金",
  annual_return_7d: 1.5234,
  nav_per_10k: 0.4123,
  window_days: 7,
  samples: 7,
  risk_caveats: [],
  peer_percentiles: null,
  benchmark: null
};

/** 造 N 条流水（按交易日倒序，与后端口径一致） */
function makeTransactions(count: number) {
  return Array.from({ length: count }, (_, i) => ({
    id: 1000 + i,
    ledger_id: 1,
    position_id: 1,
    position_name: NAME,
    type: "buy",
    asset_type: "fund",
    trade_date: `2026-09-${String((i % 28) + 1).padStart(2, "0")}`,
    confirm_date: `2026-09-${String((i % 28) + 2).padStart(2, "0")}`,
    quantity: 100,
    price: 1.5,
    fee: 0.15,
    amount: 150,
    status: null,
    account_name: "主账户",
    notes: null,
    source: "manual",
    created_at: "2026-09-01T10:00:00"
  }));
}

interface StubOpts {
  perf?: typeof PERF_FUND_STUB | typeof PERF_MONEY_STUB;
  /** 后端返回的该标的流水总数（决定折叠 / 展开 / 部分披露三态） */
  txnTotal?: number;
  /**
   * 是否「当前持有」。交易记录区块的挂载条件就是它（清仓用户去账本看完整流水），
   * 所以要测这一块必须为 true；其余用例保持 false —— 持仓区块一并挂载会引入
   * 与本批拆分无关的取数，出问题时分不清是谁的锅。
   */
  hasPosition?: boolean;
}

async function stubDetailApis(
  page: import("@playwright/test").Page,
  opts: StubOpts = {}
) {
  const perf = opts.perf ?? PERF_FUND_STUB;
  const txnTotal = opts.txnTotal ?? 0;
  const hasPosition = opts.hasPosition ?? false;

  await page.route(HOST_API, route =>
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
  await page.route(new RegExp(HOST_API.source + "products/resolve/"), route =>
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
          has_position: hasPosition,
          source: "catalog"
        },
        message: "ok"
      }
    })
  );
  await page.route(
    new RegExp(HOST_API.source + "products/fund-performance/"),
    route => route.fulfill({ status: 200, json: { data: perf, message: "ok" } })
  );
  await page.route(
    new RegExp(HOST_API.source + "products/trade-timeline/"),
    route =>
      route.fulfill({
        status: 200,
        json: { data: { symbol: SYMBOL, contributions: [] }, message: "ok" }
      })
  );
  await page.route(new RegExp(HOST_API.source + "positions/"), route =>
    route.fulfill({
      status: 200,
      json: { data: [], total: 0, page: 1, per_page: 100, message: "ok" }
    })
  );
  // 折叠态只取 per_page=10，展开取 50 —— 按请求参数决定返回多少行
  await page.route(new RegExp(HOST_API.source + "transactions"), route => {
    const url = new URL(route.request().url());
    const perPage = Number(url.searchParams.get("per_page") ?? 10);
    const rows = Math.min(perPage, txnTotal);
    return route.fulfill({
      status: 200,
      json: {
        data: makeTransactions(rows),
        total: txnTotal,
        page: 1,
        per_page: perPage,
        message: "ok"
      }
    });
  });
}

test.describe("详情页区块瘦身（#980）", () => {
  test.setTimeout(120_000);

  test("业绩：场外基金分支三块齐全，0 回撤说「正在新高」", async ({
    context,
    baseURL,
    page
  }) => {
    await injectSupabaseSession(context, baseURL!);
    await stubDetailApis(page);
    await page.goto(`/#/fund/${SYMBOL}`);

    const perf = page.locator(".performance-section");
    await expect(perf).toBeVisible({ timeout: 60_000 });

    // 三块标题（拆分后分别由 PerfFundBlock 渲染，样式留在父页 :deep 穿透）
    for (const label of ["区间收益", "回撤", "风险比"]) {
      await expect(
        perf
          .locator(".performance-section__block-label")
          .filter({ hasText: label })
      ).toBeVisible();
    }

    // 区间收益走 RiseFallText 涨跌色，值必须真的渲染出来
    await expect(perf.getByText("近 1 月")).toBeVisible();
    await expect(perf.getByText("+2.31%")).toBeVisible();
    await expect(perf.getByText("-1.42%")).toBeVisible();

    // 本轮回撤 0 ⇒ 「正在新高」；最大回撤带窗口标签
    const facts = perf.locator(".performance-section__fact");
    const current = facts.filter({ hasText: "本轮回撤" }).first();
    await expect(current.locator(".performance-section__value")).toHaveText(
      "正在新高"
    );
    await expect(current.locator(".performance-section__sub")).toHaveText(
      "高点 2026-10-23 · 已 今天"
    );
    await expect(perf.getByText("最大回撤（近3年）")).toBeVisible();
    await expect(perf.getByText("-18.52%")).toBeVisible();

    // 风险比：比值 2 位、溃疡指数按百分比、胜率带周期
    await expect(perf.getByText("卡玛比率")).toBeVisible();
    await expect(perf.getByText("0.87")).toBeVisible();
    await expect(perf.getByText("6.81%")).toBeVisible();
    await expect(perf.getByText("胜率（月）")).toBeVisible();

    // 脚注：rf 必须写出来，否则夏普不可复核
    await expect(perf.getByText(/无风险利率/)).toBeVisible();
    await expect(perf.getByText(/一年期国债收益率近似/)).toBeVisible();
  });

  test("业绩：货币基金分支只显七日年化与万份收益", async ({
    context,
    baseURL,
    page
  }) => {
    await injectSupabaseSession(context, baseURL!);
    await stubDetailApis(page, { perf: PERF_MONEY_STUB });
    await page.goto(`/#/fund/${SYMBOL}`);

    const perf = page.locator(".performance-section");
    await expect(perf).toBeVisible({ timeout: 60_000 });

    // 脚注里也写了「万份收益 / 七日年化」，故定位限定在 KPI 区，避免严格模式撞车
    const kpi = perf.locator(".performance-section__kpi");
    await expect(kpi.getByText("七日年化")).toBeVisible();
    await expect(kpi.getByText("1.52%")).toBeVisible();
    await expect(kpi.getByText("万份收益")).toBeVisible();
    // 万份收益按净值口径 4 位 + 单位（走 formatPrice 契约，位数与原来一致）
    await expect(kpi.getByText("0.4123 元")).toBeVisible();

    // 货币基金没有回撤口径：这几项一个都不许出现
    await expect(perf.getByText("本轮回撤")).toHaveCount(0);
    await expect(perf.getByText("最大回撤（近3年）")).toHaveCount(0);
    await expect(perf.getByText("年化波动率（近1年）")).toHaveCount(0);
  });

  test("交易记录：折叠写明截断，展开后给「查看全部流水」出口", async ({
    context,
    baseURL,
    page
  }) => {
    await injectSupabaseSession(context, baseURL!);
    // total 60 > 展开上限 50 ⇒ 展开态仍看不全，第三级出口必须出现
    await stubDetailApis(page, { txnTotal: 60, hasPosition: true });
    await page.goto(`/#/fund/${SYMBOL}`);

    const txn = page.locator(".transaction-section");
    await expect(txn).toBeVisible({ timeout: 60_000 });

    // 折叠态：总数 + 「当前显示最近 10 条」同时出现（首版正是缺了后半句）
    await expect(txn.locator(".transaction-section__count")).toContainText(
      "共 60 条"
    );
    await expect(txn.locator(".transaction-section__count")).toContainText(
      "（当前显示最近 10 条）"
    );
    await expect(
      txn.locator("#transaction-detail-table .el-table__row")
    ).toHaveCount(10);

    const more = txn.locator(".transaction-section__more");
    await expect(more).toHaveText("展开全部 60 条");
    await expect(more).toHaveAttribute("aria-expanded", "false");

    await more.click();

    // 展开：就地取满 50 条，按钮变「收起」，并明示当前只是切片
    await expect(more).toHaveText("收起", { timeout: 30_000 });
    await expect(more).toHaveAttribute("aria-expanded", "true");
    await expect(
      txn.locator("#transaction-detail-table .el-table__row")
    ).toHaveCount(50);
    await expect(txn.getByText(/仅显示最近 50 条/)).toBeVisible();
    await expect(txn.getByText("查看全部流水")).toBeVisible();
    // 折叠态不该有这条出口（给多数人用不到的链接是噪声）
    await expect(txn.locator(".transaction-section__count")).not.toContainText(
      "当前显示最近"
    );

    // 收起：回到 10 行，第三级出口消失
    await more.click();
    await expect(more).toHaveText("展开全部 60 条");
    await expect(
      txn.locator("#transaction-detail-table .el-table__row")
    ).toHaveCount(10);
    await expect(txn.getByText("查看全部流水")).toHaveCount(0);
  });
});
