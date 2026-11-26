import { expect, test, type Locator, type Page } from "@playwright/test";
import { injectSupabaseSession } from "./support/session";

/**
 * 投顾组合详情页六区块回归网（2026-11-25 重设计）。
 *
 * ## 这一轮换了什么（旧断言为什么整体重写）
 *
 * 旧版是**一张卡**塞六块（身份网格 / 收益 / 风险 / 成分 / 调仓 / 脚注），旧文件钉的是
 * `.advisor-section` + `.advisor-adjusts-block` + `.advisor-footnote__*` 那一套类名。
 * 重设计把它按「结论 → 归因 → 细节」拆成六张卡、各有锚点（页内导航才真正可用），
 * 类名全部随组件重建——旧断言不是「过时」，是**被测对象已不存在**。
 *
 * ## 每个区块钉一条「用户能看见、单测看不见」的不变式
 *
 * | 区块 | 不变式 | 反向验证（把实现改回去就红在哪） |
 * |---|---|---|
 * | 概览 | 只答「是什么、什么价」：身份行 + 净值 + 净值日，**业绩/风险指标一律不在此**（§02 是唯一归属） | 把 KPI 网格加回来 → `.kpi` 计数与「不含最大回撤/夏普/成立以来」几条同时红 |
 * | 收益与风险 | 近端四档落同一 ±20% 刻度、缺档不留空行；风险项**中性色** | 给 `.risk__value` 套涨跌色 → 颜色判据红 |
 * | 成分基金 | 权重降序 + 前三大合计；「我的持仓」三态（持有 / 未持有 / 未知）；标的走 `ProductDisplay` | 把 `heldCodes` 的 null 当空数组 → 「未知」被写成「未持有」；换回手写 span → `.product-cell--compact` 断言红 |
 * | 主理人调仓 | 日期倒序、加/减计数、来源标注；**有推导就挂声明** | 官方来源也挂声明 → 「不冒充」用例红 |
 * | 与我账户的对照 | 五方向同一刻度、差值 ≥5pp 才点色、提示条只点两档、覆盖率必须显示 | 按 100% 呈现覆盖率 / 三档全点色 → 对应用例红 |
 * | 组合档案 | 6 行属性齐（两列整 3 行、缺项「—」）**且不含最新净值/运作天数** + 来源行强弱分层 + 外链可感知 | 加回「最新净值」行 → 行数与标签数组同时红；无 `source_url` 仍渲染 `<a>` → 死链用例红 |
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
    strategy_summary: "以宽基为底仓，行业主题做卫星，控制单一行业暴露。",
    strategy_desc: "更长的策略说明，实际页面优先展示摘要。",
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
    // ⚠️ 量纲：接口给的是**百分数**（真实库实测 ZH012926：return_1d = -0.4、
    // return_since_incep = 175.64、max_drawdown = 32.96），不是小数。
    // 抄旧夹具的小数会让 fmtPct 输出「+0.00%」、条形宽度缩到 1/100——
    // 本文件曾整轮踩过这个坑，故这里逐项与真实响应同量纲。
    annual_return: 9.12,
    return_1d: 0.31,
    return_1w: 1.2,
    return_1m: 2.1,
    // 近 3 月故意缺：近端四档里要证明「缺档不留空行」
    return_1q: null,
    return_6m: 5.8,
    return_1y: 13.2,
    return_ytd: null,
    // 成立以来故意缺：收益大数字（§02）不能出现「—」占位；概览已不再展示该项
    return_since_incep: null,
    // 回撤也是百分数且为正（「跌了多少」由标签表达，不靠符号）
    max_drawdown: 18.42,
    volatility: 13.27,
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

function fund(
  fund_code: string,
  fund_name: string,
  advisor_ratio: number | null,
  my_market_value_cents: number | null
) {
  return { fund_code, fund_name, advisor_ratio, my_market_value_cents };
}

/** 我侧权益市值 100 万分（¥10000）：三集合的百分比据此算，便于手算校验 */
const MINE_TOTAL_CENTS = 1_000_000;

const COMPARE = {
  advisor: {
    code: CODE,
    name: "远足",
    platform: "QIEMAN",
    product_type: "基金组合",
    as_of_date: "2026-10-30",
    holdings: [
      fund("110011", "易方达中小盘混合", 25, null),
      fund("000961", "天弘沪深300ETF联接A", 20, null)
    ],
    max_drawdown: -0.1842,
    sharpe_ratio: 1.12,
    volatility: 0.1327,
    annual_return: 0.0912,
    return_since_incep: null,
    return_1y: 0.132,
    degraded: false
  },
  mine: {
    holdings: [],
    total_market_value_cents: MINE_TOTAL_CENTS,
    degraded: false
  },
  overlap: {
    // 共同持有 25 万 → 25.00% 我的市值
    common: [fund("110011", "易方达中小盘混合", 25, 250_000)],
    advisor_only: [fund("000961", "天弘沪深300ETF联接A", 20, null)],
    // 组合外两只 3 万 + 2 万 → 5.00% 我的市值
    mine_only: [
      fund("519674", "银河创新成长混合C", null, 30_000),
      fund("001186", "富国文体健康股票A", null, 20_000)
    ]
  },
  caveats: ["货基与债基已剔除", "本页不构成投资建议"]
};

/**
 * 方向对照：组合侧抄真实库实测值（18.82 / 34.58 / 31.96 / 7.36 / 7.28，覆盖 91.5%），
 * 我侧抄真实账户值。差值算出来是 +0.9 / −16.2 / −1.3 / −2.3 / +18.9 ——
 * 恰好覆盖「两档超 5pp」「三档不点色」，且最大档是固收（不是排第一的大盘），
 * 能证明提示条是按差值排序、不是按行序取前二。
 */
const STYLE_COMPARE = {
  code: CODE,
  name: "远足",
  platform: "QIEMAN",
  advisor: {
    as_of_date: "2026-10-30",
    has_snapshot: true,
    directions: [
      { key: "大盘", value: 18.82 },
      { key: "中盘", value: 34.58 },
      { key: "小盘", value: 31.96 },
      { key: "港股", value: 7.36 },
      { key: "固收", value: 7.28 }
    ],
    fund_count: 5,
    covered_weight_pct: 90.15,
    coverage_pct: 91.5,
    missing: [
      { fund_code: "001186", fund_name: "富国文体健康股票A", weight_pct: 8.37 }
    ],
    degraded: false
  },
  mine: {
    directions: [
      { key: "大盘", value: 19.74 },
      { key: "中盘", value: 18.34 },
      { key: "小盘", value: 30.71 },
      { key: "港股", value: 5.03 },
      { key: "固收", value: 26.17 }
    ],
    total_market_value_cents: MINE_TOTAL_CENTS,
    coverage_pct: 99.11,
    fund_count: 8,
    period_to: "2026-09-30",
    degraded: false
  },
  caveats: ["风格来自基金最近一期风格箱", "本页不构成投资建议"]
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
  /** 档案接口整体失败（整块空态） */
  failProfile?: boolean;
  /** 对比接口失败（「我的持仓」列应显示「—」而不是「未持有」） */
  failCompare?: boolean;
  /** 方向对照接口失败（三集合照常展示，只有方向块降级） */
  failStyle?: boolean;
  /** 覆盖档案路由（用于统计请求次数） */
  onProfileRequest?: () => void;
}

async function stubApis(page: Page, opts: StubOpts = {}) {
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
          // 组合类没有市场 / 场所（与真实库一致）；这里若写成 "CN_A"，识别卡
          // 会因为有「市场」这项身份事实而成卡，下面「整卡不渲染」的断言就失去意义
          market: null,
          venue: null,
          display_name: "远足",
          // **故意设为已关注**：这正是旧判据（「有任何一项就成卡」）会造出
          // 「只有『自选 / 已关注』的死横幅」的那组输入，否则断言会碰巧绿
          in_watchlist: true,
          // 不持有：持仓 / 交易 / 走势叠加三个区块不渲染，本用例只关心投顾区块
          has_position: false,
          source: "catalog"
        },
        message: "ok"
      }
    })
  );

  await page.route(/\/api\/products\/advisor-profile\//, route => {
    opts.onProfileRequest?.();
    if (opts.failProfile) {
      return route.fulfill({
        status: 500,
        json: { data: null, message: "e2e 档案故障", error_code: 50000 }
      });
    }
    return route.fulfill({
      status: 200,
      json: { data: profile(opts.profile), message: "ok" }
    });
  });

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

  await page.route(/\/api\/funds\/advisors\/[^/]+\/compare\//, route =>
    opts.failCompare
      ? route.fulfill({
          status: 500,
          json: { data: null, message: "e2e 对比故障", error_code: 50000 }
        })
      : route.fulfill({ status: 200, json: { data: COMPARE, message: "ok" } })
  );

  await page.route(/\/api\/funds\/advisors\/[^/]+\/style-compare\//, route =>
    opts.failStyle
      ? route.fulfill({
          status: 500,
          json: { data: null, message: "e2e 风格故障", error_code: 50000 }
        })
      : route.fulfill({
          status: 200,
          json: { data: STYLE_COMPARE, message: "ok" }
        })
  );
}

/** 读一个元素的计算样式（层级判据必须可计算，不能靠看截图） */
function computed(locator: Locator, props: string[]) {
  return locator.evaluate((el, keys) => {
    const s = getComputedStyle(el);
    return Object.fromEntries(keys.map(k => [k, s.getPropertyValue(k)]));
  }, props as string[]);
}

/** 详情页只有一个滚动宿主（布局层 `.el-scrollbar__wrap`），区块卡是它的后代 */
async function gotoPortfolio(page: Page) {
  await page.goto(`/#/portfolio/${CODE}`);
  // 概览是首块，它到位即代表品类门控通过、档案已返回
  await expect(page.locator("#nav-advisor")).toBeVisible({ timeout: 120_000 });
}

test.describe("投顾组合详情页 · 六区块结构", () => {
  test.setTimeout(120_000);

  test("六张卡各自渲染并挂上锚点（导航无死链）", async ({
    context,
    baseURL,
    page
  }) => {
    // 重设计的核心就是「拆」：一张卡时页内导航只能给一个入口。这里钉的是
    // 六块**同时**存在且各有锚点——删掉任一 import，Vue 只发 warning、父级透传的
    // id 静默丢弃，页面无可见报错（#2029 同款静默消失防线）。
    const pageErrors: string[] = [];
    page.on("pageerror", e => pageErrors.push(e.message));
    await injectSupabaseSession(context, baseURL!);
    await stubApis(page);
    await gotoPortfolio(page);

    for (const id of [
      "#nav-advisor",
      "#nav-advisor-returns",
      "#nav-advisor-holdings",
      "#nav-advisor-adjusts",
      "#nav-advisor-compare",
      "#nav-advisor-archive"
    ]) {
      await expect(page.locator(id)).toBeVisible();
    }

    // 六个锚点必须**都**进页头目录（少一个就是「有区块没入口」），且相对顺序固定。
    // 判据用「过滤后全等」而不是「整份清单」或「连续六项」：
    //   - 整份清单里还有走势 / 关联标的 / 更多数据，数量随品类与桩返回而变；
    //   - 六个投顾块**并不相邻**——`nav-trend`（走势）就夹在概览与收益之间
    //     （ProductDetailSections 里概览紧跟识别卡、走势紧随其后，其余五块在
    //     ProductAdvisorSection 里），实测目录序为 概览 · 走势 · 收益与风险 …
    await page.locator(".toc-menu__btn").click();
    const labels = await page
      .locator(".toc-menu__item")
      .evaluateAll(els => els.map(el => el.textContent?.trim() ?? ""));
    const ADVISOR_LABELS = [
      "概览",
      "收益与风险",
      "成分基金",
      "主理人调仓",
      "与我账户的对照",
      "组合档案"
    ];
    expect(labels.filter(label => ADVISOR_LABELS.includes(label))).toEqual(
      ADVISOR_LABELS
    );
    // 目录条目数 == 锚点数：既证明没有死链，也证明没有「有区块没入口」
    const counts = await page.evaluate(() => ({
      items: document.querySelectorAll(".toc-menu__item").length,
      anchors: document.querySelectorAll('.product-detail__main [id^="nav-"]')
        .length
    }));
    expect(counts.items).toBe(counts.anchors);
    expect(pageErrors).toEqual([]);
  });

  test("档案只取一次：概览与下部区块共用同一份响应", async ({
    context,
    baseURL,
    page
  }) => {
    // 概览（§01）与档案（§06）都要 profile。若各发一次，用户每次浏览多打一次请求，
    // 且两处可能拿到不同快照（滚动过程中刷新）。判据是**请求次数 == 1**。
    // 反向验证：删掉 advisorProfileCache 的 in-flight 去重 → 本用例红。
    let profileRequests = 0;
    await injectSupabaseSession(context, baseURL!);
    await stubApis(page, { onProfileRequest: () => (profileRequests += 1) });
    await gotoPortfolio(page);

    await expect(page.locator(".advisor-archive")).toBeVisible();
    expect(profileRequests).toBe(1);
  });

  test("档案取不到：整块一张空态卡，不拆成五张各报一次错", async ({
    context,
    baseURL,
    page
  }) => {
    await injectSupabaseSession(context, baseURL!);
    await stubApis(page, { failProfile: true });
    await page.goto(`/#/portfolio/${CODE}`);

    // 设计 §6 诚实降级：档案是其余五块的入参，缺了它们全都没有——一张卡说一次。
    // 两处都会写出同一句话（概览自己取同一份档案），故按组件作用域取，
    // 不用 getByText（那会 strict mode 撞两个元素）。
    await expect(page.locator(".advisor-section-state__text")).toHaveText(
      "暂无可展示的投顾组合资料",
      { timeout: 120_000 }
    );
    await expect(page.locator(".advisor-overview__hint")).toHaveText(
      "暂无可展示的投顾组合资料"
    );
    // 概览卡（独立取同一份档案）同样降级，但**不**渲染出六张空卡
    await expect(page.locator("#nav-advisor-returns")).toHaveCount(0);
    await expect(page.locator("#nav-advisor-holdings")).toHaveCount(0);
    await expect(page.locator("#nav-advisor-adjusts")).toHaveCount(0);
    await expect(page.locator("#nav-advisor-compare")).toHaveCount(0);
    await expect(page.locator("#nav-advisor-archive")).toHaveCount(0);
  });
});

test.describe("§01 概览", () => {
  test.setTimeout(120_000);

  // 只注入会话 + 打桩，**不导航**：同一 hash 的 goto 不触发重新取数，
  // 需要改桩（fail*）的用例必须自己掌控「打桩 → 首次导航」的先后。
  test.beforeEach(async ({ context, baseURL, page }) => {
    await injectSupabaseSession(context, baseURL!);
    await stubApis(page);
  });

  test("身份行 + 净值；业绩指标不在这里（全页唯一归属）", async ({ page }) => {
    await gotoPortfolio(page);
    const card = page.locator(".advisor-overview");
    await expect(card).toBeVisible();

    // 识别卡整卡不渲染：组合类不展示代码（设计 §2.6）也没有市场 / 场所，
    // 身份事实为空 ⇒ 不成卡。反向验证：把 `hasIdentityFacts` 退回旧的
    // 「有任何一项就成卡」→ 这里会多出一张横贯整行、只写「自选 / 已关注」的
    // 横幅（用户 2026-11-26 实测报的就是它：不可取消、无 tag、无意义）。
    await expect(page.locator(".product-detail__hero")).toHaveCount(0);

    // 身份一行读完「谁在管、什么风险」；主理人缺失则整项跳过。
    // 不含成立日期——它是档案属性（§06 有），概览不重复。
    await expect(card.locator(".advisor-overview__meta")).toHaveText(
      "且慢 · 盈米基金 · 中风险 · 基金组合"
    );

    // 净值保留 4 位（与库内 nav 精度一致），日涨跌带方向箭头（颜色不是唯一载体）
    await expect(card.locator(".navnow__value")).toHaveText("2.4137");
    await expect(card.locator(".navnow__delta")).toContainText("+0.31%");
    await expect(card.locator(".navnow__delta")).toContainText("↑");
    // 净值日全页只出现一次（此前页头戳 + 净值下方各写一遍）
    await expect(card.locator(".navnow__date")).toHaveText(
      "净值日期 2026-10-30"
    );

    // 业绩/风险指标**不在这块**——它们在 §02。同一屏里每个数字出现两次，
    // 读者反而不确定该信哪个（用户 2026-11-26：「同一个页面出现一次就够了」）。
    // 反向验证：把 KPI 网格加回来 → 下面几条立刻红。
    await expect(card.locator(".kpi")).toHaveCount(0);
    await expect(card).not.toContainText("最大回撤");
    await expect(card).not.toContainText("夏普比率");
    await expect(card).not.toContainText("成立以来");

    // 策略说明默认两行截断，按钮真能展开（aria-expanded 是唯一可断言的状态位）
    const toggle = card.locator(".strategy__toggle");
    await expect(toggle).toHaveText("展开");
    await expect(toggle).toHaveAttribute("aria-expanded", "false");
    await toggle.click();
    await expect(toggle).toHaveText("收起");
    await expect(toggle).toHaveAttribute("aria-expanded", "true");
  });
});

test.describe("§02 收益与风险", () => {
  test.setTimeout(120_000);

  // 只注入会话 + 打桩，**不导航**：同一 hash 的 goto 不触发重新取数，
  // 需要改桩（fail*）的用例必须自己掌控「打桩 → 首次导航」的先后。
  test.beforeEach(async ({ context, baseURL, page }) => {
    await injectSupabaseSession(context, baseURL!);
    await stubApis(page);
  });

  test("近端四档同一刻度、缺档不留空行；风险项用中性色", async ({ page }) => {
    await gotoPortfolio(page);
    const card = page.locator("#nav-advisor-returns");

    // return_1q 为 null ⇒ 只有 3 行（缺档不占行、也不写「—」）
    await expect(card.locator(".ret__row")).toHaveCount(3);
    await expect(card.locator(".ret__label")).toHaveText([
      "近 1 月",
      "近 6 月",
      "近 1 年"
    ]);
    // 「近 1 月」+2.10% → 宽度 = 2.1/20 × 50 = 5.25%（四档共用 ±20% 刻度，零轴居中）。
    // 从 inline style 读宽度而不量像素：判据要钉的是 `Math.min(|v|/SCALE,1)*50`
    // 这个换算本身，量出来的像素宽会随容器宽度变化，钉不住刻度。
    await expect(card.locator(".ret__bar").first()).toHaveAttribute(
      "style",
      /width: 5\.25%/
    );
    // 正收益的条从零轴右侧起（left 50%），负收益才是 50-width
    await expect(card.locator(".ret__bar").first()).toHaveAttribute(
      "style",
      /left: 50%/
    );
    await expect(card.locator(".ret__val").first()).toHaveText("+2.10%");

    // 长期两档与近端不同尺度：成立以来缺失 ⇒ 只剩「年化」一格
    await expect(card.locator(".longterm > div")).toHaveCount(1);
    await expect(card.locator(".longterm__value")).toHaveText("+9.12%");
    await expect(card.locator(".longterm__sub")).toHaveText("按运作时长折算");

    // 风险三项全在，且颜色 == 正文色（不套涨跌色）
    await expect(card.locator(".risk")).toHaveCount(3);
    await expect(card.locator(".risk__value")).toHaveText([
      "18.42%",
      "13.27%",
      "1.120"
    ]);
    const riskColor = await computed(card.locator(".risk__value").first(), [
      "color"
    ]);
    const bodyColor = await computed(
      page.locator("#nav-advisor-archive .archive__value").first(),
      ["color"]
    );
    expect(riskColor.color).toBe(bodyColor.color);
  });
});

test.describe("§03 成分基金", () => {
  test.setTimeout(120_000);

  // 只注入会话 + 打桩，**不导航**：同一 hash 的 goto 不触发重新取数，
  // 需要改桩（fail*）的用例必须自己掌控「打桩 → 首次导航」的先后。
  test.beforeEach(async ({ context, baseURL, page }) => {
    await injectSupabaseSession(context, baseURL!);
    await stubApis(page);
  });

  test("权重降序 + 前三大合计 + 「我的持仓」三态", async ({ page }) => {
    await gotoPortfolio(page);
    const card = page.locator("#nav-advisor-holdings");

    // 表头即契约：三列，权重列带条内条（集中度靠它一眼可得）
    await expect(card.locator("thead th")).toHaveText([
      "基金",
      "权重",
      "我的持仓"
    ]);
    await expect(card.locator(".advisor-holdings__summary")).toHaveText(
      "3 只 · 前三大 60.00% · 快照 2026-10-30"
    );

    // 默认占比降序：25 / 20 / 15（不是后端返回的原始顺序）
    await expect(card.locator("tbody tr")).toHaveCount(3);
    const weights = card.locator(".weight__num");
    await expect(weights).toHaveText(["25.00%", "20.00%", "15.00%"]);

    // 条内条的分母是最大权重 ⇒ 最大的一只拉满。
    // ⚠️ 断言容得下「100%」：`el.style.width = "100.0%"` 经 CSSOM 序列化后
    // 尾零被吃掉，属性里读回的是 `width: 100%`（Playwright 实测）。
    await expect(card.locator(".weight__fill").first()).toHaveAttribute(
      "style",
      /width: 100(\.0+)?%/
    );

    // 「我的持仓」给的是**仓位**不只是状态：金额（¥2,500 = 250_000 分）+ 占我
    // 权益市值的比例（÷ 1_000_000 分 = 25.0%）。反向验证：把 heldByCode 里的
    // my_market_value_cents 当 0 → 金额变 ¥0、占比变 0.0%，本用例红。
    const held = card.locator("tbody tr").first().locator(".held");
    await expect(held.locator(".held__amount")).toHaveText("¥2,500");
    // 文案落在「仓位」这个名词上；不足 0.1% 走「<0.1%」由单测钉（见 advisorModel.spec）
    await expect(held.locator(".held__pct")).toHaveText("占我仓位 25.0%");
    await expect(
      card.locator("tbody tr").nth(1).locator(".held-none")
    ).toHaveText("未持有");

    // 标的标识必须走仓库统一的 ProductDisplay（名称一行 + `# 代码` 一行），
    // 而不是本卡片自写一份「名称 + 代码」——那份会漏掉行高、截断与代码前缀约定。
    // 反向验证：换回手写 span（去掉 ProductDisplay）→ 这两条立刻红。
    const firstFund = card.locator("tbody tr").first();
    await expect(firstFund.locator(".product-cell--compact")).toHaveCount(1);
    await expect(firstFund.locator(".product-code-compact")).toHaveText(
      "# 110011"
    );

    // 未收录本地名录的基金不给链接（点进去是 404），但给灰标说明
    await expect(card.locator(".advisor-holdings__flag")).toHaveText([
      "未收录"
    ]);
    await expect(card.locator("tbody tr").nth(2).locator("a")).toHaveCount(0);
  });

  test("排序按钮真会翻转行序（状态位不是装饰）", async ({ page }) => {
    await gotoPortfolio(page);
    const card = page.locator("#nav-advisor-holdings");
    const sort = card.locator(".advisor-holdings__sort");
    await expect(sort).toHaveText("占比降序");
    await sort.click();
    await expect(sort).toHaveText("占比升序");
    await expect(card.locator(".weight__num")).toHaveText([
      "15.00%",
      "20.00%",
      "25.00%"
    ]);
  });

  test("对比取不到：「我的持仓」列是未知（—），不是「未持有」", async ({
    context,
    baseURL,
    page
  }) => {
    // 两者对用户是天差地别的结论：写「未持有」会让人以为自己与该组合零重合。
    // 反向验证：把 heldCodes 的 null 兜成 [] → 本用例红。
    await injectSupabaseSession(context, baseURL!);
    await stubApis(page, { failCompare: true });
    await gotoPortfolio(page);

    const card = page.locator("#nav-advisor-holdings");
    await expect(card.locator("tbody tr")).toHaveCount(3);
    await expect(card.locator(".held")).toHaveCount(0);
    await expect(
      card.locator("tbody tr").first().locator(".held-none")
    ).toHaveText("—");
  });
});

test.describe("§04 主理人调仓", () => {
  test.setTimeout(120_000);

  test("3 组倒序渲染 + 加/减计数 + 推导口径声明", async ({
    context,
    baseURL,
    page
  }) => {
    await injectSupabaseSession(context, baseURL!);
    await stubApis(page);
    await gotoPortfolio(page);

    const card = page.locator("#nav-advisor-adjusts");
    // 标题右侧给「几次 · 最近哪天」：只写「主理人调仓」看不出有多少历史
    await expect(card.locator(".advisor-timeline__summary")).toHaveText(
      "3 次 · 最近 2026-10-28"
    );

    // 宿主不重排：后端给什么序就渲染什么序（两处各排一次必然不一致）
    const items = card.locator(".tl__item");
    await expect(items).toHaveCount(3);
    await expect(card.locator(".tl__date")).toHaveText([
      /2026-10-28/,
      /2026-09-16/,
      /2026-08-05/
    ]);
    // 最近一次用实心轴点，其余空心
    await expect(items.first()).toHaveAttribute("data-latest", "true");

    const first = items.first();
    await expect(first.locator(".tl__date")).toContainText("2 笔");
    await expect(first.locator(".chip--in")).toHaveText("加仓 1");
    await expect(first.locator(".chip--out")).toHaveText("减仓 1");
    await expect(first.locator(".tl__source")).toHaveText("快照推导");
    await expect(first.locator(".chg__row")).toHaveCount(2);
    await expect(first.locator(".chg__op--add")).toHaveText("加仓");
    await expect(first.locator(".chg__op--cut")).toHaveText("减仓");
    await expect(first.locator(".chg__ratio").first()).toHaveText(
      "20.00% → 25.00%"
    );

    // 来源是快照推导就必须挂声明——不写等于冒充官方数据
    const caveat = card.locator(".advisor-timeline__caveat");
    await expect(caveat).toBeVisible();
    // 判据是「说清它不是官方数据」：既点了来源性质（快照推导），也说清了怎么来的
    await expect(caveat).toContainText("快照推导");
    await expect(caveat).toContainText("由持仓快照序列算出");
    await expect(caveat).toContainText("可能与实际调仓存在差异");
  });

  test("超过 4 组：折叠在「查看更早」，展开后全在", async ({
    context,
    baseURL,
    page
  }) => {
    await injectSupabaseSession(context, baseURL!);
    await stubApis(page, {
      adjusts: [
        adjustGroup("2026-10-28"),
        adjustGroup("2026-09-16"),
        adjustGroup("2026-08-05"),
        adjustGroup("2026-07-11"),
        adjustGroup("2026-06-20"),
        adjustGroup("2026-05-09")
      ]
    });
    await gotoPortfolio(page);

    const card = page.locator("#nav-advisor-adjusts");
    // 首屏 4 组（TL_INITIAL）：再多会把下面的对照挤到两屏外
    await expect(card.locator(".tl__item")).toHaveCount(4);
    const more = card.locator(".link-more--all");
    await expect(more).toHaveText(/查看更早的调仓（2 次）/);
    await expect(more).toHaveAttribute("aria-expanded", "false");

    await more.click();
    await expect(card.locator(".tl__item")).toHaveCount(6);
    await expect(more).toHaveText(/收起更早的调仓/);
    await expect(more).toHaveAttribute("aria-expanded", "true");
  });

  test("空态：说清「为什么没有」，不留白也不误挂声明", async ({
    context,
    baseURL,
    page
  }) => {
    await injectSupabaseSession(context, baseURL!);
    await stubApis(page, { adjusts: [] });
    await gotoPortfolio(page);

    const card = page.locator("#nav-advisor-adjusts");
    // 且慢：必须解释「需累积 ≥2 次快照」，否则用户以为功能坏了
    await expect(card.locator(".advisor-timeline__hint")).toContainText(
      "需累积 ≥2 次快照"
    );
    // 没有记录 → 不该挂「快照推导」声明（无记录可声明，挂了就是噪声）
    await expect(card.locator(".advisor-timeline__caveat")).toHaveCount(0);
    await expect(card.locator(".tl__item")).toHaveCount(0);
  });

  test("官方来源：来源标注改为官方披露，且不挂推导声明", async ({
    context,
    baseURL,
    page
  }) => {
    await injectSupabaseSession(context, baseURL!);
    await stubApis(page, {
      profile: { platform: "TIANTIAN" },
      adjusts: [adjustGroup("2026-10-28", { source: "tiantian" })]
    });
    await gotoPortfolio(page);

    const card = page.locator("#nav-advisor-adjusts");
    await expect(card.locator(".tl__item")).toHaveCount(1);
    await expect(card.locator(".tl__source")).toHaveText("天天官方");
    // 官方数据给免责声明 = 把真数据说成推的
    await expect(card.locator(".advisor-timeline__caveat")).toHaveCount(0);
  });
});

test.describe("§05 与我账户的对照", () => {
  test.setTimeout(120_000);

  // 只注入会话 + 打桩，**不导航**：同一 hash 的 goto 不触发重新取数，
  // 需要改桩（fail*）的用例必须自己掌控「打桩 → 首次导航」的先后。
  test.beforeEach(async ({ context, baseURL, page }) => {
    await injectSupabaseSession(context, baseURL!);
    await stubApis(page);
  });

  test("五方向同一刻度 + 差值 ≥5pp 才点色 + 提示条只点两档", async ({
    page
  }) => {
    await gotoPortfolio(page);
    const card = page.locator("#nav-advisor-compare");

    // 五档全在（以组合侧为骨架，缺哪个方向就错位）
    await expect(card.locator(".dir")).toHaveCount(5);
    await expect(card.locator(".dir__k")).toHaveText([
      "大盘",
      "中盘",
      "小盘",
      "港股",
      "固收"
    ]);

    // 同一刻度：分母是两侧实测最大值（34.58），故中盘的组合条拉满
    await expect(
      card.locator('.dir[aria-label^="中盘"] .dir__fill--adv')
    ).toHaveAttribute("style", /width: 100(\.0+)?%/);

    // 差值文案带符号；只有 中盘(−16.2) 与 固收(+18.9) 超 5pp 才点色
    // （小盘 −1.25 经「先取显示精度再判零」得 −1.2，不是 −1.3：Math.round 对
    //   .5 取大，diffText 的两步四舍五入是刻意为之，见 advisorDirectionModel）
    await expect(card.locator(".dir__d")).toHaveText([
      "+0.9",
      "-16.2",
      "-1.2",
      "-2.3",
      "+18.9"
    ]);
    await expect(card.locator(".dir__d--big")).toHaveCount(2);

    // 提示条按**差值绝对值**排序（固收 18.9 > 中盘 16.2），不是按行序取前二
    const callout = card.locator(".callout");
    await expect(callout).toContainText("方向差异 ≥ 5pp");
    await expect(callout).toContainText("固收 我 26.17% · 组合 7.28%");
    await expect(callout).toContainText("中盘 组合 34.58% · 我 18.34%");

    // 覆盖率是结论的一部分：按 100% 呈现会把缺失的 8.37% 摊进其他方向
    await expect(card.locator(".dir__note")).toContainText("覆盖 91.5%");
    await expect(card.locator(".advisor-compare__coverage")).toContainText(
      "8.37%"
    );
    await expect(card.locator(".advisor-compare__coverage")).toContainText(
      "未计入方向占比"
    );
  });

  test("三集合清单给「占我市值多少」+ 组合外持仓可展开", async ({ page }) => {
    await gotoPortfolio(page);
    const card = page.locator("#nav-advisor-compare");

    // 数量本身不说明问题——比例才是用户要的那个数
    await expect(card.locator(".chips .chip")).toHaveCount(3);
    await expect(card.locator(".chips .chip").first()).toContainText(
      "组合里有 · 我也持有"
    );
    await expect(card.locator(".chips .chip").first()).toContainText(
      "25.00% 我的市值"
    );
    await expect(card.locator(".chips .chip").last()).toContainText(
      "我持有 · 组合里没有"
    );
    await expect(card.locator(".chips .chip").last()).toContainText(
      "5.00% 我的市值"
    );

    const more = card.locator(".link-more");
    await expect(more).toHaveText(/展开组合外持仓（2 只）/);
    await expect(card.locator(".outside")).toHaveCount(0);
    await more.click();
    await expect(card.locator(".outside li")).toHaveCount(2);
    await expect(card.locator(".outside__weight")).toHaveText([
      "3.00%",
      "2.00%"
    ]);
    await expect(more).toHaveText(/收起组合外持仓/);
  });

  test("方向数据取不到：只降级方向块，三集合照常展示", async ({
    context,
    baseURL,
    page
  }) => {
    // 方向口径（风格箱）与三集合（基金代码级）是两件事，前者挂了不该拖走后者。
    await injectSupabaseSession(context, baseURL!);
    await stubApis(page, { failStyle: true });
    await gotoPortfolio(page);

    const card = page.locator("#nav-advisor-compare");
    await expect(card.locator(".dir")).toHaveCount(0);
    await expect(card.locator(".callout")).toHaveCount(0);
    await expect(card.locator(".advisor-compare__hint")).toContainText(
      "方向对照稍后再看"
    );
    // 三集合与组合外持仓仍在
    await expect(card.locator(".chips .chip")).toHaveCount(3);
    await expect(card.locator(".link-more")).toContainText("展开组合外持仓");
  });
});

test.describe("§06 组合档案与来源", () => {
  test.setTimeout(120_000);

  test("6 行属性齐（缺项「—」）+ 来源行强弱分层 + 外链可感知", async ({
    context,
    baseURL,
    page
  }) => {
    await injectSupabaseSession(context, baseURL!);
    await stubApis(page);
    await gotoPortfolio(page);

    const card = page.locator("#nav-advisor-archive");
    // 6 行 = 两列网格的整 3 行（少一行就空出一格灰底，像表格少画了一块）。
    // 不含「最新净值」（净值只在 §01 出现一处）、不含「运作天数」
    // （派生量 + 实测常为 null）。
    // 反向验证：把「最新净值」行加回来 → 行数与标签数组同时红。
    await expect(card.locator(".archive > div")).toHaveCount(6);
    await expect(card.locator(".archive__label")).toHaveText([
      "平台",
      "机构",
      "主理人",
      "风险等级",
      "产品类型",
      "成立日期"
    ]);
    await expect(card).not.toContainText("最新净值");

    // 缺项一律「—」（与后端「取不到就 null」的契约对称），不隐藏行——隐藏会让
    // 「平台没披露」与「这一项我们不关心」看起来一样
    await expect(
      card
        .locator(".archive > div", { hasText: "主理人" })
        .locator(".archive__value")
    ).toHaveText("—");

    // 来源行：弱标签「数据来源」+ 强值「且慢」
    await expect(card.locator(".src__label")).toHaveText("数据来源");
    await expect(card.locator(".src__value")).toHaveText("且慢");
    // 持仓快照日说明成分基金的口径时点（与成分基金卡的快照一致）
    await expect(card.locator(".src")).toContainText("持仓快照 2026-10-30");

    // 外链：新窗口 + noopener、有下划线（不依赖颜色也能看出可点）+ 外链图标
    const link = card.locator(".src__link");
    await expect(link).toHaveAttribute("href", SOURCE_URL);
    await expect(link).toHaveAttribute("target", "_blank");
    await expect(link).toHaveAttribute("rel", /noopener/);
    await expect(link).toContainText("查看官方组合页面");
    await expect(link.locator("svg")).toHaveCount(1);
    const linkStyle = await computed(link, ["text-decoration-line"]);
    expect(linkStyle["text-decoration-line"]).toBe("underline");

    // 层级判据（可计算）：值比标签重（强/弱两档），声明行比来源行小 1px
    const valueStyle = await computed(card.locator(".src__value"), [
      "color",
      "font-weight"
    ]);
    const labelStyle = await computed(card.locator(".src__label"), [
      "color",
      "font-size"
    ]);
    const weakStyle = await computed(card.locator(".src__item--weak"), [
      "font-size"
    ]);
    expect(valueStyle["font-weight"]).toBe("600");
    expect(valueStyle.color).not.toBe(labelStyle.color);
    // 声明行与来源标签同为弱色，靠字号再退一档（颜色不是唯一区分手段，
    // 但也不能只靠颜色——故两档同时存在）
    expect(parseFloat(weakStyle["font-size"])).toBe(
      parseFloat(labelStyle["font-size"]) - 1
    );
  });

  test("无外链：不渲染死链接，来源行仍成立", async ({
    context,
    baseURL,
    page
  }) => {
    await injectSupabaseSession(context, baseURL!);
    await stubApis(page, { profile: { source_url: null } });
    await gotoPortfolio(page);

    const card = page.locator("#nav-advisor-archive");
    await expect(card.locator(".src__value")).toHaveText("且慢");
    // 没有 source_url 还给链接 = 点了没反应（与「未收录」成分基金同一处理原则）
    await expect(card.locator(".src__link")).toHaveCount(0);
  });
});
