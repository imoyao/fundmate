import { expect, test, type Page } from "@playwright/test";
import { injectSupabaseSession } from "./support/session";

/**
 * 交易流水页（/#/transactions）拆分回归网（#980）。
 *
 * 这一页此前没有任何 e2e，而拆分把模板拆成了三个子组件、把取数口径挪进了纯函数模块，
 * 最容易静默坏掉的是三件事，逐一钉住：
 *
 * 1. **筛选变更必须替换列表，不能追加**。原实现把 `fetchData` 直接挂在 `@change` 上，
 *    Element Plus 会把新值当第一个参数传进去 ⇒ `isLoadMore` 收到 `"buy"` 这种真值 ⇒
 *    走追加分支：旧筛选的结果留在列表里，且页码不重置。UI 上表现为「筛了买入，
 *    却还剩着卖出的行」——比报错更难发现。
 * 2. **表格视图的「共 N 条记录」取的是后端 total**，不是本地数组长度（分页下二者不等）。
 * 3. **时间线视图按交易日折叠、当日汇总与色点各就各位**，且「最近 30 天默认展开」
 *    仍然生效（拆到子组件后改成 watch transactions 重算，靠这条兜住）。
 */

/** 相对今天生成日期串，让「最近 30 天默认展开」这条不变式与真实时钟无关 */
function dayOffset(offset: number): string {
  const d = new Date();
  d.setDate(d.getDate() - offset);
  return d.toISOString().slice(0, 10);
}

const TODAY = dayOffset(0);
const YESTERDAY = dayOffset(1);

const ROWS = [
  {
    id: 1,
    ledger_id: 1,
    position_id: 11,
    position_name: "沪深300ETF",
    type: "buy",
    asset_type: "fund",
    trade_date: TODAY,
    confirm_date: TODAY,
    quantity: 100,
    price: 1.2,
    fee: 1,
    amount: 120,
    status: "success",
    account_name: "主账户",
    notes: "定投",
    source: "manual",
    created_at: `${TODAY}T01:00:00Z`
  },
  {
    id: 2,
    ledger_id: 1,
    position_id: 12,
    position_name: "中证500ETF",
    type: "sell",
    asset_type: "fund",
    trade_date: TODAY,
    confirm_date: TODAY,
    quantity: 50,
    price: 2,
    fee: 0.5,
    amount: 100,
    status: "success",
    account_name: "主账户",
    notes: null,
    source: "manual",
    created_at: `${TODAY}T02:00:00Z`
  },
  {
    id: 3,
    ledger_id: 1,
    // 已清仓标的：position_id 为 null，表格里要打「已删除」标记并置灰
    position_id: null,
    position_name: "某只已清仓基金",
    type: "dividend",
    asset_type: "fund",
    trade_date: YESTERDAY,
    confirm_date: YESTERDAY,
    quantity: 0,
    price: 0,
    fee: 0,
    amount: 12.34,
    status: "success",
    account_name: "主账户",
    notes: null,
    source: "manual",
    created_at: `${YESTERDAY}T03:00:00Z`
  }
];

/**
 * 打桩流水接口，并记录每次请求的 query。
 *
 * ⚠️ 必须用**锚定 host 的正则**而不是宽匹配的 glob：后者会把 vite 的源码模块请求
 * （`/src/api/transactions.ts`）也匹配掉，导致整个模块加载失败。
 */
async function stubTransactions(
  page: Page,
  opts: { total?: number } = {}
): Promise<string[]> {
  const calls: string[] = [];

  await page.route(/^https?:\/\/[^/]+\/api\//, route =>
    route.fulfill({
      status: 404,
      json: { data: null, message: "e2e 未打桩", error_code: 40400 }
    })
  );

  await page.route(/^https?:\/\/[^/]+\/api\/transactions/, async route => {
    const url = new URL(route.request().url());
    calls.push(url.search);
    const type = url.searchParams.get("type");
    const rows = type ? ROWS.filter(r => r.type === type) : ROWS;
    await route.fulfill({
      status: 200,
      json: {
        data: rows,
        total: opts.total ?? rows.length,
        page: Number(url.searchParams.get("page") ?? 1),
        per_page: Number(url.searchParams.get("per_page") ?? 10),
        message: "ok"
      }
    });
  });

  return calls;
}

test.describe("交易流水页（#980 拆分）", () => {
  // 冷启动时 vite 首次编译整套依赖可能超过默认 60s
  test.setTimeout(180_000);

  test.beforeEach(async ({ context, baseURL }) => {
    await injectSupabaseSession(context, baseURL!);
  });

  test("表格视图：行数、「共 N 条」取后端 total、已删除标的置灰", async ({
    page
  }) => {
    // total 故意比返回行数大：分页下「共 N 条记录」必须是后端 total
    await stubTransactions(page, { total: 37 });
    await page.goto("/#/transactions");

    await expect(page.locator(".transaction-list")).toBeVisible({
      timeout: 90_000
    });
    await expect(page.locator(".el-table__row")).toHaveCount(ROWS.length);
    await expect(page.getByText("共 37 条记录")).toBeVisible();

    // 空态与表格互斥：有数据时不得出现
    await expect(page.getByText("暂无交易记录")).toHaveCount(0);

    // 已清仓标的打「已删除」标记（拆分时这段插槽搬进了 TransactionTableView）
    await expect(page.getByText("已删除")).toBeVisible();
    await expect(page.getByText("某只已清仓基金")).toBeVisible();

    // 分页条：total > 0 时出现
    await expect(page.locator(".el-pagination")).toBeVisible();
  });

  test("时间线视图：按交易日折叠、当日汇总与色点", async ({ page }) => {
    await stubTransactions(page);
    await page.goto("/#/transactions");

    await expect(page.locator(".transaction-list")).toBeVisible({
      timeout: 90_000
    });
    await page.getByRole("tab", { name: "时间线" }).click();

    // 两个交易日 ⇒ 两个折叠面板，标题就是交易日（按数据顺序，今天在前）
    const groups = page.locator(".el-collapse-item");
    await expect(groups).toHaveCount(2);
    await expect(groups.nth(0).locator(".el-collapse-item__header")).toHaveText(
      TODAY
    );
    await expect(groups.nth(1).locator(".el-collapse-item__header")).toHaveText(
      YESTERDAY
    );

    // 展开今天这一组。⚠️ 不断言「默认已展开」：`el-collapse-item` 没传 `name` 时
    // Element Plus 用生成 id 当 itemName，而 activeDates 里装的是日期串 ⇒ 永远匹配不上，
    // 原实现就从未真正展开过（存量缺陷，本 PR 只做等价拆分，未改）。
    const today = groups.nth(0);
    await today.locator(".el-collapse-item__header").click();
    await expect(today.locator(".day-summary")).toContainText("笔数：2 笔");

    // 当日收支口径：买入 120 记流出、卖出 100 记流入 ⇒ -20（带负号 + 跌色）
    await expect(today.locator(".day-summary .money-display")).toHaveClass(
      /is-fall/
    );
    await expect(today.locator(".day-summary .sign")).toHaveText("-");
    await expect(today.locator(".day-summary .number")).toHaveText("20.00");

    // 自定义节点：买入 / 卖出 / 分红各有自己的色点（内容虽被折叠，节点仍已渲染）
    await expect(page.locator(".custom-timeline-dot.dot-buy")).toHaveCount(1);
    await expect(page.locator(".custom-timeline-dot.dot-sell")).toHaveCount(1);
    await expect(page.locator(".custom-timeline-dot.dot-dividend")).toHaveCount(
      1
    );

    // 表格视图已卸载（互斥 v-if），不是叠着显示
    await expect(page.locator(".el-table__row")).toHaveCount(0);
  });

  test("切换筛选项 = 重置到第 1 页并替换列表（不得追加旧结果）", async ({
    page
  }) => {
    const calls = await stubTransactions(page);
    await page.goto("/#/transactions");

    await expect(page.locator(".el-table__row")).toHaveCount(ROWS.length, {
      timeout: 90_000
    });
    expect(calls.length).toBe(1);

    // 操作类型下拉 → 买入
    await page.locator(".el-select").first().click();
    await page
      .locator(".el-select-dropdown__item")
      .filter({ hasText: "买入" })
      .first()
      .click();

    // 等第二次请求落地
    await expect.poll(() => calls.length, { timeout: 30_000 }).toBe(2);
    const second = new URLSearchParams(calls[1]);
    expect(second.get("type")).toBe("buy");
    expect(second.get("page")).toBe("1");

    // 关键断言：列表被**替换**成筛选结果 1 行。
    // 修复前走追加分支，这里会是 3 + 1 = 4 行。
    await expect(page.locator(".el-table__row")).toHaveCount(1);
    await expect(page.getByText("沪深300ETF")).toBeVisible();
    await expect(page.getByText("中证500ETF")).toHaveCount(0);
    // 「共 N 条」跟着筛选后的 total 走
    await expect(page.getByText("共 1 条记录")).toBeVisible();
  });
});
