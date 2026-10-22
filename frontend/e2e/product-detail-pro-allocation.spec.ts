import { expect, test } from "@playwright/test";
import { injectSupabaseSession } from "./support/session";

/**
 * 详情页 Pro 模块三「资产配置与相关性」回归网（#994 Phase 2 接线；#2400 画法修订）。
 *
 * 钉五条不变式：
 * 1. **状态位驱动挂载**：`allocation.available=true` → 模块内容渲染（注意：phase
 *    仍是 3，挂载看的是 available 不是 phase；#2523 两态拆分后已开通态无介绍卡，
 *    徽标信号并入「模块进度」行）；
 * 2. **相关系数诚实渲染**：ρ 带符号 + |ρ| 降序；ρ ≥ 0.8 的标的必须触发
 *    「账面分散、风险未必」的总结句——这是本模块唯一真正要讲的话；
 * 3. **配色纪律（#2400 的核心修复）**：档位→颜色的映射被断言成**具体色值**。
 *    旧实现把文字级沙金 `--color-warning-ink` 当条形填充（= 褐色）、中间档用
 *    `--brand-ink`（亮色即红），层级反转。此处钉死四档实际取值：
 *    危险 #d4364a / 警示 #cc7000 / 反向 #6f8f9d / 弱关联 #e5ddd4。
 *    改色必然要改测试——这是有意的：色值是「语义」不是「样式」。
 * 4. **方向由几何表达（#2400）**：正相关条向右、负相关条向左（0 轴居中）。
 *    原实现一律向右，−0.42 与 +0.61 同观感、只差一个负号，属误导。
 * 5. **诚实披露 skipped_count**：因样本不足/无波动被跳过的持仓要讲出来，
 *    不让它悄悄从结论里消失；接口失败则整块降级。
 *
 * 另钉「名称用于阅读、编码用于记录」：每行都要露出 peer 的 symbol，加自选 /
 * 搜索时用户靠编码定位，不能只给名称。
 *
 * 接口全部 page.route 打桩，不依赖后端（docs/dev/frontend-e2e.md §7）。
 */

const NAME = "沪深300ETF联接A";
const SYMBOL = "000961";

const PRO_ALLOC_STUB = {
  symbol: SYMBOL,
  asset_type: "fund",
  window: "1Y",
  min_overlap: 60,
  available: true,
  reason: null,
  sample_days: 243,
  basis: "累计净值（分红不再投近似复权，缺失回退单位净值）",
  peers: [
    // 桩值自洽：|ρ| 降序（0.93 → 0.61 → −0.42），其中 2 只 ≥ 0.8 阈值以上只 1 只
    {
      symbol: "110020",
      name: "易方达沪深300ETF联接A",
      asset_type: "fund",
      correlation: 0.93,
      overlap_days: 240
    },
    {
      symbol: "000478",
      name: "建信中证500指数增强A",
      asset_type: "fund",
      correlation: 0.61,
      overlap_days: 238
    },
    {
      symbol: "000216",
      name: "华安易富黄金ETF联接A",
      asset_type: "fund",
      correlation: -0.42,
      overlap_days: 236
    }
  ],
  skipped_count: 2,
  high_correlation_count: 1,
  caveats: [
    "相关系数为历史区间统计值：市场剧烈波动时各类资产相关性会趋同，历史值不代表未来"
  ]
};

interface AllocOpts {
  allocStatus?: number;
  empty?: boolean;
}

async function stubProApis(
  page: import("@playwright/test").Page,
  opts?: AllocOpts
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
        data: { asset_type: { fund: "基金" }, market: { CN_A: "A股" } },
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
          venue: null,
          display_name: NAME,
          in_watchlist: false,
          has_position: true,
          source: "catalog"
        },
        message: "ok"
      }
    })
  );
  await page.route("**/api/products/pro/**", route =>
    route.fulfill({
      status: 200,
      json: {
        data: {
          symbol: SYMBOL,
          asset_type: "fund",
          pro_enabled: true,
          paywall_required: false,
          modules: {
            performance: { available: true, phase: 2 },
            risk: { available: true, phase: 2 },
            allocation: { available: true, phase: 3 },
            report: { available: false, phase: 4 }
          }
        },
        message: "ok"
      }
    })
  );
  // 兄弟模块也不打桩会让组件走失败分支，与「状态位已上线」的语义不符，故补空信封
  await page.route("**/api/products/pro-insight/**", route =>
    route.fulfill({
      status: 200,
      json: {
        data: {
          symbol: SYMBOL,
          asset_type: "fund",
          has_account_data: false,
          xirr: null,
          behavior: null
        },
        message: "ok"
      }
    })
  );
  await page.route("**/api/products/pro-risk/**", route =>
    route.fulfill({
      status: 200,
      json: {
        data: {
          symbol: SYMBOL,
          asset_type: "fund",
          bias: {
            available: false,
            bias: null,
            label: null,
            position: null,
            close: null,
            data_date: null,
            stale: false,
            reason: "e2e 未启用"
          },
          risk: {
            available: false,
            annual_volatility: null,
            var_95: null,
            sample_returns: 0,
            window: "1Y",
            as_of: null,
            basis: null,
            reason: "e2e 未启用",
            caveats: []
          },
          account: {
            has_position: false,
            position_value: 0,
            var_95_yuan: null
          }
        },
        message: "ok"
      }
    })
  );
  await page.route("**/api/products/pro-allocation/**", route => {
    if (opts?.allocStatus) {
      return route.fulfill({
        status: opts.allocStatus,
        json: { data: null }
      });
    }
    if (opts?.empty) {
      return route.fulfill({
        status: 200,
        json: {
          data: {
            symbol: SYMBOL,
            asset_type: "fund",
            window: "1Y",
            min_overlap: 60,
            available: false,
            reason: "家庭暂无其他持仓——持仓 ≥2 只才谈得上「是否真的分散」",
            sample_days: 243,
            basis: null,
            peers: [],
            skipped_count: 0,
            high_correlation_count: 0,
            caveats: []
          },
          message: "ok"
        }
      });
    }
    return route.fulfill({
      status: 200,
      json: { data: PRO_ALLOC_STUB, message: "ok" }
    });
  });
  await page.route("**/api/positions/**", route =>
    route.fulfill({
      status: 200,
      json: { data: [], total: 0, page: 1, per_page: 100, message: "ok" }
    })
  );
}

test.describe("详情页 Pro 模块三相关性（#994 Phase 2）", () => {
  test.setTimeout(120_000);

  test("状态位翻真 + 相关系数列表全渲染", async ({
    context,
    baseURL,
    page
  }) => {
    await injectSupabaseSession(context, baseURL!);
    await stubProApis(page);
    await page.goto(`/#/fund/${SYMBOL}`);

    const pro = page.locator(".pro-section");
    // 状态位驱动（#2523 两态拆分后）：已开通态无介绍卡，徽标信号并入「模块进度」行
    await expect(pro.locator(".pro-section__progress-text")).toHaveText(
      "已上线 3/4 · 智能报告与自动化 Phase 4 建设中"
    );

    const alloc = page.locator(".pro-alloc");

    // 总结句：这是本模块真正要让 user 看见的一句话
    await expect(
      alloc.getByText(/与你其余 3 只持仓中，有 1 只相关系数 ≥ 0.8/)
    ).toBeVisible();
    await expect(alloc.getByText(/账面分散了，风险未必/)).toBeVisible();

    // 相关系数：带符号保留 2 位，含负相关
    await expect(alloc.getByText("+0.93")).toBeVisible();
    await expect(alloc.getByText("+0.61")).toBeVisible();
    await expect(alloc.getByText("-0.42")).toBeVisible();

    // 定性描述已收进图例（#2400），行内不再逐行重复——避免每行都写一遍套话
    const legend = page.locator(".pro-alloc__legend");
    await expect(legend.getByText("风险集中 ρ ≥ 0.8")).toBeVisible();
    await expect(legend.getByText("明显联动")).toBeVisible();
    await expect(legend.getByText("反向对冲")).toBeVisible();
    await expect(legend.getByText("关联很弱")).toBeVisible();

    // 配色纪律（#2400）：四档钉死实际色值，见文件头说明
    const rows = alloc.locator(".pro-alloc__row");
    const barOf = (i: number) => rows.nth(i).locator(".pro-alloc__bar");
    await expect(barOf(0)).toHaveCSS("background-color", "rgb(212, 54, 74)"); // danger #d4364a
    await expect(barOf(1)).toHaveCSS("background-color", "rgb(204, 112, 0)"); // warn   #cc7000
    await expect(barOf(2)).toHaveCSS("background-color", "rgb(111, 143, 157)"); // hedge  #6f8f9d

    // 方向由几何表达：负相关的条落在 0 轴左侧（box.x 小于轨道中点）
    const track2 = await rows.nth(2).locator(".pro-alloc__track").boundingBox();
    const bar2 = await barOf(2).boundingBox();
    expect(track2).not.toBeNull();
    expect(bar2).not.toBeNull();
    expect(bar2!.x).toBeLessThan(track2!.x + track2!.width / 2);
    // 正相关在右侧
    const bar0 = await barOf(0).boundingBox();
    expect(bar0!.x).toBeGreaterThan(track2!.x + track2!.width / 2);

    // 名称用于阅读、编码用于记录（#2400）：每行都要露出 symbol
    await expect(alloc.getByText("易方达沪深300ETF联接A")).toBeVisible();
    await expect(alloc.locator(".pro-alloc__code").first()).toHaveText(
      "110020"
    );
    await expect(alloc.locator(".pro-alloc__code").nth(1)).toHaveText("000478");
    await expect(alloc.locator(".pro-alloc__code").nth(2)).toHaveText("000216");

    // 每行的配对样本数都要出现
    await expect(alloc.getByText("240 个同期交易日")).toBeVisible();

    // 诚实披露：2 只持仓因样本不足/无波动未纳入
    await expect(
      alloc.getByText(/另有 2 只持仓因同期交易日不足 60 天或无波动未纳入计算/)
    ).toBeVisible();

    // 脚注：口径 + 窗口样本 + caveat
    await expect(
      alloc.getByText(/累计净值.*近1Y窗口 · 基准序列 243 个交易日/)
    ).toBeVisible();
  });

  test("无其他持仓渲染引导文案（不编数字）", async ({
    context,
    baseURL,
    page
  }) => {
    await injectSupabaseSession(context, baseURL!);
    await stubProApis(page, { empty: true });
    await page.goto(`/#/fund/${SYMBOL}`);

    const alloc = page.locator(".pro-alloc");
    await expect(
      alloc.getByText("这里将展示「你是否真的分散了」")
    ).toBeVisible();
    // 后端原因要透出来，而不是笼统的「暂无数据」
    await expect(alloc.getByText(/持仓 ≥2 只才谈得上/)).toBeVisible();
    // 空态下不该有任何列表项
    await expect(alloc.locator(".pro-alloc__row")).toHaveCount(0);
  });

  test("pro-allocation 接口失败独立降级", async ({
    context,
    baseURL,
    page
  }) => {
    await injectSupabaseSession(context, baseURL!);
    await stubProApis(page, { allocStatus: 500 });
    await page.goto(`/#/fund/${SYMBOL}`);

    const alloc = page.locator(".pro-alloc");
    await expect(
      alloc.getByText("相关性暂时取不到，稍后再来看看")
    ).toBeVisible();

    // 独立降级：兄弟模块的状态位与内容不受影响。allocStatus=500 只打桩内容端点
    // pro-allocation，状态位 pro/** 仍回三模块已上线（report Phase 4）
    const pro = page.locator(".pro-section");
    await expect(pro.locator(".pro-section__progress-text")).toHaveText(
      "已上线 3/4 · 智能报告与自动化 Phase 4 建设中"
    );
  });
});
