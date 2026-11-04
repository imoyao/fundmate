import { expect, test } from "@playwright/test";
import { injectSupabaseSession } from "./support/session";

/**
 * 投顾组合详情页「投顾组合」区块回归网（`feat/advisor-detail-adjust`）。
 *
 * 这一轮补的是三件**用户看得见、单元测试看不到**的事：
 *
 * 1. **调仓历史终于渲染了**：此前本区块刻意不渲染调仓（注释写着「待提取共用组件」），
 *    用户看到的是「调仓历史拿不到」。现在渲染已提取为 `AdvisorAdjustList`，
 *    与持仓页共用。单测只能钉住纯函数，钉不住「模板里到底挂了没有」——
 *    组件忘 import、被 `v-else` 吃掉、宿主没接线，全是单测的盲区。
 * 2. **推导口径必须写在脸上**：来源为快照推导（`qieman`）时，库里的记录由持仓快照序列推导。
 *    不挂声明就等于冒充官方数据。这里同时钉「该挂的时候挂了」与
 *    「官方来源（`tiantian` / `qieman_official`）不该挂」——只有前者会退化成「永远挂着免责」。
 *    （且慢自 2026-11-04 起有官方 GraphQL 调仓接口，`qieman_official` 行不挂免责。）
 * 3. **脚注层级**：旧版两条脚注同为 13px 灰色，来源行与免责声明长得一模一样；
 *    外链只是换了颜色、没有下划线也没有图标，用户「感知不到可外链」。
 *    现在按信息价值分两层，判据必须是**可计算的**（字号递减、颜色有别、
 *    链接带下划线），不能靠肉眼看截图。
 *
 * 接口全部 `page.route` 打桩，不依赖后端（`docs/dev/frontend-e2e.md` §7）。
 */

const CODE = "ZH012926";
const SOURCE_URL = "https://qieman.com/alfa/portfolio/detail/123456";

/** 档案：只给**区块主体需要**的字段，其余留 null 走「—」（真实库填充率实测） */
function profile(over: Record<string, unknown> = {}) {
  return {
    code: CODE,
    name: "远足",
    platform: "QIEMAN",
    org_name: "盈米基金",
    host: null,
    risk_level: "中风险",
    product_type: "基金组合",
    strategy_type: null,
    strategy_summary: null,
    strategy_desc: null,
    allocation: null,
    estab_date: "2017-07-24",
    running_days: null,
    benchmark: null,
    excess_return: null,
    nav: 2.4137,
    nav_date: "2026-10-30",
    source_url: SOURCE_URL,
    is_active: true,
    cum_return: null,
    annual_return: 0.0912,
    return_1d: 0.0031,
    return_1w: 0.012,
    return_1m: 0.021,
    return_1q: null,
    return_6m: 0.058,
    return_1y: 0.132,
    return_ytd: null,
    return_since_incep: null,
    max_drawdown: -0.1842,
    volatility: 0.1327,
    sharpe_ratio: 1.12,
    holding_count: 3,
    adjust_count: 2,
    ...over
  };
}

const HOLDINGS = {
  code: CODE,
  name: "远足",
  platform: "QIEMAN",
  as_of_date: "2026-10-30",
  holdings: [
    {
      fund_code: "110011",
      fund_name: "易方达中小盘混合",
      pre_ratio: 20,
      after_ratio: 25,
      op_name: "加仓",
      in_local_db: true
    },
    {
      fund_code: "000961",
      fund_name: "天弘沪深300ETF联接A",
      pre_ratio: 20,
      after_ratio: 20,
      op_name: null,
      in_local_db: true
    },
    {
      fund_code: "519674",
      fund_name: "银河创新成长混合C",
      pre_ratio: 20,
      after_ratio: 15,
      op_name: "减仓",
      in_local_db: false
    }
  ]
};

/** 一组调仓的完整形态：日期 + 只数 + 主理人原文 + 明细 */
function adjustGroup(date: string, over: Record<string, unknown> = {}) {
  return {
    adjust_date: date,
    reason: "降低单一行业暴露，增加宽基权重",
    source: "qieman" as string,
    items: [
      {
        fund_code: "110011",
        fund_name: "易方达中小盘混合",
        op_name: "加仓",
        pre_ratio: 20,
        after_ratio: 25
      },
      {
        fund_code: "519674",
        fund_name: "银河创新成长混合C",
        op_name: "减仓",
        pre_ratio: 20,
        after_ratio: 15
      }
    ],
    ...over
  };
}

interface StubOpts {
  /** 调仓分组；传 `[]` 走空态 */
  adjusts?: ReturnType<typeof adjustGroup>[];
  /** 档案覆盖项（改平台 / 外链有无） */
  profile?: Record<string, unknown>;
}

async function stubApis(
  page: import("@playwright/test").Page,
  opts: StubOpts = {}
) {
  // 兜底：未打桩的接口一律 404，避免用例静默依赖真实后端
  await page.route(/^https?:\/\/[^/]+\/api\//, route =>
    route.fulfill({
      status: 404,
      json: { data: null, message: "e2e 未打桩", error_code: 40400 }
    })
  );

  await page.route(/\/api\/utils\/enums\//, route =>
    route.fulfill({
      status: 200,
      json: {
        data: {
          asset_type: { portfolio: "投顾组合" },
          market: { CN_A: "A股" }
        },
        message: "ok"
      }
    })
  );

  // 品类门控：`asset_type === 'portfolio'` 才渲染本区块（ProductDetailSections）
  await page.route(/\/api\/products\/resolve\//, route =>
    route.fulfill({
      status: 200,
      json: {
        data: {
          symbol: CODE,
          asset_type: "portfolio",
          market: "CN_A",
          venue: null,
          display_name: "远足",
          in_watchlist: false,
          // 不持有：持仓 / 交易 / 走势叠加三个区块不渲染，本用例只关心投顾区块
          has_position: false,
          source: "catalog"
        },
        message: "ok"
      }
    })
  );

  await page.route(/\/api\/products\/advisor-profile\//, route =>
    route.fulfill({
      status: 200,
      json: { data: profile(opts.profile), message: "ok" }
    })
  );

  await page.route(/\/api\/funds\/advisors\/[^/]+\/holdings\//, route =>
    route.fulfill({ status: 200, json: { data: HOLDINGS, message: "ok" } })
  );

  await page.route(/\/api\/funds\/advisors\/[^/]+\/adjusts\//, route =>
    route.fulfill({
      status: 200,
      json: {
        data: {
          code: CODE,
          name: "远足",
          platform: opts.profile?.platform ?? "QIEMAN",
          adjusts: opts.adjusts ?? [
            adjustGroup("2026-10-28"),
            adjustGroup("2026-09-16"),
            adjustGroup("2026-08-05")
          ]
        },
        message: "ok"
      }
    })
  );
}

/** 读一个元素的计算样式（层级判据必须可计算，不能靠看截图） */
function computed(
  locator: import("@playwright/test").Locator,
  props: string[]
) {
  return locator.evaluate((el, keys) => {
    const s = getComputedStyle(el);
    return Object.fromEntries(keys.map(k => [k, s.getPropertyValue(k)]));
  }, props as string[]);
}

test.describe("投顾组合详情页：调仓渲染 + 脚注层级", () => {
  test.setTimeout(120_000);

  test("调仓：3 组明细渲染 + 推导口径声明已挂", async ({
    context,
    baseURL,
    page
  }) => {
    await injectSupabaseSession(context, baseURL!);
    await stubApis(page);
    await page.goto(`/#/portfolio/${CODE}`);

    const section = page.locator(".advisor-section");
    await expect(section).toBeVisible({ timeout: 120_000 });

    // 区块主体先到位（调仓块在它下面，主体没渲染时下面也不可能有）
    await expect(section.getByText("远足")).toBeVisible();
    await expect(section.getByText("盈米基金")).toBeVisible();

    const block = section.locator(".advisor-adjusts-block");
    await expect(block).toBeVisible();

    // 标题带条数：只写「主理人调仓」看不出有几组
    await expect(
      block.locator(".advisor-section__metrics-title")
    ).toContainText("主理人调仓");
    await expect(block.getByText("最近 3 次")).toBeVisible();

    // 三组，按后端给的倒序（宿主不重排——重排会与后端各排一次而不一致）
    const groups = block.locator(".advisor-adjusts__group");
    await expect(groups).toHaveCount(3);
    await expect(groups.first().locator(".advisor-adjusts__date")).toHaveText(
      "2026-10-28"
    );
    await expect(groups.nth(2).locator(".advisor-adjusts__date")).toHaveText(
      "2026-08-05"
    );

    // 每组：只数 + 主理人原文 + 明细行（方向文案走 advisorAdjust 同源口径）
    const first = groups.first();
    await expect(first.locator(".advisor-adjusts__count")).toHaveText(
      "2 只调整"
    );
    await expect(first.locator(".advisor-adjusts__reason")).toContainText(
      "降低单一行业暴露"
    );
    await expect(first.locator(".advisor-adjusts__item")).toHaveCount(2);
    await expect(first.getByText("加仓").first()).toBeVisible();
    await expect(first.getByText("减仓").first()).toBeVisible();

    // 推导口径：来源为快照推导（qieman）时，声明必须挂在列表下方
    const caveat = block.locator(".advisor-adjusts-block__caveat");
    await expect(caveat).toBeVisible();
    await expect(caveat).toContainText("持仓快照序列推导");
    // 判据是「说清它不是官方数据」——只写「可能有差异」等于没声明来源性质
    await expect(caveat).toContainText("不提供官方调仓公告");
  });

  test("调仓空态：说清「为什么没有」，不留白也不报错", async ({
    context,
    baseURL,
    page
  }) => {
    await injectSupabaseSession(context, baseURL!);
    await stubApis(page, { adjusts: [] });
    await page.goto(`/#/portfolio/${CODE}`);

    const block = page.locator(".advisor-adjusts-block");
    await expect(block).toBeVisible({ timeout: 120_000 });

    // 且慢：空态必须解释「需要累积两次快照」，否则用户以为功能坏了
    await expect(block.locator(".advisor-adjusts-block__hint")).toContainText(
      "持仓快照"
    );
    await expect(block).toContainText("2 次快照");

    // 没有记录 → 不该挂「快照推导」声明（无记录可声明，挂了就是噪声）
    await expect(block.locator(".advisor-adjusts-block__caveat")).toHaveCount(
      0
    );
    await expect(block.locator(".advisor-adjusts__group")).toHaveCount(0);
  });

  test("官方来源（天天基金）：不挂快照推导声明", async ({
    context,
    baseURL,
    page
  }) => {
    await injectSupabaseSession(context, baseURL!);
    await stubApis(page, {
      profile: { platform: "TIANTIAN" },
      adjusts: [adjustGroup("2026-10-28", { source: "tiantian" })]
    });
    await page.goto(`/#/portfolio/${CODE}`);

    const block = page.locator(".advisor-adjusts-block");
    await expect(block).toBeVisible({ timeout: 120_000 });

    await expect(block.locator(".advisor-adjusts__group")).toHaveCount(1);
    // 官方数据给免责声明 = 把真数据说成推的
    await expect(block.locator(".advisor-adjusts-block__caveat")).toHaveCount(
      0
    );
  });

  test("脚注：来源行强、声明行弱、外链可感知", async ({
    context,
    baseURL,
    page
  }) => {
    await injectSupabaseSession(context, baseURL!);
    await stubApis(page);
    await page.goto(`/#/portfolio/${CODE}`);

    const footnote = page.locator(".advisor-footnote");
    await expect(footnote).toBeVisible({ timeout: 120_000 });

    const label = footnote.locator(".advisor-footnote__label");
    const value = footnote.locator(".advisor-footnote__value");
    const link = footnote.locator(".advisor-footnote__link");
    const disclaimer = footnote.locator(".advisor-footnote__disclaimer");

    // 来源行：弱标签「数据来源」+ 强值「且慢」
    await expect(label).toHaveText("数据来源");
    await expect(value).toHaveText("且慢");

    // 外链：新窗口 + 带 noopener、有下划线（不依赖颜色也能看出可点）+ 外链图标
    await expect(link).toHaveAttribute("href", SOURCE_URL);
    await expect(link).toHaveAttribute("target", "_blank");
    await expect(link).toHaveAttribute("rel", /noopener/);
    await expect(link).toContainText("查看官方组合页面");
    await expect(link.locator("svg")).toHaveCount(1);

    const linkStyle = await computed(link, ["text-decoration-line", "color"]);
    expect(linkStyle["text-decoration-line"]).toBe("underline");

    // 层级判据（可计算）：值比标签重、声明比来源小 1px、链接颜色与正文不同
    const valueStyle = await computed(value, ["color", "font-weight"]);
    const labelStyle = await computed(label, ["color", "font-size"]);
    const disclaimerStyle = await computed(disclaimer, ["color", "font-size"]);

    expect(valueStyle["font-weight"]).toBe("600");
    expect(valueStyle["color"]).not.toBe(labelStyle["color"]);

    const sourcePx = parseFloat(labelStyle["font-size"]);
    const disclaimerPx = parseFloat(disclaimerStyle["font-size"]);
    expect(sourcePx).toBe(13);
    expect(disclaimerPx).toBe(sourcePx - 1);
    expect(disclaimerStyle["color"]).not.toBe(valueStyle["color"]);

    // 两条仍在同一组里（`--spaced` / `--attached` 间距语义照旧，未被本卡改掉）
    await expect(footnote.locator(".section-footnote--spaced")).toHaveCount(1);
    await expect(footnote.locator(".section-footnote--attached")).toHaveCount(
      1
    );
  });

  test("无外链：不渲染死链接，来源行仍成立", async ({
    context,
    baseURL,
    page
  }) => {
    await injectSupabaseSession(context, baseURL!);
    await stubApis(page, { profile: { source_url: null } });
    await page.goto(`/#/portfolio/${CODE}`);

    const footnote = page.locator(".advisor-footnote");
    await expect(footnote).toBeVisible({ timeout: 120_000 });

    await expect(footnote.locator(".advisor-footnote__value")).toHaveText(
      "且慢"
    );
    // 没有 source_url 还给链接 = 点了没反应（与「未收录」成分基金同一处理原则）
    await expect(footnote.locator(".advisor-footnote__link")).toHaveCount(0);
  });
});
