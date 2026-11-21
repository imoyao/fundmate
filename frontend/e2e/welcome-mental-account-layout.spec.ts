import { expect, test, type Page } from "@playwright/test";
import { injectSupabaseSession } from "./support/session";

/**
 * 首页「心理账户」卡比例回归（#3115 后续）。
 *
 * 这张卡此前和左栏（财务晴雨表 + 近期动态）同高：右栏容器 `h-full`、
 * 卡片 `flex-1 h-full`、内容区 `justify-between`。五档只有 5 行、脚注两段，
 * 内容约 330px；左栏却有 650px+ ⇒ 图例与脚注之间被顶出一大块空白
 * （1440 宽实测 325px），卡片成了 357×657 的半空竖长板。
 *
 * 判据不写「卡片必须多高」——那会随左栏内容变化；只钉一件事：
 * **图例底部到脚注顶部之间不应出现超过一个常规间距的空白**。
 * 旧实现把两段推到上下两端（325px），新实现是一个 `gap-4`（16px）。
 */

test.use({ viewport: { width: 1440, height: 1000 } });

const DIST = {
  data: {
    type_distribution: [],
    allocation_distribution: [{ name: "长期增值", value: 605275.68 }],
    market_distribution: [],
    account_distribution: [],
    category_distribution: [],
    liability_distribution: [],
    total_assets: 3305951.68,
    total_liabilities: 1760000,
    net_worth: 1545951.68,
    positions_total_mv: 605275.68,
    allocation_scope: {
      denominator: 605276,
      excluded_total: 2705687,
      excluded: [
        { name: "固定资产", value: 2200091 },
        { name: "账外类现金", value: 445596 },
        { name: "应收款", value: 50000 }
      ],
      liabilities_total: 1760000,
      buckets: [
        { key: "liquid", label: "活钱", value: 0 },
        { key: "stable", label: "稳健底仓", value: 0 },
        { key: "growth", label: "长期增值", value: 605275.68 },
        { key: "speculative", label: "高风险博弈", value: 0 },
        { key: "protection", label: "保险保障", value: 0 }
      ]
    }
  },
  message: "ok"
};

async function mockApis(page: Page) {
  // Playwright 的 route 后注册者优先 ⇒ 具体桩必须写在兜底 404 之后
  await page.route(/^https?:\/\/[^/]+\/api\//, route =>
    route.fulfill({ status: 404, json: { data: null, message: "e2e 未打桩" } })
  );
  await page.route(/\/api\/summary\/distributions\//, route =>
    route.fulfill({ status: 200, json: DIST })
  );
}

test.describe("首页心理账户卡比例", () => {
  test.setTimeout(180_000);

  test.beforeEach(async ({ context, baseURL }) => {
    await injectSupabaseSession(context, baseURL!);
  });

  test("图例与脚注之间没有大块空白（卡片高度按内容走）", async ({ page }) => {
    await mockApis(page);
    await page.goto("/#/welcome");

    const card = page
      .locator(".card-block")
      .filter({ has: page.locator(".mental-account__bar") });
    await expect(card).toHaveCount(1, { timeout: 90_000 });
    await expect(card.locator(".mental-account__foot")).toBeVisible();

    const gap = await page.evaluate(() => {
      const legend = document.querySelector(".mental-account__legend")!;
      const foot = document.querySelector(".mental-account__foot")!;
      const legendBottom = legend.getBoundingClientRect().bottom;
      const footTop = foot.getBoundingClientRect().top;
      return Math.round(footTop - legendBottom);
    });

    // 正常相邻 = gap-4（16px）。阈值放到 48 是给行高/字体差异留余量，
    // 旧实现的 325px 空白必红。
    expect(gap).toBeLessThanOrEqual(48);
  });
});
