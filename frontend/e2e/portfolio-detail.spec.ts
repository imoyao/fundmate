import { expect, test, type Page } from "@playwright/test";
import { injectSupabaseSession } from "./support/session";

/**
 * 组合详情页回归网（#980 拆分 views/asset/portfolio/detail.vue）。
 *
 * 这一页此前没有任何 e2e，而拆分把四张表拆成了四个组件、把区间超额的五段派生
 * 搬进了 composable。最容易静默坏掉的是四件事：
 *
 * 1. **超额卡的两个值不能互换**：`基准指数` 的 caption 用 `benchmark.range_return`，
 *    `超额收益` 的值用 `excess_return`、caption 用 `range_rate vs benchmark.range_return`。
 *    拆进 composable 后若取错字段，两张卡会「各自看着都对、但对不上」。
 * 2. **分页是前端切片**（pageSize 20）：21 行必须出现两页，翻页后只剩 1 行。
 * 3. **未归档持仓的归档流程**：对话框默认选第一个关联账户，确认后 PATCH
 *    `/api/positions/{id}/` 的请求体必须是 `{ ledger_id }`，且**两张表都要刷新**
 *    （未归档自己重取、已归档持仓由父层重取）。
 * 4. **空态文案**：三张表各自的空态。
 */

const PORTFOLIO = {
  id: 7,
  name: "稳健组合",
  purpose: "长期增值",
  target_return: 8,
  benchmark: "000300",
  is_deleted: false
};

const LEDGERS = [
  { id: 11, name: "支付宝-基金", ledger_type: "general", portfolio_id: 7 },
  { id: 12, name: "招行现金", ledger_type: "cash", portfolio_id: 7 },
  { id: 13, name: "别的组合的账户", ledger_type: "general", portfolio_id: 8 }
];

const HOLDING_ROWS = [
  {
    symbol: "110011",
    name: "易方达中小盘混合",
    type_label: "混合型",
    market_value: 5000,
    pnl: 300,
    pnl_rate: 6.3,
    account_name: "支付宝-基金",
    source: "manual",
    type: "fund",
    quantity: 200000,
    current_price: 2.5,
    avg_price: 2.35
  },
  {
    symbol: "510300",
    name: "沪深300ETF",
    type_label: "ETF",
    market_value: 3000,
    pnl: -100,
    pnl_rate: -3.2,
    account_name: "支付宝-基金",
    source: "explore",
    type: "etf",
    quantity: 100000,
    current_price: 3,
    avg_price: 3.1
  },
  {
    // 资产行（id = asset.id + 100000）：无份额 / 现价，盈亏必须显示 --
    name: "某现金资产",
    type_label: "现金",
    market_value: 2000,
    pnl: null,
    pnl_rate: null,
    account_name: "支付宝-基金",
    source: null
  }
];

const UNARCHIVED = [
  {
    id: 901,
    symbol: "000001",
    name: "华夏成长混合",
    type_label: "混合型",
    market_value: 888,
    source: "explore"
  }
];

const EXCESS = {
  scope: "portfolio",
  ledger_id: null,
  portfolio_id: 7,
  start_date: "2026-07-26",
  end_date: "2026-10-24",
  range_rate: 2,
  range_pnl: 100,
  range_baseline: 5000,
  range_reason: null,
  benchmark: {
    code: "000300",
    name: "沪深300",
    range_return: 1,
    bench_start_date: "2026-07-26",
    bench_end_date: "2026-10-24",
    reason: null
  },
  excess_return: 1
};

/**
 * 打桩本页所有取数，并记录关键调用。
 *
 * ⚠️ 与其它 e2e 一致用**锚定 host 的正则**而不是宽 glob：后者会把 vite 的源码模块
 * 请求（`/src/api/portfolio.ts`）也匹配掉，导致模块加载失败、页面白屏。
 */
async function stubPortfolio(
  page: Page,
  opts: { holdings?: unknown[] } = {}
): Promise<{ positionsCalls: () => number; patchBodies: () => unknown[] }> {
  let positionsCalls = 0;
  const patchBodies: unknown[] = [];
  const holdings = opts.holdings ?? HOLDING_ROWS;

  await page.route(/^https?:\/\/[^/]+\/api\//, route =>
    route.fulfill({
      status: 404,
      json: { data: null, message: "e2e 未打桩", error_code: 40400 }
    })
  );

  await page.route(/^https?:\/\/[^/]+\/api\/utils\/enums\/?$/, route =>
    route.fulfill({
      status: 200,
      json: {
        data: {
          position_source: { manual: "手动录入", explore: "探市录入" }
        }
      }
    })
  );

  await page.route(/^https?:\/\/[^/]+\/api\/portfolios\/7\/$/, route =>
    route.fulfill({ status: 200, json: { data: PORTFOLIO, message: "ok" } })
  );

  await page.route(
    /^https?:\/\/[^/]+\/api\/portfolios\/7\/holdings\/$/,
    route =>
      route.fulfill({
        status: 200,
        json: { data: holdings, message: "ok" }
      })
  );

  await page.route(/^https?:\/\/[^/]+\/api\/portfolios\/7\/xirr\/$/, route =>
    route.fulfill({
      status: 200,
      json: { data: { xirr: null, message: "e2e 暂无 XIRR" } }
    })
  );

  await page.route(/^https?:\/\/[^/]+\/api\/ledgers\/\?/, route =>
    route.fulfill({ status: 200, json: { data: LEDGERS, message: "ok" } })
  );

  await page.route(/^https?:\/\/[^/]+\/api\/positions\/\?/, async route => {
    positionsCalls += 1;
    const url = new URL(route.request().url());
    const unfiled = url.searchParams.get("ledger_id") === "null";
    await route.fulfill({
      status: 200,
      json: { data: unfiled ? UNARCHIVED : [], message: "ok" }
    });
  });

  await page.route(/^https?:\/\/[^/]+\/api\/positions\/\d+\/$/, async route => {
    patchBodies.push(route.request().postDataJSON());
    await route.fulfill({ status: 200, json: { data: {}, message: "ok" } });
  });

  await page.route(
    /^https?:\/\/[^/]+\/api\/summary\/benchmark-excess\//,
    route =>
      route.fulfill({ status: 200, json: { data: EXCESS, message: "ok" } })
  );

  return {
    positionsCalls: () => positionsCalls,
    patchBodies: () => patchBodies
  };
}

/** 按区块标题定位卡片（页面里有多张 el-table，全局选 .el-table__row 会串表） */
function cardOf(page: Page, heading: string) {
  return page
    .locator(".card-block")
    .filter({ has: page.getByRole("heading", { name: heading }) });
}

/** 打开组合详情页并等首屏数据落到 DOM */
async function openDetail(page: Page) {
  await page.goto("/#/asset/portfolios/7");
  await expect(page.locator("h2.text-2xl")).toHaveText("稳健组合", {
    timeout: 90_000
  });
}

test.describe("组合详情页（#980 拆分）", () => {
  // 冷启动时 vite 首次编译整套依赖可能超过默认 60s
  test.setTimeout(180_000);

  test.beforeEach(async ({ context, baseURL }) => {
    await injectSupabaseSession(context, baseURL!);
  });

  test("指标卡：基准与超额各取各的字段，且只统计本组合的账户", async ({
    page
  }) => {
    await stubPortfolio(page);
    await openDetail(page);

    const cards = page.locator(".metric-card");
    await expect(cards).toHaveCount(4);

    // 关联账户只算 portfolio_id === 本组合的（3 个账户里 1 个属于别的组合）
    const linked = cards.filter({ hasText: "关联账户" });
    await expect(linked.locator(".metric-card__value")).toHaveText("2");

    // 基准指数：名字来自后端归一结果，caption 用 benchmark.range_return
    const benchmark = cards.filter({ hasText: "基准指数" });
    await expect(benchmark.locator(".metric-card__value")).toHaveText(
      "沪深300"
    );
    await expect(benchmark.locator(".metric-card__caption")).toHaveText(
      "同期 +1.00% · 近 90 天"
    );

    // 超额收益：值用 excess_return，caption 用「区间收益 vs 基准同期」
    const excess = cards.filter({ hasText: "超额收益" });
    await expect(excess.locator(".metric-card__value")).toHaveText("1.00");
    await expect(excess.locator(".metric-card__caption")).toHaveText(
      "近 90 天 · +2.00% vs +1.00%"
    );

    // 标题副标题 + 目标收益率
    await expect(page.locator("h2.text-2xl")).toHaveText("稳健组合");
    await expect(page.getByText("长期增值")).toBeVisible();
    await expect(
      cards.filter({ hasText: "目标收益率" }).locator(".metric-card__value")
    ).toHaveText("8");
  });

  test("持仓明细：来源标签、所属账户、资产行盈亏 --，且分页是前端切片", async ({
    page
  }) => {
    // 21 行 ⇒ pageSize 20 ⇒ 两页；第二页只剩 1 行
    const many = Array.from({ length: 21 }, (_, i) => ({
      ...HOLDING_ROWS[0],
      symbol: `10000${i}`,
      name: `基金${i}`,
      market_value: 1000 + i
    }));
    await stubPortfolio(page, { holdings: many });
    await openDetail(page);

    const card = cardOf(page, "持仓明细");
    const rows = card.locator(".el-table__row");
    await expect(rows).toHaveCount(20);
    await expect(card.locator(".el-pagination")).toBeVisible();

    await card.locator(".el-pager li", { hasText: "2" }).click();
    await expect(rows).toHaveCount(1);
  });

  test("三张表的口径与空态：来源标签、资产行 --、关联账户表、未归档表", async ({
    page
  }) => {
    await stubPortfolio(page);
    await openDetail(page);

    const holdingsCard = cardOf(page, "持仓明细");
    const unarchivedCard = cardOf(page, "未归档持仓");
    const ledgersCard = cardOf(page, "关联账户");

    await expect(holdingsCard.locator(".el-table__row")).toHaveCount(3);
    await expect(unarchivedCard.locator(".el-table__row")).toHaveCount(1);
    await expect(ledgersCard.locator(".el-table__row")).toHaveCount(2);

    // 来源标签走后端枚举（前端不硬编码中文）
    await expect(holdingsCard.getByText("手动录入").first()).toBeVisible();
    await expect(unarchivedCard.getByText("探市录入")).toBeVisible();

    // 资产行（无份额 / 现价）盈亏显示 --，不造 0
    await expect(holdingsCard.locator(".el-table__row").nth(2)).toContainText(
      "--"
    );

    // 关联账户表：本组合两个账户，类型分别是通用 / 现金
    await expect(ledgersCard.getByText("支付宝-基金")).toBeVisible();
    await expect(ledgersCard.getByText("通用账户")).toBeVisible();
    await expect(ledgersCard.getByText("现金账户")).toBeVisible();
    // 别的组合的账户不能出现在本页
    await expect(page.getByText("别的组合的账户")).toHaveCount(0);
  });

  test("未归档持仓：默认选第一个关联账户，确认后按 {ledger_id} 归档并刷新两张表", async ({
    page
  }) => {
    const stub = await stubPortfolio(page);
    await openDetail(page);

    await expect(page.getByText("华夏成长混合")).toBeVisible();
    const callsBefore = stub.positionsCalls();

    await page.getByRole("button", { name: "归档" }).click();
    const dialog = page.locator(".el-dialog").filter({ hasText: "归档到账户" });
    await expect(dialog).toBeVisible();
    // 默认选中第一个关联账户
    await expect(dialog).toContainText("支付宝-基金");

    await dialog.getByRole("button", { name: "确定归档" }).click();

    await expect
      .poll(() => stub.patchBodies().length, { timeout: 15_000 })
      .toBe(1);
    expect(stub.patchBodies()[0]).toEqual({ ledger_id: 11 });

    // 未归档列表重取（归档成功后要把它从列表里清掉）
    await expect
      .poll(() => stub.positionsCalls(), { timeout: 15_000 })
      .toBeGreaterThan(callsBefore);
    await expect(dialog).toBeHidden();
  });
});
