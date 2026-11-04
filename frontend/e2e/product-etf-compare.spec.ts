import { expect, test, type Page } from "@playwright/test";

import { injectSupabaseSession } from "./support/session";

/**
 * #980 拆分回归网：**关联 ETF 对比表拆成两个子组件后，行为（尤其是降级）不变**。
 *
 * 拆分把 `ProductEtfCompare.vue`（610 行）拆成
 * `etfCompare/{etfCompareModel.ts, useScrollFade.ts, EtfComparePicks.vue,
 * EtfCompareTable.vue}`。等价性脚本证得了文案 / 类名 / 样式 0 缺失，但证不到
 * 下面三件只有真浏览器能证的事：
 *
 * 1. **降级契约**。这张表的每一列都来自第三方（东财 F10 / 同花顺 / 新浪 / 腾讯兜底），
 *    任一字段失败都得落到「—」而不是 `NaN` / `null` / `undefined`。九个格式化函数
 *    搬进模型层时最容易出的错正是「边界条件抄漏一条」——单测覆盖了函数，这里覆盖
 *    「抄漏之后页面上真会出现 `null`」这条最后一公里。
 * 2. **两个渲染门禁**。`recommend_rank` 全 null 时**优选小卡整块不渲染**（不留空壳
 *    标题），指数四窗口全 null 时**基准行不渲染**。这两条都是「少了才对」的断言，
 *    写反了（断言存在）会恒真，所以每条都配一条正向前提（表必须在、行必须在）。
 * 3. **横滚渐隐搬进了子组件**。`scroller` 这个 DOM ref 随表格一起下移到
 *    `EtfCompareTable`，父层不再持有它；本用例用「窄视口下渐隐出现、滚到尽头后消失」
 *    钉住 `useScrollFade` 在子组件里仍然量得到元素。
 *
 * 防假绿的三条刻意设计：
 * 1. **先坐实区块真的挂载了**（标题「关联 ETF 对比」可见 + 对比表有行），否则
 *    「优选小卡不出现」在接口失败 / 无关联时也是真的，用例恒真；
 * 2. **断言格式化结果而不是元素存在**——「—」「1.23亿」「管理 0.50% / 托管 0.10%」
 *    才是模型层真的被搬对了；
 * 3. **渐隐用例用窄视口**（表 `min-width: 760px`），宽视口下永远不可滚，断言
 *    「渐隐出现」反而恒假、断言「不出现」恒真。
 *
 * 反向验证（写完必须做，否则不知道自己写的是不是恒真用例）：
 * 把 `EtfComparePicks` 的 `v-if="hasRecommend"` 摘掉，用例二必须在
 * 「优选 ETF 整块不渲染」那行报红；把 `indexBaselineOf` 改成恒返回 `w`，
 * 用例二必须在「基准行不渲染」那行报红。
 */

test.describe.configure({ timeout: 300_000 });

const INDEX_SYMBOL = "000300";

/** 三条对比行：名次刻意乱序给出（2 / 1 / 不参评），验证前端按名次升序重排 */
const ROWS = [
  {
    code: "510300",
    name: "沪深300ETF",
    nav: 4.1234,
    nav_date: "2026-10-24",
    nav_change_pct: 0.31,
    change_pct: 0.42,
    amount: 1.234e8,
    returns: { m1: 1.11, m3: 2.22, m6: 3.33, y1: 12.34 },
    tracking_diff_y1: -0.18,
    scale_yi: 12.345,
    mgmt_fee_pct: 0.5,
    custody_fee_pct: 0.1,
    recommend_rank: 2
  },
  {
    code: "159919",
    name: "300ETF",
    nav: 1.2345,
    nav_date: "2026-10-24",
    nav_change_pct: -0.12,
    change_pct: -0.24,
    amount: 5.6e7,
    returns: { m1: -1.11, m3: -2.22, m6: -3.33, y1: 11.11 },
    tracking_diff_y1: -0.05,
    scale_yi: 3.5,
    mgmt_fee_pct: 0.15,
    custody_fee_pct: null,
    recommend_rank: 1
  },
  {
    code: "510310",
    name: "HS300ETF",
    nav: null,
    nav_date: null,
    nav_change_pct: null,
    change_pct: null,
    amount: null,
    returns: { m1: null, m3: null, m6: null, y1: null },
    tracking_diff_y1: null,
    scale_yi: null,
    mgmt_fee_pct: null,
    custody_fee_pct: null,
    recommend_rank: null
  }
];

const COMPARE_OK = {
  index_code: INDEX_SYMBOL,
  as_of: "2026-10-24",
  index_returns: { m1: null, m3: null, m6: null, y1: 12.52 },
  rows: ROWS
};

/** 全降级：三行都无行情、`recommend_rank` 全 null、指数四窗口全 null */
const COMPARE_DEGRADED = {
  index_code: INDEX_SYMBOL,
  as_of: null,
  index_returns: { m1: null, m3: null, m6: null, y1: null },
  rows: ROWS.map(r => ({
    ...r,
    nav: null,
    change_pct: null,
    amount: null,
    returns: { m1: null, m3: null, m6: null, y1: null },
    tracking_diff_y1: null,
    scale_yi: null,
    mgmt_fee_pct: null,
    custody_fee_pct: null,
    recommend_rank: null
  }))
};

/** 关联标的：带一条 `peer_role === "etf"` 才会挂载对比表 */
const RELATED = {
  groups: ["同标的 ETF"],
  links: [
    {
      code: "510300",
      name: "沪深300ETF",
      link_type: "index_etf",
      label: "同标的 ETF",
      peer_role: "etf"
    }
  ]
};

function compareSection(page: Page) {
  return page.locator(".etf-cmp");
}

async function stubBackend(
  context: Parameters<typeof injectSupabaseSession>[0],
  page: Page,
  baseURL: string,
  opts: { compare?: Record<string, unknown> | "fail" } = {}
) {
  await injectSupabaseSession(context, baseURL);

  await page.route(
    url => new URL(url).pathname.startsWith("/api/"),
    async route => {
      const p = new URL(route.request().url()).pathname;

      if (p === "/api/products/resolve/") {
        return route.fulfill({
          json: {
            data: {
              symbol: INDEX_SYMBOL,
              asset_type: "index",
              market: "CN",
              venue: "EXCHANGE",
              display_name: "沪深300",
              in_watchlist: false,
              has_position: false,
              source: "catalog"
            },
            message: ""
          }
        });
      }
      if (p === "/api/products/related-symbols/") {
        return route.fulfill({ json: { data: RELATED, message: "" } });
      }
      if (p === "/api/products/index-etf-compare/") {
        if (opts.compare === "fail") {
          return route.fulfill({ status: 500, json: { message: "boom" } });
        }
        return route.fulfill({
          json: { data: opts.compare ?? COMPARE_OK, message: "" }
        });
      }
      return route.fulfill({ json: { data: [], total: 0, message: "" } });
    }
  );
}

async function gotoIndexDetail(page: Page) {
  await page.goto(`/#/index/${INDEX_SYMBOL}`, { waitUntil: "commit" });
  await expect(page.locator(".sidebar-container")).toBeVisible({
    timeout: 150_000
  });
  await expect(
    compareSection(page).getByText("关联 ETF 对比", { exact: true })
  ).toBeVisible({ timeout: 60_000 });
}

test.describe("关联 ETF 对比表（#980 拆分回归）", () => {
  test("正常态：优选小卡按名次升序、12 列格式化、基准行与脚注齐全", async ({
    context,
    page,
    baseURL
  }) => {
    await stubBackend(context, page, baseURL, { compare: COMPARE_OK });
    await gotoIndexDetail(page);
    const section = compareSection(page);

    // ── 前提：对比表真的渲染出来了 ──
    await expect(section.locator(".etf-cmp__table")).toBeVisible();
    await expect(section.locator("tbody tr")).toHaveCount(3);

    // ── 优选小卡：后端给的名次是 2 / 1 / 未参评，前端按名次升序画前两只 ──
    await expect(section.getByText("优选 ETF", { exact: true })).toBeVisible();
    const picks = section.locator(".etf-cmp__pick");
    await expect(picks).toHaveCount(2);
    await expect(picks.nth(0)).toContainText("优选 · 第 1");
    await expect(picks.nth(0)).toContainText("300ETF");
    await expect(picks.nth(0)).toHaveClass(/etf-cmp__pick--first/);
    await expect(picks.nth(1)).toContainText("第 2");
    await expect(picks.nth(1)).not.toHaveClass(/etf-cmp__pick--first/);

    // ── 九列格式化：每行都验一遍模型层搬过去没有抄漏 ──
    const firstRow = section.locator("tbody tr").first();
    await expect(firstRow).toContainText("510300");
    await expect(firstRow).toContainText("4.1234"); // nav: 4 位小数
    await expect(firstRow).toContainText("+0.42%"); // change_pct
    await expect(firstRow).toContainText("1.23亿"); // amount: 元 → 亿
    await expect(firstRow).toContainText("12.35亿"); // scale_yi
    await expect(firstRow).toContainText("管理 0.50% / 托管 0.10%"); // 双费率
    await expect(firstRow).toContainText("+12.34%"); // returns.y1
    await expect(firstRow).toContainText("-0.18%"); // tracking_diff_y1

    // 第二行只缺托管费 → 只显管理费（不是整格「—」）
    const secondRow = section.locator("tbody tr").nth(1);
    await expect(secondRow).toContainText("管理 0.15%");
    await expect(secondRow).not.toContainText("托管");

    // 涨跌语义类：涨红跌绿由令牌给，这里只验正负分到了正确的类
    await expect(firstRow.locator(".etf-cmp__num--rise")).not.toHaveCount(0);
    await expect(secondRow.locator(".etf-cmp__num--fall")).not.toHaveCount(0);

    // ── 指数基准行：四窗口只有 y1 有值 ⇒ 整行仍画，且落在同一列 ──
    const baseline = section.locator("tfoot tr");
    await expect(baseline).toHaveCount(1);
    await expect(baseline).toContainText("指数");
    await expect(baseline).toContainText("+12.52%");

    // ── 脚注：净值口径 + 行情来源 ──
    await expect(
      section.getByText(
        "净值截至 2026-10-24（T-1 口径） · 当日行情来自新浪财经"
      )
    ).toBeVisible();
  });

  test("全降级：优选小卡与基准行整块不渲染，各格落「—」", async ({
    context,
    page,
    baseURL
  }) => {
    await stubBackend(context, page, baseURL, { compare: COMPARE_DEGRADED });
    await gotoIndexDetail(page);
    const section = compareSection(page);

    // ── 前提：表还在（否则「小卡不出现」只是因为整块没渲染，用例恒真）──
    await expect(section.locator(".etf-cmp__table")).toBeVisible();
    await expect(section.locator("tbody tr")).toHaveCount(3);

    // ── 门禁一：recommend_rank 全 null ⇒ 优选小卡整块消失，不留空壳标题 ──
    await expect(section.getByText("优选 ETF", { exact: true })).toHaveCount(0);
    await expect(section.locator(".etf-cmp__pick")).toHaveCount(0);

    // ── 门禁二：指数四窗口全 null ⇒ 基准行不画（画一行「—」会被读成收益为 0）──
    await expect(section.locator("tfoot tr")).toHaveCount(0);

    // ── 九列全部落「—」，且不出现 null / NaN / undefined ──
    const bodyText = await section.locator(".etf-cmp__table").innerText();
    expect(bodyText).not.toMatch(/null|NaN|undefined/);
    const firstRow = section.locator("tbody tr").first();
    for (const _ of [0, 1, 2, 3, 4, 5, 6]) {
      // 每行的行情列（净值 / 涨幅 / 成交额 / 规模 / 费率 / 四窗口 / 跟踪差）
      await expect(firstRow).toContainText("—");
    }
    // 代码与名称不是行情，仍应可见（表壳 + 名称/跳转仍有价值）
    await expect(firstRow).toContainText("510300");
    await expect(firstRow).toContainText("沪深300ETF");

    // ── 缺 as_of 时脚注只说来源，不留空分隔符 ──
    await expect(section.getByText("当日行情来自新浪财经")).toBeVisible();
  });

  test("接口失败：整块收敛成「—」，不阻塞详情页其余内容", async ({
    context,
    page,
    baseURL
  }) => {
    await stubBackend(context, page, baseURL, { compare: "fail" });
    await gotoIndexDetail(page);
    const section = compareSection(page);

    await expect(section.locator(".etf-cmp__hint")).toHaveText("—");
    await expect(section.locator(".etf-cmp__table")).toHaveCount(0);
    await expect(section.getByText("优选 ETF", { exact: true })).toHaveCount(0);
  });
});

test.describe("横滚右缘渐隐（#980：随表格下移到 EtfCompareTable）", () => {
  /** 表 `min-width: 760px`，窄于此才真的可滚 */
  test.use({ viewport: { width: 900, height: 800 } });

  test("窄视口出现渐隐，滚到尽头后消失", async ({ context, page, baseURL }) => {
    await stubBackend(context, page, baseURL, { compare: COMPARE_OK });
    await gotoIndexDetail(page);
    const section = compareSection(page);

    const scroller = section.locator(".etf-cmp__scroll");
    const fade = section.locator(".etf-cmp__fade");
    await expect(scroller).toBeVisible();

    // 前提：容器真的可滚（`scrollWidth > clientWidth`），否则渐隐本就不该出现
    await expect
      .poll(() => scroller.evaluate(el => el.scrollWidth - el.clientWidth > 2))
      .toBe(true);

    await expect(fade).toBeVisible();

    // 滚到尽头 → 渐隐消失（右边没有内容了还留着等于撒谎）
    await scroller.evaluate(el => {
      el.scrollLeft = el.scrollWidth;
    });
    await expect
      .poll(() =>
        scroller.evaluate(
          el => el.scrollLeft >= el.scrollWidth - el.clientWidth - 2
        )
      )
      .toBe(true);
    await expect(fade).toHaveCount(0);
  });
});
