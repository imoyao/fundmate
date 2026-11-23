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

/** 造 n 行长榜单：吸顶 / 横滚用例需要页面真的能纵向滚动（3 行撑不出滚动容器） */
function manyRows(n: number): typeof ROWS {
  return Array.from({ length: n }, (_, i) => ({
    ...ROWS[0],
    fund_code: String(100000 + i),
    fund_name: `样本基金 ${i + 1}`,
    in_holdings: i === 0,
    in_watchlist: i === 1
  }));
}

async function stubApi(
  page: Page,
  rows: typeof ROWS = ROWS
): Promise<StubHandle> {
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
            rows,
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
      .locator(".el-table__header th.th-group")
      .evaluateAll(nodes => nodes.map(n => Number(n.getAttribute("colspan"))));
    const metricHeads = await page
      .locator(".el-table__header th.th-metric")
      .count();
    expect(groupColspans).toEqual([3, 2, 4]);
    expect(groupColspans.reduce((a, b) => a + b, 0)).toBe(metricHeads);

    // ③ 三行都在；持仓/自选徽章各归其位；名称缺失回退代码且不重复
    const rows = table(page).locator("tbody tr");
    await expect(rows).toHaveCount(3);
    await expect(rows.nth(0).locator(".fund-tag--holding")).toHaveText("持仓");
    await expect(rows.nth(1).locator(".fund-tag--watch")).toHaveText("自选");
    await expect(rows.nth(2).locator(".fund-tag")).toHaveCount(0);

    // 类型标记与名称**分居两行**：列宽 232px，徽章挂在名称行会把长名称挤断、
    // 且贴着名称末字读起来像名称的一部分（「…发起C 持仓」）。判据是结构：
    // 名称行里没有徽章，徽章在代码行（.fund-link__meta）。
    await expect(rows.nth(0).locator(".fund-link__name .fund-tag")).toHaveCount(
      0
    );
    await expect(
      rows.nth(0).locator(".fund-link__meta .fund-tag--holding")
    ).toHaveText("持仓");

    // 名称缺失时回退代码（名称行即代码），元信息行只剩徽章、不再重复一遍代码
    const secondName = rows.nth(1).locator(".fund-link__name");
    await expect(secondName).toHaveText("000001");
    await expect(
      rows.nth(1).locator(".fund-link__meta .fund-tag--watch")
    ).toHaveText("自选");
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

    // ⑥ 派生读的是同一份数据：脚注的窗口 / 样本区间 / 口径版本
    const footnote = page.locator(".footnote");
    await expect(footnote).toContainText("近3年");
    await expect(footnote).toContainText("700~730");
    await expect(footnote).toContainText("口径版本 7");

    // ⑥b 数据截至（#3215 上移到页头胶囊）：脚注不再重复同一个日期——
    //     旧实现日期只在脚注里，长榜滚到底才看得见；现在两者互斥，任一出现都算回归。
    await expect(page.locator(".page-header__updated")).toHaveText(
      /数据截至\s*2026-10-23/
    );
    await expect(footnote).not.toContainText("2026-10-23");

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
      page.locator(".el-table__header th.th-metric").filter({ hasText: label });

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
    // 未参与排序的可排序列：el-table 写的是 aria-sort=""（空串即「未声明方向」，
    // 与 "none" 等效——非法值会被读屏器忽略）。这里钉的是「旧列不再声称方向」，
    // 不是某个字符串：若旧列仍挂着 descending，本断言即转红。
    expect(await headOf("UI").getAttribute("aria-sort")).toBe("");

    // ④ 表头高亮列随之切换（col-active 是「当前排序列」的视觉锚点）
    await expect(headOf("夏普")).toHaveClass(/col-active/);
    await expect(headOf("UI")).not.toHaveClass(/col-active/);

    // ④b 数据区**不**再挂这个类：旧实现给整列铺 --brand-200 暖色带，与夏普 /
    //     卡玛的数据条叠在一起（条比带浅，读成「带上的白色缺口」）。锚点只留表头。
    await expect(table(page).locator("tbody td.col-active")).toHaveCount(0);

    // ⑤ 排序说明跟着变（composable 派生 + 表格 emit 的联合结果）。
    //    说明不进正文，挂在标题信息图标的 aria-label 上（也是读屏唯一能读到它的地方）。
    await expect(page.locator(".section-header__info")).toHaveAttribute(
      "aria-label",
      /按「夏普」从优到劣/
    );
  });

  test("类型筛选：带只数的分段控制器，一次点击即换类取榜", async ({ page }) => {
    test.setTimeout(240_000);
    const stub = await stubApi(page);
    await openPage(page);

    // ① 类型只有 5 类（一级主维度 2–6）⇒ 平铺分段控制器，不是下拉框。
    //    旧的 240px 下拉框 + 叠在上面的「基金类型」微标签占两行 60px，
    //    选完还看不到别的类型各有几只；#3215 换成平铺 + 计数。
    await expect(page.locator("#fund-type")).toHaveCount(0);
    const seg = page.locator(".segmented-control");
    await expect(seg).toHaveCount(1);
    const items = seg.locator(".segmented-control__item");
    await expect(items).toHaveCount(2);

    // ② 只数直接挂在选项上（「（共 42 只）」不再只活在下拉面板里）
    await expect(items.nth(0)).toContainText("偏股混合型");
    await expect(items.nth(0).locator(".segmented-control__count")).toHaveText(
      "42"
    );
    await expect(items.nth(1).locator(".segmented-control__count")).toHaveText(
      "8"
    );

    // ③ 默认选中只数最多的那一类（typeOptions 已按 count 降序）
    await expect(items.nth(0)).toHaveClass(/is-active/);
    await expect(items.nth(0)).toHaveAttribute("aria-selected", "true");

    // ④ emit → 父层写值 → 重取：判据是请求参数，不是视觉
    await items.nth(1).click();
    await expect
      .poll(() => stub.rankingQueries.at(-1)?.get("fund_type_id"))
      .toBe("12");
    await expect(items.nth(1)).toHaveClass(/is-active/);
    await expect(items.nth(0)).not.toHaveClass(/is-active/);
  });
});

/** 页面级滚动：fixedHeader 模式下真正滚动的是 `.app-main .el-scrollbar__wrap` */
async function scrollAppWrap(page: Page, top: number) {
  await page.evaluate(y => {
    const wrap = document.querySelector<HTMLElement>(
      ".app-main .el-scrollbar__wrap"
    );
    if (wrap) {
      wrap.scrollTop = y;
      return;
    }
    window.scrollTo(0, y);
  }, top);
}

/** 表头首行顶边相对滚动容器顶边的偏移：吸顶成功 ≈ 0；跟着滚走会变成负数 */
async function headerOffset(page: Page): Promise<number> {
  return page.evaluate(() => {
    // 用 thead th 而不是 .el-table__header：自建 table 与 el-table 都命中，
    // 反向验证（回退实现）时量到的才是「表头真的滚走了」而不是「选择器找不到」
    const th = document.querySelector<HTMLElement>(".ranking-table thead th");
    const wrap = document.querySelector<HTMLElement>(
      ".app-main .el-scrollbar__wrap"
    );
    if (!th) return Number.NaN;
    const base = wrap ? wrap.getBoundingClientRect().top : 0;
    return th.getBoundingClientRect().top - base;
  });
}

/** 最右数值列左缘相对表格左缘的偏移：用来证明横滚真的滚动了内容 */
async function lastNumLeft(page: Page): Promise<number> {
  return page.evaluate(() => {
    const tds = document.querySelectorAll<HTMLElement>(
      ".ranking-table .el-table__body tr:first-child td.col-num"
    );
    const td = tds[tds.length - 1];
    const root = document.querySelector<HTMLElement>(".ranking-table");
    if (!td || !root) return Number.NaN;
    return td.getBoundingClientRect().left - root.getBoundingClientRect().left;
  });
}

/** 基金列左缘相对表格左缘的偏移：冻结成功时横滚前后不变 */
async function fundLeftOffset(page: Page): Promise<number> {
  return page.evaluate(() => {
    const td = document.querySelector<HTMLElement>(
      ".ranking-table .el-table__body td.col-fund"
    );
    const root = document.querySelector<HTMLElement>(".ranking-table");
    if (!td || !root) return Number.NaN;
    return td.getBoundingClientRect().left - root.getBoundingClientRect().left;
  });
}

/**
 * 表头吸顶 + 横向滚动（#3200）。
 *
 * 旧实现（自建 `<table>` + `.table-scroll{overflow-x:auto}`）的病根：横向 auto 让该
 * 容器成为 sticky 的「最近滚动祖先」，纵向滚动时 thead 直接滚出视口（实测 top=494px）。
 * 这里的判据只依赖几何量，与视觉细节解耦：
 *
 * 1. 滚过表头原位后，表头相对滚动容器顶边的偏移稳定在 0 附近（不随滚动线性增大/变负）；
 * 2. 1366 屏列总宽超容器 → 表格内部横滚可用，且滚中间列时基金列不跟着跑。
 *
 * 反向验证：把 FundRankingTable 改回自建 table（裸 `overflow-x:auto`）→ 判据 1 转红。
 */
test.describe("同类优选表头吸顶与横向滚动（#3200）", () => {
  // 最受约束的主流笔记本：列总宽 ≈1060px，内容区约 1010px → 必然内部横滚
  test.use({ viewport: { width: 1366, height: 768 } });

  // 会话必须逐个 describe 注入（beforeEach 不跨 describe 继承）：漏掉会停在登录页
  test.beforeEach(async ({ context, baseURL }) => {
    await injectSupabaseSession(context, baseURL!);
  });

  test("纵向滚动表头吸在容器顶部；横向滚动基金列恒冻", async ({ page }) => {
    test.setTimeout(240_000);
    // Vue 会吞掉子组件 render 错误（DOM 冻结在末次成功渲染、只留 warn），
    // 所以除了断言内容，还要单独收 pageerror
    const pageErrors: string[] = [];
    page.on("pageerror", err => pageErrors.push(err.message));

    await stubApi(page, manyRows(40));
    await openPage(page);

    // 桩生效：40 行都渲染出来了（不是空表 → 后面「表头在不在」的判据才有意义）
    await expect(table(page).locator("tbody tr")).toHaveCount(40);

    // ① 纵向：滚过表头原位后应吸住，且不同滚动位置下表头位置一致
    const scrollable = await page.evaluate(() => {
      const wrap = document.querySelector<HTMLElement>(
        ".app-main .el-scrollbar__wrap"
      );
      return !!wrap && wrap.scrollHeight > wrap.clientHeight + 200;
    });
    expect(scrollable).toBe(true);

    await scrollAppWrap(page, 600);
    await expect.poll(() => headerOffset(page)).toBeLessThanOrEqual(2);
    const at600 = await headerOffset(page);

    await scrollAppWrap(page, 900);
    await expect.poll(() => headerOffset(page)).toBeLessThanOrEqual(2);
    const at900 = await headerOffset(page);

    // 「吸住」= 滚动位置变了 300px、表头位置却没变；跟着滚走会差出这 300
    expect(Math.abs(at600 - at900)).toBeLessThanOrEqual(2);
    expect(at900).toBeGreaterThanOrEqual(-1);

    // ② 横向：横滚必须发生在表格内部，页面级横向滚动条仍然禁止（#1341）
    const bodyWrap = page.locator(
      ".ranking-table .el-table__body-wrapper .el-scrollbar__wrap"
    );
    expect(
      await bodyWrap.evaluate(el => el.scrollWidth > el.clientWidth + 20)
    ).toBe(true);
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth > window.innerWidth + 1
      )
    ).toBe(false);

    // 1366 屏的溢出量就是「最后一列差多少」（列总宽 1060 vs 内容区约 1010）：
    // 判据是「有溢出、滚得动」，不是某个固定像素数
    const overflow = await bodyWrap.evaluate(
      el => el.scrollWidth - el.clientWidth
    );
    expect(overflow).toBeGreaterThan(20);

    const beforeFund = await fundLeftOffset(page);
    const beforeLast = await lastNumLeft(page);
    await bodyWrap.evaluate(el => {
      el.scrollLeft = el.scrollWidth;
    });
    await expect
      .poll(() => bodyWrap.evaluate(el => el.scrollLeft))
      .toBeGreaterThan(10);
    const afterFund = await fundLeftOffset(page);
    const afterLast = await lastNumLeft(page);

    // 内容确实滚了：最右一列左移了与 scrollLeft 同量级的距离
    expect(beforeLast - afterLast).toBeGreaterThan(10);
    // 冻结列：横滚前后左缘不变（不冻结会被推走同样距离）
    expect(Math.abs(afterFund - beforeFund)).toBeLessThanOrEqual(2);

    expect(pageErrors).toEqual([]);
  });
});
