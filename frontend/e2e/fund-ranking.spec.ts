import { expect, test, type Page } from "@playwright/test";

import { injectSupabaseSession } from "./support/session";

/**
 * 「同类优选」页回归网（#980 拆分后补的行为判据）。
 *
 * 拆分为 6 个文件后，「模板与样式逐字一致」能证明视觉没变，但证明不了三件接线：
 *
 * 1. **props 下行**：rows / tableColumns / columnGroups / metric / order 从 composable
 *    → 页面 → 表格 → 基金单元格，任何一层传漏都是静默空表；
 * 2. **emit 上行**：点表头 → `sort` → 父层改 metric/order → 重取（表头高亮与箭头随之变）；
 * 3. **派生读的是同一份数据**：脚注的窗口 / 样本 / 口径版本、剔除气泡，都来自 rows 与
 *    接口返回——拆 composable 最容易在这里丢字段。
 *
 * 所以这里的断言全是「渲染结果 + 请求参数」，不测样式值；并顺带钉住三条既有口径：
 * - 双层表头 colspan 与列数逐列对齐（分组漏一个键，表头就会错位）；
 * - **UI 列首击按 asc**（越低越好，否则先把最煎熬的排前面）；
 * - 名称缺失回退代码、持仓/自选徽章各归其位。
 */

const TYPES = {
  caliber_version: 7,
  types: [
    { fund_type_id: 11, name: "偏股混合型", count: 42 },
    { fund_type_id: 12, name: "中长期纯债型", count: 8 }
  ]
};

const ROWS = [
  {
    fund_code: "110011",
    fund_name: "易方达中小盘",
    fund_type_id: 11,
    as_of: "2026-10-23T00:00:00",
    in_holdings: true,
    in_watchlist: false,
    max_drawdown: -18.42,
    current_drawdown: -3.1,
    drawdown_days: 22,
    annual_return: 12.345,
    annual_volatility: 21.5,
    ret_1m: 1.234,
    ret_3m: -2.345,
    ret_1y: 8.1,
    sharpe: 2,
    sortino: 1.2,
    calmar: 0.9,
    ulcer_index: 18.5,
    upi: 0.4,
    return_drawdown_ratio: 0.3,
    win_rate: 55.2,
    sample_points: 720,
    basis: "acc_nav",
    window_label: "近3年"
  },
  {
    // 名称缺失：页面必须回退显示代码，且不重复显示两遍
    fund_code: "000001",
    fund_name: null,
    fund_type_id: 11,
    as_of: "2026-10-23T00:00:00",
    in_holdings: false,
    in_watchlist: true,
    max_drawdown: -5.5,
    current_drawdown: -0.4,
    drawdown_days: 6,
    annual_return: 3.2,
    annual_volatility: 8.5,
    ret_1m: 0.4,
    ret_3m: 1.1,
    ret_1y: 2.2,
    sharpe: 0.5,
    sortino: 0.7,
    calmar: 0.2,
    ulcer_index: 3.4,
    upi: 0.2,
    return_drawdown_ratio: 0.1,
    win_rate: 50,
    sample_points: 730,
    basis: "acc_nav",
    window_label: "近3年"
  },
  {
    // 指标缺失：数值一律降级「—」，且不画数据条（不编造 0）
    fund_code: "519066",
    fund_name: "汇添富蓝筹",
    fund_type_id: 11,
    as_of: "2026-10-23T00:00:00",
    in_holdings: false,
    in_watchlist: false,
    max_drawdown: null,
    current_drawdown: null,
    drawdown_days: null,
    annual_return: null,
    annual_volatility: null,
    ret_1m: null,
    ret_3m: null,
    ret_1y: null,
    sharpe: null,
    sortino: null,
    calmar: null,
    ulcer_index: null,
    upi: null,
    return_drawdown_ratio: null,
    win_rate: null,
    sample_points: 700,
    basis: "insufficient",
    window_label: "近3年"
  }
];

interface StubHandle {
  /** 每次 `fund-risk-ranking/` 请求的 query（按发生顺序） */
  rankingQueries: URLSearchParams[];
}

async function stubApi(page: Page): Promise<StubHandle> {
  const rankingQueries: URLSearchParams[] = [];

  await page.route(/^https?:\/\/[^/]+\/api\//, async route => {
    const url = new URL(route.request().url());
    const path = url.pathname;

    if (path === "/api/products/fund-risk-types/") {
      return route.fulfill({
        json: { data: TYPES, message: "ok", error_code: 0 }
      });
    }
    if (path === "/api/products/fund-risk-ranking/") {
      rankingQueries.push(url.searchParams);
      const metric = url.searchParams.get("metric") ?? "sharpe";
      const order = url.searchParams.get("order") ?? "desc";
      return route.fulfill({
        json: {
          data: {
            fund_type_id: Number(url.searchParams.get("fund_type_id") ?? 11),
            metric,
            order,
            caliber_version: 7,
            rows: ROWS,
            // 剔除条数必须展示：否则「榜上只有 3 只」会被读成「同类只有 3 只」
            excluded_distorted: 5
          },
          message: "ok",
          error_code: 0
        }
      });
    }
    return route.fulfill({ json: { data: [], total: 0, message: "" } });
  });

  return { rankingQueries };
}

const table = (page: Page) => page.locator(".ranking-table");

async function openPage(page: Page) {
  await page.goto("/#/asset/fund-ranking", { waitUntil: "commit" });
  await expect(table(page)).toBeVisible({ timeout: 150_000 });
}

test.describe.configure({ mode: "serial" });

test.describe("同类优选（#980 拆分）", () => {
  test.beforeEach(async ({ context, baseURL }) => {
    await injectSupabaseSession(context, baseURL!);
  });

  test("表格结构：分组 colspan 逐列对齐、行与徽章就位、缺指标降级「—」", async ({
    page
  }) => {
    test.setTimeout(240_000);
    const stub = await stubApi(page);
    await openPage(page);

    // ① 首次加载：默认选中只数最多的类型，指标夏普、降序
    expect(stub.rankingQueries.length).toBeGreaterThan(0);
    expect(stub.rankingQueries[0].get("fund_type_id")).toBe("11");
    expect(stub.rankingQueries[0].get("metric")).toBe("sharpe");
    expect(stub.rankingQueries[0].get("order")).toBe("desc");

    // ② 双击表头：分组 colspan 之和必须等于指标列数（分组 keys 漏一个就错位）
    const groupColspans = await page
      .locator(".th-group-row .th-group")
      .evaluateAll(nodes => nodes.map(n => Number(n.getAttribute("colspan"))));
    const metricHeads = await page.locator(".th-metric-row th").count();
    expect(groupColspans).toEqual([3, 2, 4]);
    expect(groupColspans.reduce((a, b) => a + b, 0)).toBe(metricHeads);

    // ③ 三行都在；持仓/自选徽章各归其位；名称缺失回退代码且不重复
    const rows = table(page).locator("tbody tr");
    await expect(rows).toHaveCount(3);
    await expect(rows.nth(0).locator(".fund-tag--holding")).toHaveText("持仓");
    await expect(rows.nth(1).locator(".fund-tag--watch")).toHaveText("自选");
    await expect(rows.nth(2).locator(".fund-tag")).toHaveCount(0);
    const secondName = rows.nth(1).locator(".fund-link__name");
    // 名称缺失时回退代码；徽章与名称同在一个 span 内（所以用 contains 而非 exact）
    await expect(secondName).toContainText("000001");
    await expect(secondName.locator(".fund-tag--watch")).toHaveText("自选");
    await expect(rows.nth(1).locator(".fund-link__code")).toHaveCount(0);

    // ④ 数据条：夏普列（第 1 个数值列）2.0 是榜内最大 → 满条；0.5 是最小 → 4%
    const sharpeCell = (i: number) => rows.nth(i).locator("td.col-num").nth(0);
    await expect(sharpeCell(0).locator(".data-bar")).toHaveAttribute(
      "style",
      /width:\s*100%/
    );
    await expect(sharpeCell(1).locator(".data-bar")).toHaveAttribute(
      "style",
      /width:\s*4%/
    );
    // 缺指标的行：数值「—」；数据条节点仍存在但**没有宽度**（v-if 挂在 col.bar 上而非值上，
    // 这是拆分前既有行为，纯装饰、视觉无差，本轮按「零视觉变更」纪律原样保留）
    await expect(sharpeCell(2).locator(".num-text")).toHaveText("—");
    const emptyBarStyle =
      (await sharpeCell(2).locator(".data-bar").getAttribute("style")) ?? "";
    expect(emptyBarStyle).not.toMatch(/width/);

    // ⑤ 收益列带符号，风险列不带（UI=18.50 而不是 +18.50）
    const cellsOf = async (i: number) =>
      rows.nth(i).locator("td.col-num .num-text").allInnerTexts();
    const first = await cellsOf(0);
    expect(first[5]).toBe("+12.35"); // 年化收益
    expect(first[6]).toBe("+1.23"); // 近1月
    expect(first[7]).toBe("-2.35"); // 近3月
    expect(first[3]).toBe("18.50"); // UI：中性、无符号

    // ⑥ 派生读的是同一份数据：脚注的窗口 / 样本区间 / 口径版本 / 数据截至
    const footnote = page.locator(".footnote");
    await expect(footnote).toContainText("近3年");
    await expect(footnote).toContainText("700~730");
    await expect(footnote).toContainText("口径版本 7");
    await expect(footnote).toContainText("2026-10-23");

    // ⑦ 剔除条数可见（诚实降级）
    await expect(page.locator(".excluded-tip")).toContainText("5 只被剔除");
  });

  test("点表头排序：UI 列首击 asc、再击翻转，且表头高亮与 aria-sort 跟随", async ({
    page
  }) => {
    test.setTimeout(240_000);
    const stub = await stubApi(page);
    await openPage(page);

    const headOf = (label: string) =>
      page.locator(".th-metric-row th").filter({ hasText: label });

    // ① UI 列 dir=low：首击必须 asc（越低越好），否则先把最煎熬的排前面
    await headOf("UI").click();
    await expect
      .poll(() => stub.rankingQueries.at(-1)?.get("metric"))
      .toBe("ulcer_index");
    expect(stub.rankingQueries.at(-1)?.get("order")).toBe("asc");
    await expect(headOf("UI")).toHaveAttribute("aria-sort", "ascending");

    // ② 再击同一列翻转方向
    await headOf("UI").click();
    await expect
      .poll(() => stub.rankingQueries.at(-1)?.get("order"))
      .toBe("desc");
    await expect(headOf("UI")).toHaveAttribute("aria-sort", "descending");

    // ③ 换列：夏普 dir=high → 首击 desc；旧列的 aria-sort 回到 none
    await headOf("夏普").click();
    await expect
      .poll(() => stub.rankingQueries.at(-1)?.get("metric"))
      .toBe("sharpe");
    expect(stub.rankingQueries.at(-1)?.get("order")).toBe("desc");
    await expect(headOf("UI")).toHaveAttribute("aria-sort", "none");

    // ④ 表头高亮列随之切换（col-active 是「当前排序列」的视觉锚点）
    await expect(headOf("夏普")).toHaveClass(/col-active/);
    await expect(headOf("UI")).not.toHaveClass(/col-active/);

    // ⑤ 排序说明跟着变（composable 派生 + 表格 emit 的联合结果）。
    //    说明不进正文，挂在标题信息图标的 aria-label 上（也是读屏唯一能读到它的地方）。
    await expect(page.locator(".section-header__info")).toHaveAttribute(
      "aria-label",
      /按「夏普」从优到劣/
    );
  });
});
