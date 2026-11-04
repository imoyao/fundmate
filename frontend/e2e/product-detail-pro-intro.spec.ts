import { expect, test, type Page } from "@playwright/test";
import { injectSupabaseSession } from "./support/session";

/**
 * 高级洞察 Pro 介绍卡两态回归网（#2523，用户 #2400 评审反馈）：
 *
 * 「下面的 4 个 Pro 介绍卡应仅在无权限时显示（引导开通，功能未实现），
 *  已开通则不需或换更好方式；4 张卡片是不是应该带个名字？锚点名称和总卡片
 *  名称对应。」
 *
 * 钉三条不变式：
 * 1. **未开通**（paywall_required=true，或状态位取不到）→ 四张介绍卡可见，
 *    且带组名（不再是浮块）；
 * 2. **已开通**（paywall_required=false）→ 介绍卡整组隐藏——模块内容就在上方，
 *    「Phase N 建设中」的排期语言不该留给付费用户；
 * 3. **组名与页内导航锚点名同名同序**（「高级洞察 Pro」）——锚点与总卡片名对应。
 *
 * 判据刻意取后端 `paywall_required` 而非 env 覆盖：env（VITE_PRO_PAYWALL_ENABLED）
 * 在 e2e 中恒 false（只关遮罩），若介绍卡可见性挂它，两态就永远测不到。
 *
 * 反向验证：
 * - showIntroGrid 改成恒 true → 用例 2 红（已开通仍见介绍卡）；
 * - showIntroGrid 改成恒 false → 用例 1 红（未开通没有引导卡）；
 * - 组名文案与 NAV_LABELS 改得不一样 → 用例 3 红（对应关系断裂）。
 */

const NAME = "永赢北证50成份指数发起C";
const SYMBOL = "023887";

async function stubApis(
  page: Page,
  opts: { paywallRequired: boolean; modulesLive?: boolean }
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
        data: {
          asset_type: { fund: "基金" },
          market: { CN_A: "A股" },
          venue: { OTC: "场外" }
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
          has_position: false,
          source: "position"
        },
        message: "ok"
      }
    })
  );
  await page.route("**/api/products/fund-profile/**", route =>
    route.fulfill({
      status: 200,
      json: {
        data: {
          fund_code: SYMBOL,
          name: NAME,
          fund_type: "指数型-股票",
          company: "永赢基金管理有限公司",
          unit_nav: 1.1,
          nav_date: "2026-10-21",
          change_pct: 0.5,
          source: "天天基金"
        },
        message: "ok"
      }
    })
  );
  await page.route("**/api/products/trend/**", route =>
    route.fulfill({
      status: 200,
      json: {
        data: { kind: "", values: [], dates: [], source: "", basis: "" },
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
          paywall_required: opts.paywallRequired,
          // 引导态（未开通）默认全未上线——正是「介绍卡广告的是什么」的
          // 真实场景；已开通态给三个上线，模拟内容态（组件各自降级不阻断区块）
          modules: opts.modulesLive
            ? {
                performance: { available: true, phase: 2 },
                risk: { available: true, phase: 2 },
                allocation: { available: true, phase: 3 },
                report: { available: false, phase: 4 }
              }
            : {
                performance: { available: false, phase: 2 },
                risk: { available: false, phase: 2 },
                allocation: { available: false, phase: 3 },
                report: { available: false, phase: 4 }
              }
        },
        message: "ok"
      }
    })
  );
}

test.describe("高级洞察 Pro 介绍卡两态（#2523）", () => {
  test.setTimeout(180_000);

  test.beforeEach(async ({ context, baseURL }) => {
    await injectSupabaseSession(context, baseURL!);
  });

  test("未开通：四张介绍卡 + 组名可见，且组名与导航锚点名同名", async ({
    page
  }) => {
    await stubApis(page, { paywallRequired: true });
    await page.goto(`/#/fund/${SYMBOL}`);
    const pro = page.locator("#nav-pro");
    await expect(pro).toBeVisible({ timeout: 60_000 });

    // 引导态：四张卡在（未上线模块的徽标也来自状态位）
    await expect(pro.locator(".pro-module")).toHaveCount(4);

    // 组名：卡片不再是浮块；与页内导航锚点名**逐字相同**
    const introName = pro.locator(".pro-section__intro-name");
    await expect(introName).toBeVisible();
    await expect(introName).toHaveText("高级洞察 Pro");
    const pill = page
      .locator(".page-nav")
      .locator(".page-nav__pill", { hasText: "高级洞察" });
    await expect(pill).toHaveText("高级洞察 Pro");
  });

  test("已开通：介绍卡整组隐藏（模块内容态，不向付费用户推销）", async ({
    page
  }) => {
    await stubApis(page, { paywallRequired: false, modulesLive: true });
    await page.goto(`/#/fund/${SYMBOL}`);
    const pro = page.locator("#nav-pro");
    await expect(pro).toBeVisible({ timeout: 60_000 });

    // 已开通：整组隐藏（网格 + 组名行都不在）
    await expect(pro.locator(".pro-section__grid")).toHaveCount(0);
    await expect(pro.locator(".pro-module")).toHaveCount(0);
    await expect(pro.locator(".pro-section__intro-name")).toHaveCount(0);

    // 区块本身还在（标题 + 已上线模块内容区）——隐藏的是介绍卡，不是区块
    await expect(pro.locator(".section-header__title")).toHaveText("高级洞察");
  });
});
