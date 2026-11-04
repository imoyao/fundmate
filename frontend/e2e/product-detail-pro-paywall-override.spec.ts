import { expect, test, type Page } from "@playwright/test";
import { injectSupabaseSession } from "./support/session";

/**
 * 付费墙遮罩的 URL 运行时覆盖回归网（#2527）。
 *
 * 背景：遮罩开关原本只有 env `VITE_PRO_PAYWALL_ENABLED` 一个覆盖层，且是
 * **构建期**的——想预览「遮罩挂上」的样子必须改 env 重启 dev server；
 * e2e 里 env 恒 false（见 playwright.config.ts），遮罩这条交互**长期零覆盖**。
 *
 * 新增 URL 层 `?pro_paywall=0|1`（优先级 URL > env > 后端），本 spec 钉三件事：
 * 1. **URL "1" 压过 env="false"**：遮罩可见——这是运行时放行口的存在意义；
 * 2. **URL 只动遮罩，不动权益事实**（#2523 不变式的延伸）：介绍卡两态的判据
 *    永远是后端 `paywall_required`，挂 URL 也不行——
 *    - entitled + `?pro_paywall=1` → 遮罩在、介绍卡仍旧整组隐藏；
 *    - 未开通 + `?pro_paywall=0` → 遮罩不在、介绍卡仍旧四张在；
 * 3. **不认识的取值不猜**：`?pro_paywall=yes` 按没给处理，逐层落到 env（false）。
 *
 * 反向验证：
 * - paywallUrlFlag 不接进 resolvePaywallEnabled → 用例 1 红（遮罩不出现）；
 * - 组件把 entitled 改成也看 URL → 用例 2/3 的两态断言红；
 * - 未知取值按 "1" 处理 → 用例 4 红（遮罩错误出现）。
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

test.describe("付费墙遮罩 URL 运行时覆盖（#2527）", () => {
  test.setTimeout(180_000);

  test.beforeEach(async ({ context, baseURL }) => {
    await injectSupabaseSession(context, baseURL!);
  });

  test('URL "1" 压过 env=false：遮罩可见，且两态不被 URL 翻转', async ({
    page
  }) => {
    // 后端说已开通（无遮罩才是默认），env 也关着——只有 URL 能把它放出来
    await stubApis(page, { paywallRequired: false, modulesLive: true });
    await page.goto(`/#/fund/${SYMBOL}?pro_paywall=1`);
    const pro = page.locator(".pro-section");
    await expect(pro).toBeVisible({ timeout: 60_000 });

    // 遮罩：URL 覆盖生效（env=false 被压过）
    await expect(pro.locator(".pro-paywall")).toBeVisible();
    await expect(pro.getByText("解锁高级风险指标与交易行为分析")).toBeVisible();

    // 两态不变式：已开通家庭的介绍卡仍整组隐藏——URL 只动遮罩，不改权益事实
    await expect(pro.locator(".pro-section__grid")).toHaveCount(0);
    await expect(pro.locator(".pro-module")).toHaveCount(0);
  });

  test('未开通 + URL "0"：遮罩不在，介绍卡四张仍旧在', async ({ page }) => {
    await stubApis(page, { paywallRequired: true });
    await page.goto(`/#/fund/${SYMBOL}?pro_paywall=0`);
    const pro = page.locator(".pro-section");
    await expect(pro).toBeVisible({ timeout: 60_000 });

    // 遮罩不在（env 本就关着；URL "0" 同向，不制造新信息但钉住不翻转）
    await expect(pro.locator(".pro-paywall")).toHaveCount(0);

    // 两态不变式：未开通家庭的介绍卡仍在——URL "0" 没有把权益事实翻掉
    await expect(pro.locator(".pro-module")).toHaveCount(4);
    await expect(pro.locator(".pro-section__intro-name")).toBeVisible();
  });

  test("未知取值不猜：?pro_paywall=yes 按没给处理（落到 env=false，遮罩不出现）", async ({
    page
  }) => {
    await stubApis(page, { paywallRequired: false, modulesLive: true });
    await page.goto(`/#/fund/${SYMBOL}?pro_paywall=yes`);
    const pro = page.locator(".pro-section");
    await expect(pro).toBeVisible({ timeout: 60_000 });

    // 若把未知取值当 "1" 处理，这里会红
    await expect(pro.locator(".pro-paywall")).toHaveCount(0);
  });

  test("基线：不带参数时遮罩不在（env=false 的既有行为不回退）", async ({
    page
  }) => {
    await stubApis(page, { paywallRequired: true });
    await page.goto(`/#/fund/${SYMBOL}`);
    const pro = page.locator(".pro-section");
    await expect(pro).toBeVisible({ timeout: 60_000 });
    await expect(pro.locator(".pro-paywall")).toHaveCount(0);
  });
});
