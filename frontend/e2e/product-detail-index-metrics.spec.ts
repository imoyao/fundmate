import { expect, test } from "@playwright/test";
import { injectSupabaseSession } from "./support/session";

/**
 * 详情页指数区块信息增强回归网（#2278：阶段性收益 + 十大权重 + 快照字段）。
 *
 * 钉四条不变式：
 * 1. **快照字段入事实格**：发布日期 / 样本数 / 加权方式 / 币种来自 index-profile
 *    的同一份数据；官网未填的键（样本数 / 加权方式）逐字段降级「—」而非留白；
 * 2. **收益表诚实渲染**：有值窗口带符号显示（+5.12%），历史不足的窗口显示「—」
 *    （不编数是本卡验收红线），脚注带数据日期与来源；
 * 3. **权重表 + 月频口径标注**：行渲染 + 前十大合计集中度 + 「月频」脚注——
 *    权重与日频行情不同源，口径标注是验收硬要求；
 * 4. **各区块独立降级**：收益接口失败 → 收益块显示空态文案，权重块照常渲染，
 *    互不拖垮，详情页可用。
 *
 * 接口全部 page.route 打桩，不依赖后端（docs/dev/frontend-e2e.md §7）。
 *
 * 反向验证：删掉 ProductIndexSection 里 <ProductIndexReturns>/<ProductIndexWeights>
 * 挂载 → 用例 1/2 红；把 ProductIndexReturns 的 null 分支改回硬编码 0 → 「—」断言红；
 * 去掉快照字段的逐字段降级（直接渲染原值）→ 「—」断言红。
 */

const NAME = "光伏产业指数";
const SYMBOL = "931151";

async function stubIndexApis(
  page: import("@playwright/test").Page,
  opts?: { returnsStatus?: number }
) {
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
        data: { asset_type: { index: "指数" }, market: { CN_A: "A股" } },
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
          asset_type: "index",
          market: "CN_A",
          venue: null,
          display_name: NAME,
          in_watchlist: false,
          has_position: false,
          source: "catalog"
        },
        message: "ok"
      }
    })
  );
  await page.route("**/api/products/index-profile/**", route =>
    route.fulfill({
      status: 200,
      json: {
        data: {
          index_code: SYMBOL,
          name: NAME,
          publisher_label: "中证指数公司",
          is_core: false,
          description: "中证光伏产业指数选取不超过50只光伏产业链代表性证券。",
          pe: 28.51,
          dividend_yield: 0.42,
          valuation_date: "2026-10-16",
          pe_percentile: 35.4,
          percentile_metric: "滚动市盈率（乐咕乐股月频）",
          percentile_date: "2026-09-30",
          publish_date: "2019-04-22",
          cons_number: null,
          weighting_type: null,
          currency: "人民币"
        },
        message: "ok"
      }
    })
  );
  await page.route("**/api/products/index-returns/**", route => {
    if (opts?.returnsStatus) {
      return route.fulfill({
        status: opts.returnsStatus,
        json: { data: null }
      });
    }
    return route.fulfill({
      status: 200,
      json: {
        data: {
          index_code: SYMBOL,
          as_of: "2026-10-16",
          source: "csindex",
          returns: {
            m1: 5.12,
            m3: null,
            ytd: 18.3,
            y1: 25.1,
            y2: null,
            y3: 40.2
          },
          volatility_y1: 28.45
        },
        message: "ok"
      }
    });
  });
  await page.route("**/api/products/index-weights/**", route =>
    route.fulfill({
      status: 200,
      json: {
        data: {
          index_code: SYMBOL,
          as_of: "2026-09-30",
          frequency: "monthly",
          constituent_count: 50,
          total_weight: 100,
          top10_weight: 55.12,
          top10: [
            {
              code: "601012",
              name: "隆基绿能",
              weight: 9.85,
              exchange: "上海证券交易所"
            },
            {
              code: "300274",
              name: "阳光电源",
              weight: 8.21,
              exchange: "深圳证券交易所"
            },
            {
              code: "000591",
              name: "太阳能",
              weight: 6.4,
              exchange: "深圳证券交易所"
            }
          ]
        },
        message: "ok"
      }
    })
  );
  await page.route("**/api/positions/**", route =>
    route.fulfill({
      status: 200,
      json: { data: [], total: 0, page: 1, per_page: 100, message: "ok" }
    })
  );
}

test.describe("详情页指数信息增强（#2278）", () => {
  test.setTimeout(120_000);

  test("快照字段 + 阶段性收益 + 十大权重全渲染", async ({
    context,
    baseURL,
    page
  }) => {
    await injectSupabaseSession(context, baseURL!);
    await stubIndexApis(page);
    await page.goto(`/#/index/${SYMBOL}`);

    // 快照字段：官网有值的键原样渲染，没填的键（样本数/加权方式）逐字段「—」
    const facts = page.locator(".index-section__facts");
    await expect(facts.getByText("发布日期")).toBeVisible();
    await expect(facts.getByText("2019-04-22")).toBeVisible();
    await expect(facts.getByText("样本数")).toBeVisible();
    await expect(facts.getByText("加权方式")).toBeVisible();
    await expect(facts.getByText("币种")).toBeVisible();
    await expect(facts.getByText("人民币")).toBeVisible();

    // 阶段性收益：正收益带 + 号，null 窗口显示「—」（不编数是验收红线）
    const returns = page.locator(".idx-returns");
    await expect(returns.getByText("阶段性收益")).toBeVisible();
    await expect(returns.getByText("+5.12%")).toBeVisible();
    await expect(returns.getByText("今年至今")).toBeVisible();
    // m3 / y2 两窗口 null → 恰好两个「—」（计数断言：多了是漏降级，少了是编数）
    await expect(returns.getByText("—")).toHaveCount(2);
    await expect(returns.getByText("28.45%")).toBeVisible(); // 年化波动率
    await expect(
      returns.getByText("行情截至 2026-10-16 · 来源：中证指数官网")
    ).toBeVisible();

    // 十大权重：行渲染 + 集中度 + 月频口径标注
    const weights = page.locator(".idx-weights");
    await expect(weights.getByText("十大权重股")).toBeVisible();
    await expect(weights.getByText("隆基绿能")).toBeVisible();
    await expect(weights.getByText("阳光电源")).toBeVisible();
    await expect(weights.getByText("9.850%")).toBeVisible();
    await expect(
      weights.getByText("前十大合计 55.12% · 成分股共 50 只")
    ).toBeVisible();
    await expect(
      weights.getByText("权重截至 2026-09-30（月频口径，来自中证指数官网）")
    ).toBeVisible();
  });

  test("收益接口失败独立降级：收益块空态，权重块照常渲染", async ({
    context,
    baseURL,
    page
  }) => {
    await injectSupabaseSession(context, baseURL!);
    await stubIndexApis(page, { returnsStatus: 500 });
    await page.goto(`/#/index/${SYMBOL}`);

    const returns = page.locator(".idx-returns");
    await expect(returns.getByText("暂无可展示的收益数据")).toBeVisible();

    // 独立降级：收益挂了不拖垮权重（断网/接口失败是验收项）
    const weights = page.locator(".idx-weights");
    await expect(weights.getByText("十大权重股")).toBeVisible();
    await expect(weights.getByText("隆基绿能")).toBeVisible();

    // 快照字段不受影响（同一张指数卡内的另一组数据源）
    await expect(
      page.locator(".index-section__facts").getByText("2019-04-22")
    ).toBeVisible();
  });
});
