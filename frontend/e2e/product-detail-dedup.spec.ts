import { expect, test, type Page } from "@playwright/test";
import { injectSupabaseSession } from "./support/session";

/**
 * 产品详情页去重回归网（用户反馈：同一个产品名在一页里出现 4 次）。
 *
 * 钉两条不变式：
 * 1. 识别信息（名称 + 品类）只由页头承担，识别卡（`.product-detail__hero`）不再复述；
 * 2. 持仓区块按账户分行，行标签是渠道名，不再逐行抄产品名，表头整块只出一次——
 *    因此整页产品名恰好只出现 1 次。
 *
 * 接口全部用 `page.route` 打桩，不依赖后端（docs/dev/frontend-e2e.md §7）。
 */

const NAME = "永赢北证50成份指数发起C";
const SYMBOL = "023887";

async function stubProductApis(page: Page) {
  // 兜底：未显式打桩的接口一律 404，让各区块走自己的降级分支——
  // 否则这些请求会经 vite 代理打到本机 8000 端口的真后端，用例就不再自洽。
  // ⚠️ 必须用**锚定到 host 的正则**而不是 `**/api/**`：后者连 vite 的源码模块请求
  // `/src/api/auth.ts` 也一起匹配掉（首版就是这么把应用壳打死在加载页上的）。
  await page.route(/^https?:\/\/[^/]+\/api\//, route =>
    route.fulfill({
      status: 404,
      json: { data: null, message: "e2e 未打桩", error_code: 40400 }
    })
  );
  await page.route("**/api/utils/enums/**", route =>
    route.fulfill({
      status: 200,
      json: {
        data: {
          asset_type: { fund: "基金", stock: "股票" },
          market: { CN_A: "A股" },
          venue: { OTC: "场外", EXCHANGE: "场内" }
        },
        message: "ok"
      }
    })
  );
  await page.route("**/api/products/resolve/**", route =>
    route.fulfill({
      status: 200,
      json: {
        data: {
          symbol: SYMBOL,
          asset_type: "fund",
          market: "CN_A",
          venue: "OTC",
          display_name: NAME,
          in_watchlist: true,
          has_position: true,
          source: "position"
        },
        message: "ok"
      }
    })
  );
  // #2029：此前本用例根本没给 fund-profile 打桩，请求落到上面的兜底 404 →
  // 基金资料区块走降级分支 → 又因为 detail.vue 漏 import 而完全不渲染，
  // 两处缺陷互相掩盖。补上打桩后，缺 import 会直接让新增断言变红。
  await page.route("**/api/products/fund-profile/**", route =>
    route.fulfill({
      status: 200,
      json: {
        data: {
          fund_code: SYMBOL,
          name: NAME,
          full_name: "永赢北证50成份指数发起式证券投资基金",
          fund_type: "指数型-股票",
          fund_variety: "股票型",
          company: "永赢基金管理有限公司",
          unit_nav: 0.8234,
          nav_date: "2026-10-09",
          prev_unit_nav: 0.8201,
          prev_nav_date: "2026-10-08",
          change_pct: 0.402,
          scale: 12.34,
          create_time: "2022-03-15",
          risk_level: null,
          benchmark: "中证北证50成份指数收益率*95%+银行活期存款利率*5%",
          managers: [
            {
              mgr_code: "MGR0001",
              name: "测试经理",
              company: "永赢基金管理有限公司",
              appointment_date: "2022-03-15",
              is_classic: true
            }
          ],
          fee_rates: {
            fund_code: SYMBOL,
            currency: "CNY",
            purchase: [{ start_quota: 0, end_quota: 1000000, rate: 0.012 }],
            redeem: [{ start_day: 0, end_day: 7, rate: 0.015 }]
          },
          source: "天天基金"
        },
        message: "ok"
      }
    })
  );
  // #2029 卡 B：业绩与风险区块同样此前没打桩会落到兜底 404 → 走降级。
  // 补桩后 detail.vue 漏挂 ProductPerformanceSection 会让下面的断言变红（反向验证同卡 A）。
  await page.route("**/api/products/fund-performance/**", route =>
    route.fulfill({
      status: 200,
      json: {
        data: {
          fund_kind: "fund",
          applicable: true,
          basis: "acc_nav",
          acc_nav_caveat:
            "累计净值口径（分红不再投近似复权），非严格分红再投复权净值",
          intervals: [
            { key: "1w", label: "近1周", value: 1.23 },
            { key: "1m", label: "近1月", value: 3.45 },
            { key: "3m", label: "近3月", value: 6.78 },
            { key: "6m", label: "近6月", value: 9.01 },
            { key: "1y", label: "近1年", value: 12.34 },
            { key: "2y", label: "近2年", value: 18.56 },
            { key: "3y", label: "近3年", value: 22.78 },
            { key: "5y", label: "近5年", value: 35.9 },
            { key: "ytd", label: "今年以来", value: 8.12 },
            { key: "since", label: "成立以来", value: 45.67 }
          ],
          max_drawdown: -18.52,
          max_drawdown_basis: "fixed_3y",
          max_drawdown_window: "近3年",
          max_drawdown_as_of: "2026-10-09",
          volatility_1y: 16.6,
          as_of: "2026-10-09",
          source: "天天基金"
        },
        message: "ok"
      }
    })
  );
  // #2029 卡 C：行业配置 + 持仓明细共用一个端点，同样此前没打桩会落到兜底 404。
  // 打桩刻意做成**双 scheme + top10 口径**，这样下面两条断言才真的在验证
  // 「GICS 单列参考」与「前十大口径提示」这两个分支，而不是恰好路过的 happy path。
  await page.route("**/api/products/fund-holdings-detail/**", route =>
    route.fulfill({
      status: 200,
      json: {
        data: {
          fund_code: "110020",
          fund_name: "易方达消费行业股票",
          applicable: true,
          has_industry: true,
          has_holding: true,
          industries: [
            {
              scheme: "csrc",
              scheme_label: "证监会门类",
              is_primary: true,
              report_period: "2026Q2",
              report_date: "2026-06-30",
              total_ratio: 89.0,
              items: [
                {
                  industry_code: "C",
                  industry_name: "制造业",
                  ratio: 30.5
                },
                {
                  industry_code: "A",
                  industry_name: "金融业",
                  ratio: 22.25
                },
                {
                  industry_code: "I",
                  industry_name: "信息传输",
                  ratio: null
                }
              ]
            },
            {
              scheme: "gics",
              scheme_label: "GICS 板块",
              is_primary: false,
              report_period: "2025Q4",
              report_date: "2025-12-31",
              total_ratio: 12.0,
              items: [
                {
                  industry_code: "25",
                  industry_name: "非必需消费品",
                  ratio: 12.0
                }
              ]
            }
          ],
          // 环形图只含主口径（csrc）且与表格同口径
          industry_chart: [
            { name: "制造业", value: 30.5 },
            { name: "金融业", value: 22.25 }
          ],
          holdings: {
            rows: [
              {
                rank: 1,
                stock_code: "600519",
                stock_name: "贵州茅台",
                ratio: 9.87,
                shares: 1234.5,
                market_value: 98765.43
              },
              {
                rank: 2,
                stock_code: "000858",
                stock_name: null,
                ratio: 7.65,
                shares: null,
                market_value: null
              }
            ],
            basis: "top10",
            basis_label: "前十大（季报）",
            report_period: "2026Q2",
            report_date: "2026-06-30",
            shown_total_ratio: 17.52
          },
          as_of: "2026-06-30",
          source: "东方财富"
        },
        message: "ok"
      }
    })
  );
  await page.route("**/api/positions/**", route =>
    // 注意：**不能**套信封包装器——positions 的响应体本身就是
    // `{ data: [...], total, page, per_page }`，再包一层会让组件拿到对象而非数组
    // （症状：整块显示「当前产品暂无持仓记录。」，第一版就是这么错的）
    // 两条不同 ledger 的持仓，用于走通 #2012 的「多账户」分支（单账户会进指标网格）
    route.fulfill({
      status: 200,
      json: {
        data: [position(1, 2, "支付宝"), position(2, 3, "招商银行")],
        total: 2,
        page: 1,
        per_page: 100,
        message: "ok"
      }
    })
  );
}

/** 打桩持仓行：只有 id / ledger_id / account_name 会变，其余口径字段恒定 */
function position(id: number, ledgerId: number, accountName: string) {
  return {
    id,
    symbol: SYMBOL,
    name: NAME,
    market: "CN_A",
    type: "fund",
    account_name: accountName,
    quantity: 29551.43,
    avg_price: 10000,
    currency: "CNY",
    current_price: 7600,
    trade_date: "2026-10-08",
    notes: null,
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
    ledger_id: ledgerId,
    market_value: 22532.97,
    pnl: -18.5
  };
}

test.describe("产品详情页去重（页头承担识别信息）", () => {
  // 冷启动时 vite 首次编译整套依赖可能超过默认 60s
  test.setTimeout(180_000);

  test.beforeEach(async ({ context, baseURL, page }) => {
    await injectSupabaseSession(context, baseURL!);
    await stubProductApis(page);
  });

  test("识别卡不再复述产品名与品类（识别信息只在页头出现）", async ({
    page
  }) => {
    await page.goto(`/#/fund/${SYMBOL}`);
    await expect(page.getByRole("heading", { level: 1 })).toContainText(NAME, {
      timeout: 60_000
    });
    // 修复前：识别卡里还有一个 h2 名称 + 类型徽章，与页头一字不差地重复
    const hero = page.locator(".product-detail__hero");
    await expect(hero).toBeVisible();
    expect(await countVisibleIn(hero, NAME)).toBe(0);
    expect(await countVisibleIn(hero, "基金")).toBe(0);
  });

  test("识别卡仍展示代码等事实项（去重不等于删信息）", async ({ page }) => {
    await page.goto(`/#/fund/${SYMBOL}`);
    const hero = page.locator(".product-detail__hero");
    await expect(hero).toBeVisible({ timeout: 60_000 });
    await expect(hero.getByText(SYMBOL)).toBeVisible();
    await expect(hero.getByText("已关注")).toBeVisible();
    await expect(hero.getByText("已持有")).toBeVisible();
  });

  test("整页产品名只出现 1 次，持仓表头整块只出 1 次", async ({ page }) => {
    await page.goto(`/#/fund/${SYMBOL}`);
    // 等持仓区块渲染完（打桩里有两条不同账户的持仓 → 走多账户表格分支）
    const table = page.locator(".product-position__table");
    await expect(table).toBeVisible({ timeout: 60_000 });

    // 页头 h1 = 唯一一次；识别卡与持仓行里都不再重复
    const bodyText = await page.locator("body").innerText();
    expect(bodyText.split(NAME).length - 1).toBe(1);

    // #2012 之后整块只有**一个** thead（旧版每个渠道块各带一整套表头），
    // 且首列是「账户」而不是「产品」
    await expect(table.locator("thead")).toHaveCount(1);
    await expect(table.locator("thead th").first()).toHaveText("账户");
    // ⚠️ 这条断言必须**限定在 positions 表内**，不能全页 getByText：
    // #2314（1c5647d34，详情页设计审计项修复）把**另一张**表——持仓明细
    // `.holding-section__table`——的「代码 / 名称」两列**有意合并成一个「产品」列**
    // （ProductHoldingSection.vue:138，代码注释写明「复用全站 ProductDisplay」）。
    // 全页扫会把那张表的产品列表头一起算进来 ⇒ 期望 0 实得 1。
    // 原不变式「positions 区块内不出现『产品』字样」本身仍然成立，只是作用域要收窄。
    await expect(table.getByText("产品", { exact: true })).toHaveCount(0);

    // 行标签是账户名——产品名不再以任何形式出现在持仓区块里
    await expect(table.locator("tbody .product-position__account")).toHaveText([
      "支付宝",
      "招商银行"
    ]);
  });
});

/**
 * #2029 回归网：基金资料区块必须真的渲染。
 *
 * 这条不是「多测一点」——修复前 detail.vue 漏了 ProductFundSection 的 import，
 * Vue 只发一条「Failed to resolve component」warning 就静默不渲染，
 * 基金详情页从上线起就没有基金资料区块，而当时的用例只断言「识别卡不复述产品名」，
 * 恰好完全绕开了这个区块。
 *
 * 反向验证：把 detail.vue 的 import 行删掉，本用例必须红。
 */
test.describe("基金资料区块确实挂载（#2029）", () => {
  test.setTimeout(180_000);

  test.beforeEach(async ({ context, baseURL, page }) => {
    await injectSupabaseSession(context, baseURL!);
    await stubProductApis(page);
  });

  test("基金详情页渲染基金资料区块并带出资料字段", async ({ page }) => {
    await page.goto(`/#/fund/${SYMBOL}`);
    const section = page.locator(".fund-section");
    await expect(section).toBeVisible({ timeout: 60_000 });

    // 区块标题 + 首屏净值与资料字段（打桩里有值，故不该出现降级文案）
    await expect(
      section.getByRole("heading", { name: "基金资料" })
    ).toBeVisible();
    await expect(section.getByText("0.8234")).toBeVisible();
    await expect(section.getByText("永赢基金管理有限公司")).toBeVisible();
    await expect(section.getByText("指数型-股票")).toBeVisible();

    // 降级文案不应出现——有值的数据被打桩喂到了
    await expect(section).not.toContainText("暂无可展示的基金资料");
  });

  test("区块脚注标注数据来源而非表名", async ({ page }) => {
    await page.goto(`/#/fund/${SYMBOL}`);
    const section = page.locator(".fund-section");
    await expect(section).toBeVisible({ timeout: 60_000 });
    // #1969 起脚注给站点名（天天基金），不给 daily_worth 这类表名
    await expect(section.getByText("天天基金")).toBeVisible();
    await expect(section).not.toContainText("daily_worth");
  });
});

/**
 * #2029 卡 B 回归网：业绩与风险区块必须真的渲染。
 *
 * 这条与卡 A 同源——修复前基金资料区块因漏 import 而静默不渲染，本卡若也漏挂
 * `<ProductPerformanceSection>`，Vue 只会发一条 warning 不报错，详情页就少了整块业绩数据。
 *
 * 反向验证：把 detail.vue 里 <ProductPerformanceSection> 的挂载删掉，本用例必须红。
 */
test.describe("业绩与风险区块确实挂载（#2029 卡 B）", () => {
  test.setTimeout(180_000);

  test.beforeEach(async ({ context, baseURL, page }) => {
    await injectSupabaseSession(context, baseURL!);
    await stubProductApis(page);
  });

  test("基金详情页渲染业绩与风险区块并带出指标", async ({ page }) => {
    await page.goto(`/#/fund/${SYMBOL}`);
    const section = page.locator(".performance-section");
    await expect(section).toBeVisible({ timeout: 60_000 });

    // 区块标题
    await expect(
      section.getByRole("heading", { name: "业绩与风险" })
    ).toBeVisible();

    // 区间收益切面带出标签（成立以来有打桩值）
    await expect(section.getByText("成立以来")).toBeVisible();

    // 风险指标：最大回撤为纯文本数值（非 RiseFallText），可直接断言
    await expect(section.getByText("最大回撤（近3年）")).toBeVisible();
    await expect(section.getByText("-18.52%")).toBeVisible();

    // 脚注给站点名而非表名
    await expect(section.getByText("天天基金")).toBeVisible();
    await expect(section).not.toContainText("daily_worth");

    // 有数据时不应出现降级文案
    await expect(section).not.toContainText("暂无可展示的业绩数据");
  });
});

/**
 * #2029 卡 C 回归网：行业配置 + 持仓明细两张卡必须真的渲染，且遵守两条硬口径。
 *
 * 与卡 A / 卡 B 同源：漏挂组件 Vue 只发 warning 不报错，详情页就少一整块数据。
 * 这里额外钉**两条容易被改坏的分支**：
 * - GICS 单列参考且标注「不可相加」（csrc/gics 跨体系相加会得出荒谬结论）；
 * - `top10` 口径必须出「不代表全部持仓」的提示（否则用户会把「只披露10 只」
 *   误读成「只买了 10 只」）。
 *
 * 反向验证：删掉 detail.vue 里 <ProductHoldingsSections> 的挂载 → 本用例红。
 */
test.describe("行业配置与持仓明细区块确实挂载（#2029 卡 C）", () => {
  test.setTimeout(180_000);

  test.beforeEach(async ({ context, baseURL, page }) => {
    await injectSupabaseSession(context, baseURL!);
    await stubProductApis(page);
  });

  test("渲染行业配置卡并把 GICS 单列为参考", async ({ page }) => {
    await page.goto(`/#/fund/${SYMBOL}`);
    const section = page.locator(".industry-section");
    await expect(section).toBeVisible({ timeout: 60_000 });
    await expect(
      section.getByRole("heading", { name: "行业配置" })
    ).toBeVisible();

    // 主口径表格带出行业与占比
    // 体系名在 SectionHeader 的 #action 区（#2112 起），且**必须用容器精确定位**：
    // GICS 参考提示里插了同一串字（「该分类体系与上方证监会门类不可相加」），
    // 直接 getByText 会命中 2 个元素触发 strict mode 违规。
    await expect(section.locator(".industry-section__scheme")).toHaveText(
      "证监会门类"
    );
    await expect(section.getByText("制造业")).toBeVisible();
    await expect(section.getByText("30.50%")).toBeVisible();
    // 缺失占比降级为「—」，不按 0 展示
    await expect(section.getByText("信息传输")).toBeVisible();

    // 非主口径单列，且明确标注不可相加
    await expect(section.getByText("GICS 板块（参考）")).toBeVisible();
    await expect(section.getByText("不可相加")).toBeVisible();

    // 脚注给站点名（东财，非净值链路的天天基金）
    await expect(section.getByText("东方财富")).toBeVisible();
    await expect(section).not.toContainText("暂无行业配置数据");
  });

  test("渲染持仓明细卡并标注 top10 口径", async ({ page }) => {
    await page.goto(`/#/fund/${SYMBOL}`);
    const section = page.locator(".holding-section");
    await expect(section).toBeVisible({ timeout: 60_000 });
    await expect(
      section.getByRole("heading", { name: "持仓明细" })
    ).toBeVisible();

    // 表格行带出代码 / 名称 / 占比
    await expect(section.getByText("600519")).toBeVisible();
    await expect(section.getByText("贵州茅台")).toBeVisible();
    await expect(section.getByText("9.87%")).toBeVisible();

    // 口径标注（top10） + 「不代表全部持仓」提示
    await expect(section.getByText("前十大（季报）")).toBeVisible();
    await expect(section.getByText("不代表该基金的全部持仓")).toBeVisible();

    // 缺失字段降级（stock_name / shares / market_value 均为 null）
    // ⚠️ 必须同时锁定「类名」与「行」两层：
    // ① 类名：#2314 让持仓明细复用 ProductDisplay 的 compact 模式，
    //    `.product-name` 渲染 `name || symbol || "--"`（ProductDisplay:14-16），
    //    同时 `.product-code-compact` 渲染 `# ${symbol}`（:27-33）；名称为空时两者
    //    文本都是 "000858" ⇒ 只限定类名仍会命中 2 个节点（strict mode 报错）。
    // ② 行：持仓表有 2 行，两行都有 .product-name ⇒ 还得按文本筛出那一行。
    // （另：旧注释写「降级『—』」与实际不符——名称缺失时实际**回落为代码**而非破折号。）
    await expect(
      section.locator(".holding-section__product .product-name", {
        hasText: "000858"
      })
    ).toHaveText("000858");

    await expect(section).not.toContainText("暂无持仓明细数据");

    // 短表格不该出现展开按钮——「展开全部 2 只」这种按钮是纯噪声。
    // PREVIEW_SIZE 若被改成 0 / 1，这里会转红。
    await expect(section.getByRole("button")).toHaveCount(0);
  });
});

/**
 * 持仓明细渐进披露回归网。
 *
 * 库内实测（2026-10-12）：`fund_holdings` 最新报告期共 113 只基金，其中
 * **112 只是 `full` 口径、中位 67 行、最大 100 行**，全部超过预览行数——
 * 把整张表堆在详情页是**主流形态而非偶发**，会把走势 / 业绩挤出几屏之外。
 * 故默认只渲染前 10 行，其余靠按钮渐进披露。
 *
 * 钉三条容易被改坏的点：
 * 1. 超量才出按钮（短表格不出）——否则到处是「展开全部 2 只」这类噪声；
 * 2. 「所示合计」跟着**可见行**走——折叠时显示全量合计会让标签变成假的；
 * 3. ⚠️「不代表全部持仓」只属于 `basis=top10`。`full` 口径是「数据全但表格长」，
 *    折叠**不得**复用该警告，否则用户会以为全量披露的基金也只披露了十只。
 *
 * 反向验证：把 `PREVIEW_SIZE` 调大（或去掉 `needToggle`）→ 第 1 条断言转红；
 * 把 tfoot 改回直接用 `holdings.shown_total_ratio` → 第 2 条断言转红。
 */
test.describe("持仓明细渐进披露（#1968 子卡）", () => {
  test.setTimeout(180_000);

  // 15 行 `full` 口径持仓：每行 1.5%，故前 10 行合计 15.00%、全量 22.50%
  const MANY_ROWS = Array.from({ length: 15 }, (_, i) => ({
    rank: i + 1,
    stock_code: `6000${i}`,
    stock_name: `测试重仓${i + 1}`,
    ratio: 1.5,
    shares: 100 + i,
    market_value: 1000 + i
  }));

  test.beforeEach(async ({ context, baseURL, page }) => {
    await injectSupabaseSession(context, baseURL!);
    await stubProductApis(page);
    // 覆盖 stubProductApis 里的 2 行 top10 打桩（后注册的 route 优先匹配）
    await page.route("**/api/products/fund-holdings-detail/**", route =>
      route.fulfill({
        status: 200,
        json: {
          data: {
            fund_code: SYMBOL,
            fund_name: NAME,
            applicable: true,
            has_industry: false,
            has_holding: true,
            industries: [],
            holdings: {
              rows: MANY_ROWS,
              basis: "full",
              basis_label: "全量披露（半年报/年报）",
              report_period: "2026H1",
              report_date: "2026-06-30",
              shown_total_ratio: 22.5
            },
            as_of: "2026-06-30",
            source: "东方财富"
          },
          message: "ok"
        }
      })
    );
  });

  test("超过预览行数时默认折叠，展开后才渲染全量", async ({ page }) => {
    await page.goto(`/#/fund/${SYMBOL}`);
    const section = page.locator(".holding-section");
    await expect(section).toBeVisible({ timeout: 60_000 });

    // 默认只渲染前 10 行
    await expect(section.locator("tbody tr")).toHaveCount(10);

    const more = section.getByRole("button", { name: /展开全部 15 只/ });
    await expect(more).toBeVisible();
    // 折叠态也带出全量合计：不必为了看一眼总占比先展开上百行
    await expect(more).toContainText("22.50%");
    // 「所示合计」必须等于可见行之和，而不是全量合计
    await expect(section.locator("tfoot")).toContainText("15.00%");

    await more.click();
    await expect(section.locator("tbody tr")).toHaveCount(15);
    // 展开后合计跟着可见行走：10 行 15.00% → 15 行 22.50%
    await expect(section.locator("tfoot")).toContainText("22.50%");
    await expect(section.getByRole("button", { name: "收起" })).toBeVisible();
  });

  test("full 口径折叠不误出 top10 警告", async ({ page }) => {
    await page.goto(`/#/fund/${SYMBOL}`);
    const section = page.locator(".holding-section");
    await expect(section).toBeVisible({ timeout: 60_000 });

    await expect(section.getByText("全量披露（半年报/年报）")).toBeVisible();
    await expect(section).not.toContainText("不代表该基金的全部持仓");
  });
});

/** 计数限定在某个容器内（识别卡），避免被页头 / 持仓区块的同名文本干扰 */
function countVisibleIn(locator: ReturnType<Page["locator"]>, text: string) {
  return locator.evaluate((el, name) => {
    const body = (el as HTMLElement).innerText ?? "";
    return body.split(name).length - 1;
  }, text);
}
