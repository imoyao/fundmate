import { expect, test, type Page } from "@playwright/test";
import { injectSupabaseSession } from "./support/session";

/**
 * 交易流水页（/#/transactions）拆分回归网（#980）。
 *
 * 这一页此前没有任何 e2e，而拆分把模板拆成三个子组件（Toolbar / TableView /
 * TimelineView）、把展示口径收进纯函数模块 `transactionListModel.ts`。最容易
 * 静默坏掉的是四件事，逐一钉住：
 *
 * 1. **筛选变更必须替换列表，不能追加**。原实现把 `fetchData` 直接挂在 `@change`
 *    上，Element Plus 会把新值当第一个参数传进去 ⇒ `isLoadMore` 收到 `"buy"` 这种
 *    真值 ⇒ 走追加分支：旧筛选的行留在列表里，页码也不重置。UI 上表现为「筛了买入，
 *    却还剩着卖出的行」——比报错更难发现。
 * 2. **「共 N 条」取后端 total**，不是本地数组长度（分页下二者不等）。
 * 3. **时间线按月分组**（设计 §五：桌面上一天一两笔，按日分组就是一屏空折叠头），
 *    月头汇总给方向号但**不染色**（± 回答「钱进还是钱出」，不是涨跌），
 *    且默认展开最近两个**有记录的**月（不是日历上最近两月）。
 * 4. **已清仓 ≠ 已删除**：胶囊文案是「已清仓」，且整行**不打灰**（#980 曾把它
 *    打成「已删除」并置灰，等于把真实发生过的流水说成失效数据）。
 */

/** 相对今天生成日期串，让「最近两个月默认展开」这条不变式与真实时钟无关 */
function dayOffset(offset: number): string {
  const d = new Date();
  d.setDate(d.getDate() - offset);
  return d.toISOString().slice(0, 10);
}

const TODAY = dayOffset(0);
const YESTERDAY = dayOffset(1);
/** > 31 天 ⇒ 必然落在另一个月份，用来造出第二个「有记录的月」 */
const TWO_MONTHS_AGO = dayOffset(75);

const ROWS = [
  {
    id: 1,
    ledger_id: 1,
    position_id: 11,
    position_name: "沪深300ETF",
    symbol: "510300",
    position_state: "held",
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
    symbol: "510500",
    position_state: "held",
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
    position_id: 13,
    // 已清仓：判据是后端下发的 `position_state`，**不是** `position_id === null`
    // （#2343「清仓不删行」之后持仓行保留、position_id 仍有值）
    position_name: "某只已清仓基金",
    symbol: "000001",
    position_state: "cleared",
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
  },
  {
    id: 4,
    ledger_id: 1,
    position_id: 14,
    position_name: "纳指ETF",
    symbol: "513100",
    position_state: "held",
    type: "buy",
    asset_type: "fund",
    trade_date: TWO_MONTHS_AGO,
    confirm_date: TWO_MONTHS_AGO,
    quantity: 25,
    price: 2,
    fee: 0,
    amount: 50,
    status: "success",
    account_name: "主账户",
    notes: null,
    source: "manual",
    created_at: `${TWO_MONTHS_AGO}T04:00:00Z`
  }
];

/** 与 `transactionListModel.monthOf` 同口径：交易日优先 */
function monthOf(day: string): string {
  return (day || "").slice(0, 7);
}

function monthLabel(month: string): string {
  const [year, mon] = month.split("-");
  return `${year} 年 ${Number(mon)} 月`;
}

/** 后端已按有效交易日倒序返回，分组保持插入顺序 ⇒ 这里照抄一份期望顺序 */
const EXPECTED_MONTHS = ROWS.reduce<string[]>((acc, row) => {
  const month = monthOf(row.trade_date);
  if (!acc.includes(month)) acc.push(month);
  return acc;
}, []);

/** 流入为正、流出为负（与 `transactionListModel.signedAmount` 同口径） */
const INFLOW_TYPES = ["sell", "dividend", "deposit"];

function rowsIn(month: string) {
  return ROWS.filter(row => monthOf(row.trade_date) === month);
}

function netOf(rows: typeof ROWS): number {
  return rows.reduce(
    (sum, row) =>
      sum +
      (INFLOW_TYPES.includes(row.type)
        ? Number(row.amount)
        : -Number(row.amount)),
    0
  );
}

function sumOf(rows: typeof ROWS, type: string): number {
  return rows
    .filter(row => row.type === type)
    .reduce((sum, row) => sum + Number(row.amount), 0);
}

/**
 * 打桩交易流水接口，并记录每次**列表**请求的 query。
 *
 * 两条刻意写法：
 * - 未打桩的 `/api/` 一律 404 兜底，但必须用**锚定 host 的正则**而不是宽 glob：
 *   后者会把 vite 的源码模块请求（`/src/api/transactions.ts`）也吃掉，模块加载失败。
 * - 列表正则必须**锚定路径结尾**（`/api/transactions(\?|$)`）。写成前缀匹配
 *   `/api/transactions` 会把汇总条的 `GET /api/transactions/summary` 也算成列表请求，
 *   「首次进入只发一次列表请求」的断言就会假失败（本仓曾这样误判过）。
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

  await page.route(
    /^https?:\/\/[^/]+\/api\/transactions(\?|$)/,
    async route => {
      const url = new URL(route.request().url());
      calls.push(url.search);
      const type = url.searchParams.get("type");
      const rows = type ? ROWS.filter(row => row.type === type) : ROWS;
      // total 的「放大」只对未筛选请求生效：筛过之后 total 必须跟着筛选结果走，
      // 否则「共 N 条」会一直显示桩里那个 37，等于把这条不变式测空了
      const total = type ? rows.length : (opts.total ?? rows.length);
      await route.fulfill({
        status: 200,
        json: {
          data: rows,
          total,
          page: Number(url.searchParams.get("page") ?? 1),
          per_page: Number(url.searchParams.get("per_page") ?? 10),
          message: "ok"
        }
      });
    }
  );

  return calls;
}

test.describe("交易流水页（#980 拆分）", () => {
  // 冷启动时 vite 首次编译整套依赖可能超过默认 60s
  test.setTimeout(180_000);

  test.beforeEach(async ({ context, baseURL }) => {
    await injectSupabaseSession(context, baseURL!);
  });

  test("表格视图：行数、「共 N 条」取后端 total、已清仓不打灰", async ({
    page
  }) => {
    // total 故意比返回行数大：分页下「共 N 条」必须是后端 total
    await stubTransactions(page, { total: 37 });
    await page.goto("/#/transactions");

    await expect(page.locator(".transaction-list")).toBeVisible({
      timeout: 90_000
    });
    await expect(page.locator(".el-table__row")).toHaveCount(ROWS.length);

    // 卡头计数（页面自己的口径说明）与分页条 total 都取后端值
    await expect(page.locator(".txn-toolbar__count")).toContainText("共 37 条");
    await expect(page.locator(".el-pagination__total")).toHaveText("共 37 条");

    // 空态与表格互斥：有数据时不得出现
    await expect(page.getByText("没有符合条件的流水")).toHaveCount(0);

    // 已清仓行的胶囊与「不打灰」：文案是「已清仓」，不是 #980 打的「已删除」
    await expect(page.getByText("已删除")).toHaveCount(0);
    const cleared = page
      .locator(".el-table__row")
      .filter({ hasText: "某只已清仓基金" });
    // `exact` 是必须的：资产名「某只已清仓基金」本身也含「已清仓」三个字
    await expect(cleared.getByText("已清仓", { exact: true })).toBeVisible();
    // 整行不灰：灰度会让真实流水的金额和日期一起看不清
    await expect(cleared).toHaveCSS("filter", "none");
    await expect(cleared).toHaveCSS("opacity", "1");
    await expect(cleared).toContainText("12.34");

    // 分页条：total > 0 时出现
    await expect(page.locator(".el-pagination")).toBeVisible();
  });

  test("时间线视图：按月分组、月头汇总带方向号不染色、默认展开最近两月", async ({
    page
  }) => {
    const calls = await stubTransactions(page, { total: 37 });
    await page.goto("/#/transactions");

    await expect(page.locator(".transaction-list")).toBeVisible({
      timeout: 90_000
    });
    await expect(
      page.getByRole("tablist", { name: "流水视图切换" })
    ).toBeVisible();
    await page
      .getByRole("tablist", { name: "流水视图切换" })
      .getByRole("tab", { name: "时间线" })
      .click();

    // 两个月 ⇒ 两个分组，月头文案由 monthOf 推出来（不依赖具体月份）
    const heads = page.locator(".txn-month__head");
    await expect(heads).toHaveCount(EXPECTED_MONTHS.length);
    for (const [index, month] of EXPECTED_MONTHS.entries()) {
      await expect(heads.nth(index).locator(".txn-month__label")).toHaveText(
        monthLabel(month)
      );
    }

    // 「默认展开最近两个有记录的月」：拆成子组件后靠 watch(transactions) 重算，
    // 这条兜住它（重新打开页面时 prevOpen 为空 ⇒ 回到默认）
    for (let index = 0; index < EXPECTED_MONTHS.length; index += 1) {
      await expect(heads.nth(index)).toHaveAttribute("aria-expanded", "true");
    }
    await expect(page.locator("li.txn-row")).toHaveCount(ROWS.length);

    // 首月月头汇总：笔数 / 买入 / 卖出 / 净额各就各位
    const firstGroup = page.locator(".txn-timeline > section").nth(0);
    const firstRows = rowsIn(EXPECTED_MONTHS[0]);
    await expect(firstGroup.locator(".txn-month__summary")).toContainText(
      `${firstRows.length} 笔`
    );

    const metrics = firstGroup.locator(".txn-month__metric");
    await expect(metrics.nth(0).locator(".money-display .number")).toHaveText(
      sumOf(firstRows, "buy").toFixed(2)
    );
    await expect(metrics.nth(1).locator(".money-display .number")).toHaveText(
      sumOf(firstRows, "sell").toFixed(2)
    );

    // 净额：± 只表方向（流出为 -），**不染色**（`auto-color=false` ⇒ 既无 is-rise 也无 is-fall）
    const net = netOf(firstRows);
    const netDisplay = metrics.nth(2).locator(".money-display");
    await expect(netDisplay).not.toHaveClass(/is-fall/);
    await expect(netDisplay).not.toHaveClass(/is-rise/);
    await expect(netDisplay.locator(".sign")).toHaveText(net < 0 ? "-" : "+");
    await expect(netDisplay.locator(".number")).toHaveText(
      Math.abs(net).toFixed(2)
    );

    // 色点：买 / 卖 / 分红各有自己的圆点，数量跟着行数走
    await expect(page.locator(".txn-row__dot.dot-buy")).toHaveCount(
      ROWS.filter(row => row.type === "buy").length
    );
    await expect(page.locator(".txn-row__dot.dot-sell")).toHaveCount(1);
    await expect(page.locator(".txn-row__dot.dot-dividend")).toHaveCount(1);

    // 已清仓行在时间线里同样是安静胶囊，不是删除
    await expect(page.locator(".txn-row__badge")).toHaveCount(1);
    await expect(page.locator(".txn-row__badge")).toHaveText("已清仓");

    // 表格视图已卸载（互斥 v-if），不是叠着显示
    await expect(page.locator(".el-table__row")).toHaveCount(0);

    // 「加载更多」是追加：翻到第 2 页并保留已有行
    await page.getByRole("button", { name: "加载更多数据" }).click();
    await expect.poll(() => calls.length, { timeout: 30_000 }).toBe(2);
    expect(new URLSearchParams(calls[1]).get("page")).toBe("2");
    await expect(page.locator("li.txn-row")).toHaveCount(ROWS.length * 2);
  });

  test("切换筛选项 = 重置到第 1 页并替换列表（不得追加旧结果）", async ({
    page
  }) => {
    const calls = await stubTransactions(page, { total: 37 });
    await page.goto("/#/transactions");

    await expect(page.locator(".el-table__row")).toHaveCount(ROWS.length, {
      timeout: 90_000
    });
    // 首次进入只发一次列表请求（汇总条走 /api/transactions/summary，不算列表调用）
    expect(calls.length).toBe(1);

    // 先翻到第 2 页，才能验证「换筛选后页码回到 1」
    await page.locator(".el-pager li").filter({ hasText: /^2$/ }).click();
    await expect.poll(() => calls.length, { timeout: 30_000 }).toBe(2);
    expect(new URLSearchParams(calls[1]).get("page")).toBe("2");

    // 一级筛选「交易类型」是分段控制器（不是下拉）
    await page
      .getByRole("tablist", { name: "按交易类型筛选" })
      .getByRole("tab", { name: "买入" })
      .click();

    await expect.poll(() => calls.length, { timeout: 30_000 }).toBe(3);
    const third = new URLSearchParams(calls[2]);
    expect(third.get("type")).toBe("buy");
    // 关键：换筛选必须重置页码，否则会拿到「第 2 页的买入」
    expect(third.get("page")).toBe("1");

    // 关键断言：列表被**替换**成筛选结果。修复前走追加分支，这里会多出旧筛选的行
    const buyCount = ROWS.filter(row => row.type === "buy").length;
    await expect(page.locator(".el-table__row")).toHaveCount(buyCount);
    await expect(page.getByText("沪深300ETF")).toBeVisible();
    await expect(page.getByText("中证500ETF")).toHaveCount(0);
    await expect(page.locator(".txn-toolbar__count")).toContainText(
      `共 ${buyCount} 条`
    );
    await expect(page.locator(".el-pager li.is-active")).toHaveText("1");
  });
});
