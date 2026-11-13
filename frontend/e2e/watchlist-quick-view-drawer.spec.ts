import { expect, test } from "@playwright/test";

import { injectSupabaseSession } from "./support/session";

/**
 * #980 拆分回归网：**自选行「速览」抽屉拆成 7 个区块组件后，行为不变**。
 *
 * 拆分把一个 651 行的 `WatchlistQuickViewDrawer.vue` 拆成
 * `quickView/{Head,QuoteSection,HoldingSection,InfoSection,AdvisorSection,
 * AdjustSection,NotesSection}.vue` + `quickViewModel.ts`（纯函数）+
 * `useQuickViewDetail.ts`（按需拉取）。等价性脚本已证文案 / 类名 / 样式声明 0 缺失，
 * 但脚本证不到「**跨层的 props / emit 还通不通**」——这正是拆分的真实风险点：
 *
 * 1. `edit-notes` 是**三段跳**：`QuickViewNotesSection` → `WatchlistQuickViewDrawer`
 *    → `WatchlistDialogs` → `openNotesEditor`。任一环漏 emit，点「编辑」就是静默无反应
 *    （不像报错那样显眼，只能靠真点一次才知道）；
 * 2. 「成分与调仓」的按需拉取触发条件在 `useQuickViewDetail` 的 watch 源里
 *    （打开 / 换标的 / 品类是投顾组合，缺一不拉）——单测 mock 掉 watch 就永远绿，
 *    只有真浏览器能证「抽屉一开，两个投顾接口真的发出去了」；
 * 3. scoped 样式边界：`.wqv-*` 骨架抽进 partial 后由各区块各自 `@use`，
 *    若某个区块漏 `@use`，DOM 和文案都还在、只有样式没了——脚本查不出来，
 *    得靠真渲染后的布局（这里用「区块标题可见 + 单元格内容可见」兜一层）。
 *
 * 防假绿的三条刻意设计：
 * 1. **先坐实行真的渲染出来了**（否则「抽屉里没有某区块」只是因为没数据）；
 * 2. **投顾场景先证「请求真发出」**，再证渲染——顺序反了，「两个接口没打」
 *    与「打了但没渲染」会长得一模一样；
 * 3. **品类分支各测一行**（index 无「持有」/ bond「查看详情」禁用），
 *    而不是只测数据最全的基金行——只测全量行会放过分品类 `v-if` 的接线错误。
 *
 * 反向验证（写完必须做，否则不知道自己写的是不是恒真用例）：
 * 把 `QuickViewNotesSection` 的 `@click="emit(...)"` 删掉，用例三「编辑」那段必须报红；
 * 把 `useQuickViewDetail` 的 watch 里 `!isPf` 提前 return，用例二必须在
 * 「投顾接口被请求」那一行报红。
 */

test.describe.configure({ timeout: 420_000 });

/** 基金行：字段最全，走「全部区块 + 详情可跳」路径 */
const FUND_ROW = {
  id: 1,
  symbol: "023887",
  name: "某某混合A",
  display_name: "某某混合A",
  asset_type: "fund",
  type_label: "混合型",
  venue: "OTC",
  market: "CN",
  status: "HOLDING",
  current_price: 0.95,
  change_pct: 1.05,
  holding_quantity: 12000,
  holding_cost_price: 0.83,
  position_market_value: 960.5,
  holding_pnl: 144,
  created_at: "2026-09-01T00:00:00Z",
  group_names: ["核心仓"],
  tag_ids: [7],
  notes: "每月 8 日定投，跌破 0.8 加倍。",
  is_pinned: false,
  favorite: false,
  tags: []
};

/** 投顾组合行：走「隐藏代码 + 投顾信息 + 成分与调仓按需拉取」路径 */
const PORTFOLIO_ROW = {
  id: 2,
  symbol: "PF0001",
  name: "稳健增长组合",
  display_name: "稳健增长组合",
  asset_type: "portfolio",
  type_label: "投顾组合",
  advisor_platform: "且慢",
  advisor_host: "主理人A",
  advisor_strategy_type: "股债平衡",
  advisor_allocation_label: "稳健增值",
  advisor_product_type: "基金组合",
  advisor_nav: 1.2345,
  advisor_nav_date: "2026-09-11",
  advisor_strategy_summary: "以股债 3:7 为中枢，季度再平衡。",
  advisor_source_url: "https://example.com/portfolio/PF0001",
  created_at: "2026-08-01T00:00:00Z",
  group_names: [],
  tag_ids: [],
  notes: "",
  is_pinned: false,
  favorite: false,
  tags: []
};

/** 指数行：不可持有 ⇒ 不应出现「持有」区；详情页一期已开放 */
const INDEX_ROW = {
  id: 3,
  symbol: "000300",
  name: "沪深300",
  display_name: "沪深300",
  asset_type: "index",
  type_label: "宽基指数",
  current_price: 4010.25,
  change_pct: -0.62,
  holding_quantity: 0,
  holding_cost_price: null,
  position_market_value: null,
  holding_pnl: null,
  created_at: "2026-07-01T00:00:00Z",
  group_names: [],
  tag_ids: [],
  notes: "",
  is_pinned: false,
  favorite: false,
  tags: []
};

/** 无行情行：既无最新价也不是组合 ⇒ 抽屉不得有锚点（空锚点会白占 32px 节奏） */
const NO_QUOTE_ROW = {
  id: 5,
  symbol: "999999",
  name: "未取到行情标的",
  display_name: "未取到行情标的",
  asset_type: "bond",
  type_label: "可转债",
  created_at: "2026-06-01T00:00:00Z",
  group_names: [],
  tag_ids: [],
  notes: "",
  is_pinned: false,
  favorite: false,
  tags: []
};

/** 可转债行：一期未开放详情页 ⇒ 「查看详情」必须禁用并说明原因，不静默失败 */
const BOND_ROW = {
  id: 4,
  symbol: "113050",
  name: "某转债",
  display_name: "某转债",
  asset_type: "bond",
  type_label: "可转债",
  current_price: 118.42,
  change_pct: 0.31,
  created_at: "2026-06-01T00:00:00Z",
  group_names: [],
  tag_ids: [],
  notes: "",
  is_pinned: false,
  favorite: false,
  tags: []
};

/** 投顾明细接口（成分 / 调仓）：计数 + 供数，缺一不可 */
const ADVISOR_HOLDINGS_RE = /\/api\/funds\/advisors\/[^/]+\/holdings\//;
const ADVISOR_ADJUSTS_RE = /\/api\/funds\/advisors\/[^/]+\/adjusts\//;

const ADVISOR_HOLDINGS = {
  code: "PF0001",
  name: "稳健增长组合",
  platform: "qieman",
  as_of_date: "2026-09-11",
  holdings: [
    {
      fund_code: "000001",
      fund_name: "华夏成长混合",
      pre_ratio: 20,
      after_ratio: 24,
      op_name: "加仓",
      in_local_db: true
    },
    {
      fund_code: "000002",
      fund_name: "某债基A",
      pre_ratio: 30,
      after_ratio: 24,
      op_name: "减仓",
      in_local_db: true
    },
    {
      fund_code: "000003",
      fund_name: "未收录基金",
      pre_ratio: 10,
      after_ratio: 12,
      op_name: "加仓",
      in_local_db: false
    }
  ]
};

const ADVISOR_ADJUSTS = {
  code: "PF0001",
  name: "稳健增长组合",
  platform: "qieman",
  adjusts: [
    {
      adjust_date: "2026-09-11",
      reason: null,
      source: "qieman",
      items: [
        {
          fund_code: "000001",
          fund_name: "华夏成长混合",
          op_name: "加仓",
          pre_ratio: 20,
          after_ratio: 24
        },
        {
          fund_code: "000002",
          fund_name: "某债基A",
          op_name: "减仓",
          pre_ratio: 30,
          after_ratio: 24
        }
      ]
    }
  ]
};

/** 列表行按可见文本定位（页面里只有一张主表；冻结列会多渲染一份 DOM，故用 filter） */
function rowOf(page: import("@playwright/test").Page, text: string) {
  return page.locator(".el-table__row").filter({ hasText: text }).first();
}

/**
 * 抽屉容器：用**外壳契约** `[data-testid="product-drawer"]` 定位。
 *
 * 原实现按标题文本「速览」收窄——泛化标题已按设计删除（产品名就是标题），
 * 而且读文案当定位器一改文案就红。页面里另有 SettingsDrawer 等，
 * data-testid 只加在三处产品抽屉的外壳上，天然唯一。
 */
function drawerOf(page: import("@playwright/test").Page) {
  return page.locator('[data-testid="product-drawer"]');
}

/**
 * 打开某一行的速览抽屉，并坐实「抽屉真的开了」再交回控制权。
 *
 * `text` 传**列表里可见**的文本：组合 / 经理类行不展示代码（组合分层信息占位），
 * 传 symbol 会找不到行——那不是缺陷，是设计（抽屉头部同样隐藏代码）。
 */
async function openQuickView(
  page: import("@playwright/test").Page,
  text: string
) {
  const row = rowOf(page, text);
  await expect(row).toBeVisible({ timeout: 120_000 });
  await row.getByText(text).first().click();
  const drawer = drawerOf(page);
  await expect(drawer).toBeVisible({ timeout: 30_000 });
  // 外壳头部渲染完成 = 抽屉内容就绪（产品名即标题）
  await expect(drawer.locator(".pd-name")).toBeVisible({ timeout: 30_000 });
  return drawer;
}

/** 装桩：会话 + 后端接口。rows 由各用例自己给 */
async function stubBackend(
  context: import("@playwright/test").BrowserContext,
  page: import("@playwright/test").Page,
  baseURL: string,
  rows: Record<string, unknown>[],
  onAdvisor?: { holdings?: number; adjusts?: number }
) {
  await injectSupabaseSession(context, baseURL);

  await page.route(
    url => new URL(url).pathname.startsWith("/api/"),
    async route => {
      const url = new URL(route.request().url());
      const p = url.pathname;

      if (p === "/api/watchlist/items/") {
        return route.fulfill({
          json: {
            data: rows,
            total: rows.length,
            page: 1,
            per_page: 200,
            message: ""
          }
        });
      }
      if (p === "/api/watchlist/tags/") {
        return route.fulfill({
          json: {
            data: [{ id: 7, name: "定投", color: null }],
            total: 1,
            message: ""
          }
        });
      }
      if (ADVISOR_HOLDINGS_RE.test(p)) {
        if (onAdvisor) onAdvisor.holdings += 1;
        return route.fulfill({ json: { data: ADVISOR_HOLDINGS, message: "" } });
      }
      if (ADVISOR_ADJUSTS_RE.test(p)) {
        if (onAdvisor) onAdvisor.adjusts += 1;
        return route.fulfill({ json: { data: ADVISOR_ADJUSTS, message: "" } });
      }
      return route.fulfill({ json: { data: [], total: 0, message: "" } });
    }
  );
}

/** 进自选页并坐实首屏（前提一：数据真的渲染出来了） */
async function gotoWatchlist(page: import("@playwright/test").Page) {
  await page.goto("/#/watchlist", { waitUntil: "commit" });
  await expect(page.locator(".sidebar-container")).toBeVisible({
    timeout: 150_000
  });
}

test.describe("自选行速览抽屉（#980 拆分回归）", () => {
  test("基金行：锚点与四个区块文案齐全，备注「编辑」跨层生效，查看详情可跳", async ({
    context,
    page,
    baseURL
  }) => {
    const advisor = { holdings: 0, adjusts: 0 };
    await stubBackend(context, page, baseURL!, [FUND_ROW], advisor);
    await gotoWatchlist(page);
    await expect(page.getByText("023887").first()).toBeVisible({
      timeout: 120_000
    });

    const drawer = await openQuickView(page, "023887");

    // ── 外壳契约：抽屉必须挂到 body（#3101）──
    // 留在页面容器里时，点「查看详情」会与路由 fade-transform 抢帧：父级过渡的
    // transform 改写 `position: fixed` 遮罩的包含块，抽屉与遮罩跟着整页位移淡出。
    // 这条断言守的是 `append-to-body` 这一个属性，删掉它只有真机采样才看得出来。
    expect(
      await drawer.evaluate(el => el.closest(".main-content") === null)
    ).toBe(true);

    // ── 头部（外壳渲染）：名称 / 代码（带 # 前缀）/ 品类胶囊 ──
    await expect(drawer.locator(".pd-name")).toHaveText("某某混合A");
    await expect(drawer.locator(".pd-meta__code")).toHaveText("#023887");
    await expect(drawer.locator(".pd-type")).toHaveText("混合型");

    // ── 锚点：原「行情」区块并入（最新价 4 位精度 + 涨跌幅副行）──
    //    同一个问题不答两遍：锚点必须唯一，且「行情」标题不再作为区块出现
    const anchor = drawer.locator('[data-testid="num-anchor"]');
    await expect(anchor).toHaveCount(1);
    await expect(anchor).toContainText("0.95");
    await expect(anchor).toContainText("1.05");
    await expect(drawer.getByText("行情", { exact: true })).toHaveCount(0);

    // ── 持有：数量 / 市值 / 成本价 / 收益（fund 可持有 ⇒ 必须出现）──
    //    数量带千分位（与持仓明细抽屉同一写法）：份额会被逐位核对，位数要一眼可数
    await expect(drawer.locator(".pd-sec__title").first()).toHaveText("持有");
    await expect(
      drawer.locator(".wqv-cell").filter({ hasText: "持有数量" })
    ).toContainText("12,000");
    await expect(
      drawer.locator(".wqv-cell").filter({ hasText: "持仓市值" })
    ).toContainText("960");
    await expect(
      drawer.locator(".wqv-cell").filter({ hasText: "成本价" })
    ).toContainText("0.83");
    await expect(
      drawer.locator(".wqv-cell").filter({ hasText: "持仓收益" })
    ).toContainText("144");

    // ── 「信息」区块已删除：添加自选日 / 分组 / 标签降为备注区末行 13px 元信息 ──
    //    标签与分组是管理元数据，不是决策信息（设计 §6.2），但文案仍须能读到
    await expect(drawer.getByText("信息", { exact: true })).toHaveCount(0);
    const notesMeta = drawer.locator(".wqv-note__meta");
    await expect(notesMeta).toContainText("已添加 2026-09-01");
    await expect(notesMeta).toContainText("所属分组 核心仓");
    await expect(notesMeta).toContainText("标签 定投");

    // ── 备注：有内容则显示全文 ──
    await expect(drawer.getByText("每月 8 日定投")).toBeVisible();

    // ── 跨层 emit：NotesSection → Drawer → Dialogs → openNotesEditor ──
    // 拆分成「孙组件」后最容易断的一环：断了不报错，只是点了没反应。
    await drawer.getByRole("button", { name: "编辑" }).click();
    await expect(
      page.locator(".el-dialog").filter({ hasText: "编辑备注" })
    ).toBeVisible({ timeout: 30_000 });
    await page.keyboard.press("Escape");
    await expect(
      page.locator(".el-dialog").filter({ hasText: "编辑备注" })
    ).toBeHidden({ timeout: 30_000 });

    // ── 详情页入口：唯一出口在 footer 内；fund 已开放 ⇒ 可点且真跳 ──
    const footer = drawer.locator('[data-testid="drawer-footer"]');
    const detailBtn = footer.getByRole("button", { name: "查看详情" });
    await expect(detailBtn).toHaveCount(1);
    await expect(detailBtn).toBeEnabled();
    // 全抽屉只有这一个「查看详情」（header / 内容区都不再放）
    await expect(drawer.getByRole("button", { name: "查看详情" })).toHaveCount(
      1
    );
    await expect(footer).toContainText("查看完整业绩、持仓与历史记录");
    await detailBtn.click();
    await page.waitForURL(/#\/fund\/023887/, { timeout: 30_000 });
    await expect(drawerOf(page)).toBeHidden({ timeout: 30_000 });
  });

  test("投顾组合行：隐藏代码 + 投顾信息 + 成分与调仓按需拉取", async ({
    context,
    page,
    baseURL
  }) => {
    const advisor = { holdings: 0, adjusts: 0 };
    await stubBackend(context, page, baseURL!, [PORTFOLIO_ROW], advisor);
    await gotoWatchlist(page);
    // 前提：组合行真的渲染出来（组合类行不展示代码，故按名称坐实）
    await expect(page.getByText("稳健增长组合").first()).toBeVisible({
      timeout: 120_000
    });

    const drawer = await openQuickView(page, "稳健增长组合");

    // ── 头部：组合类不展示代码，识别信息行给「品类 · 平台 · 主理人 · 策略」──
    await expect(drawer.locator(".pd-name")).toHaveText("稳健增长组合");
    await expect(drawer.locator(".pd-meta__code")).toHaveCount(0);
    await expect(drawer.locator(".pd-meta")).toContainText("投顾组合");
    await expect(drawer.locator(".pd-meta")).toContainText("且慢");
    await expect(drawer.locator(".pd-meta")).toContainText("主理人A");
    await expect(drawer.locator(".pd-meta")).toContainText("股债平衡");
    await expect(drawer.locator(".pd-meta")).not.toContainText("PF0001");
    // 组合不可持有 ⇒ 无「持有」区
    await expect(drawer.getByText("持有", { exact: true })).toHaveCount(0);

    // ── 锚点：组合净值（原「投顾信息」里的净值行并入锚点，不再答两遍）──
    const anchor = drawer.locator('[data-testid="num-anchor"]');
    await expect(anchor).toHaveCount(1);
    await expect(anchor).toContainText("1.2345");
    await expect(anchor).toContainText("截至 2026-09-11");

    // ── 投顾信息：配置目标 / 产品类型 / 策略简介 / 官方页面 ──
    await expect(drawer.getByText("投顾信息")).toBeVisible();
    await expect(
      drawer.locator(".wqv-row").filter({ hasText: "配置目标" })
    ).toContainText("稳健增值");
    await expect(
      drawer.locator(".wqv-row").filter({ hasText: "产品类型" })
    ).toContainText("基金组合");
    await expect(
      drawer.locator(".wqv-row").filter({ hasText: "组合净值" })
    ).toHaveCount(0);
    await expect(drawer.getByText("以股债 3:7 为中枢")).toBeVisible();
    const link = drawer.locator(".wqv-link");
    await expect(link).toHaveAttribute(
      "href",
      "https://example.com/portfolio/PF0001"
    );

    // ── 成分与调仓：先证「按需拉取真的打了两个接口」，再证渲染 ──
    // 顺序不能反：反了，「没打请求」和「打了没渲染」长得一样，用例恒真。
    await expect
      .poll(() => advisor.holdings, { timeout: 30_000 })
      .toBeGreaterThan(0);
    await expect
      .poll(() => advisor.adjusts, { timeout: 30_000 })
      .toBeGreaterThan(0);

    await expect(drawer.getByText("成分与调仓")).toBeVisible();
    await expect(
      drawer.locator(".wqv-row").filter({ hasText: "成分基金" })
    ).toContainText("3 只");
    await expect(drawer.getByText("1 只未收录本地")).toBeVisible();

    // 调仓日分组：日期 + 只数 + 操作名 + 占比迁移
    const adjust = drawer.locator(".wqv-adjust").first();
    await expect(adjust).toContainText("2026-09-11");
    await expect(adjust).toContainText("2 只调整");
    await expect(adjust).toContainText("华夏成长混合");
    await expect(adjust).toContainText("20.00% → 24.00%");
    // 加/减仓走涨跌语义类（不是行情色，别混）
    await expect(adjust.locator(".wqv-op--add")).toHaveCount(1);
    await expect(adjust.locator(".wqv-op--cut")).toHaveCount(1);
  });

  test("品类分支：指数无「持有」区、无可转债出口、无行情时不出锚点", async ({
    context,
    page,
    baseURL
  }) => {
    await stubBackend(context, page, baseURL!, [
      INDEX_ROW,
      BOND_ROW,
      NO_QUOTE_ROW
    ]);
    await gotoWatchlist(page);
    await expect(page.getByText("000300").first()).toBeVisible({
      timeout: 120_000
    });
    await expect(page.getByText("113050").first()).toBeVisible({
      timeout: 120_000
    });

    // ── 指数：不可持有 ⇒ 不出现「持有」区 ──
    const idxDrawer = await openQuickView(page, "000300");
    // 「行情」「信息」两个区块已删除：行情并进锚点，信息降为备注末行元信息。
    // 指数行仍有最新价，锚点必须还在——否则并区后就凭空丢了主数值。
    await expect(idxDrawer.locator('[data-testid="num-anchor"]')).toHaveCount(
      1
    );
    await expect(idxDrawer.locator('[data-testid="num-anchor"]')).toContainText(
      "4,010.25"
    );
    await expect(idxDrawer.getByText("行情", { exact: true })).toHaveCount(0);
    await expect(idxDrawer.getByText("持有", { exact: true })).toHaveCount(0);
    await expect(idxDrawer.getByText("信息", { exact: true })).toHaveCount(0);
    // 指数已开放详情页 ⇒ footer 里有且只有一个出口
    await expect(
      idxDrawer
        .locator('[data-testid="drawer-footer"]')
        .getByRole("button", { name: "查看详情" })
    ).toHaveCount(1);

    await page.keyboard.press("Escape");
    await expect(drawerOf(page)).toBeHidden({ timeout: 30_000 });

    // ── 可转债：品类无详情页 ⇒ footer **不渲染**按钮，只留原因文案 ──
    //    （灰按钮会制造「即将可用」的假期待，且读屏不解释原因）
    const bondDrawer = await openQuickView(page, "113050");
    await expect(
      bondDrawer.locator('[data-testid="drawer-footer"]').getByRole("button")
    ).toHaveCount(0);
    await expect(bondDrawer).toContainText("该品类暂无详情页");
    // 被删的泛化标题不再出现：产品名就是标题
    await expect(bondDrawer.getByText("速览", { exact: true })).toHaveCount(0);

    await page.keyboard.press("Escape");
    await expect(drawerOf(page)).toBeHidden({ timeout: 30_000 });

    // ── 无行情：既非组合也没有最新价 ⇒ 锚点整块不渲染（不是渲染个空块）──
    const noQuoteDrawer = await openQuickView(page, "999999");
    await expect(
      noQuoteDrawer.locator('[data-testid="num-anchor"]')
    ).toHaveCount(0);
    // 抽屉本身仍在（骨架不依赖锚点）
    await expect(noQuoteDrawer.locator(".pd-name")).toBeVisible();
  });
});
