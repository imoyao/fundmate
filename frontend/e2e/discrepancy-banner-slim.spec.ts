import { expect, test, type Page } from "@playwright/test";
import { injectSupabaseSession } from "./support/session";

/**
 * #980 批 B8 回归网：`DiscrepancyBanner` 拆分后的接线（407 → 240 行）。
 *
 * 取数、家庭级 dismiss、路由返回刷新搬进 `useDiscrepancyBanner.ts`（19 例单测），
 * 明细行搬进 `DiscrepancyList.vue`。这里钉的是**只有真渲染才暴露**的三件事：
 *
 * ① `v-if="routeAllowed && !loading && !dismissed && count > 0"` 这串合取——
 *    拆 composable 时最容易把 `routeAllowed` 或 `loading` 漏掉，症状是「工作台页
 *    自己又挂一条重复提醒」或「首屏闪一下空横幅」。
 * ② 条数口径：只算域 B。把域 A 混进来会让横幅数字与工作台「待裁决差异」对不上。
 * ③ 收起/展开的双向切换：`hiddenCount > 0` 与 `count > COLLAPSED_LIMIT` 是两条
 *    互斥分支，接错一条就出现「展开全部 6 项」点了没反应或永远不出现「收起」。
 *
 * ⚠️ 桩的路径**不带** `/api` 前缀：`api/reconciliation.ts` 里写的是
 * `/reconciliation/discrepancies/`，靠 vite dev 代理转发（同 reconcile-workbench-head）。
 * 只 match `/api/` 的话请求会漏到代理上，页面表现是「横幅不出现」，且不报错。
 */

const DISCREPANCY_URL = /\/reconciliation\/discrepancies/;

/** 本地日期字符串（后端那种带微秒的尾巴，前端只取前 10 位） */
function isoDaysAgo(days: number): string {
  const d = new Date();
  d.setDate(d.getDate() - days);
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T06:06:39.184874`;
}

function row(
  id: number,
  domain: string,
  symbol: string,
  daysAgo: number
): Record<string, unknown> {
  return {
    id,
    domain,
    symbol,
    discrepancy_type: "quantity",
    status: "pending",
    diff: 1000,
    first_detected_at: isoDaysAgo(daysAgo)
  };
}

/** 6 条域 B（最久 30 天）+ 1 条域 A（999 天，若泄漏进横幅必然抢占第一行） */
const ROWS = [
  row(1, "B", "600519", 30),
  row(2, "B", "000001", 5),
  row(3, "B", "110011", 4),
  row(4, "B", "161725", 3),
  row(5, "B", "512880", 2),
  row(6, "B", "002594", 1),
  row(7, "A", "LEAK-A", 999)
];

async function mockApis(page: Page) {
  await page.route(/^https?:\/\/[^/]+\/api\//, route =>
    route.fulfill({ status: 404, json: { data: null, message: "e2e 未打桩" } })
  );
  // 后注册先匹配：具体桩放最后
  await page.route(DISCREPANCY_URL, route =>
    route.fulfill({ json: { data: ROWS, message: "" } })
  );
}

test.describe("对账差异横幅拆分后回归（#980 批 B8）", () => {
  test.setTimeout(180_000);

  test.beforeEach(async ({ context, baseURL }) => {
    await injectSupabaseSession(context, baseURL!);
  });

  test("只算域 B 且收起态 5 行：条数、最久天数、第一行都收紧", async ({
    page
  }) => {
    await mockApis(page);
    await page.goto("/#/panorama");

    // 布局两分支互斥，只该出现一条
    const banner = page.locator(".recon-banner");
    await expect(banner).toHaveCount(1, { timeout: 90_000 });
    await expect(banner).toBeVisible();

    // 6 条域 B（域 A 那条不算）
    await expect(banner.locator(".recon-banner__count")).toHaveText("6");
    await expect(banner.locator(".recon-banner__stalest")).toContainText(
      "最久一条已挂 30 天"
    );

    // 收起态最多 5 行，最久那条在第一位
    const items = banner.locator(".recon-banner__item");
    await expect(items).toHaveCount(5);
    await expect(items.first()).toContainText("600519");
    await expect(items.first()).toContainText("30 天前发现");
    // 域 A 绝不能出现在横幅里
    await expect(banner).not.toContainText("LEAK-A");
    await expect(banner.locator(".recon-banner__link")).toHaveText(
      "展开全部 6 项"
    );
  });

  test("展开 / 收起双向切换", async ({ page }) => {
    await mockApis(page);
    await page.goto("/#/panorama");

    const banner = page.locator(".recon-banner");
    await expect(banner).toBeVisible({ timeout: 90_000 });

    await banner.locator(".recon-banner__link").click();
    await expect(banner.locator(".recon-banner__item")).toHaveCount(6);
    await expect(banner.locator(".recon-banner__link")).toHaveText(
      "收起，仅看前 5 项"
    );

    await banner.locator(".recon-banner__link").click();
    await expect(banner.locator(".recon-banner__item")).toHaveCount(5);
    await expect(banner.locator(".recon-banner__link")).toHaveText(
      "展开全部 6 项"
    );
  });

  test("关闭后本次会话不再出现（含刷新）", async ({ page }) => {
    await mockApis(page);
    await page.goto("/#/panorama");

    const banner = page.locator(".recon-banner");
    await expect(banner).toBeVisible({ timeout: 90_000 });

    await page
      .getByRole("button", { name: "本次会话不再提示" })
      .first()
      .click();
    await expect(banner).toHaveCount(0);

    const keys = await page.evaluate(() =>
      Object.keys(window.sessionStorage).filter(k =>
        k.startsWith("recon_pending_banner_dismissed")
      )
    );
    expect(keys.length).toBe(1);

    await page.reload();
    await expect(page.locator(".recon-banner")).toHaveCount(0, {
      timeout: 90_000
    });
  });

  test("进工作台后站外提醒消失，且落地的是工作台本身（routeAllowed + goToWorkbench）", async ({
    page
  }) => {
    await mockApis(page);
    await page.goto("/#/panorama");

    const banner = page.locator(".recon-banner");
    await expect(banner).toBeVisible({ timeout: 90_000 });

    // 走真实路径：横幅上的主按钮跳工作台并带 domain=B
    await banner.getByRole("button", { name: "去对账工作台处理" }).click();
    await expect(page).toHaveURL(/reconcile-workbench/);
    await expect(page).toHaveURL(/domain=B/);

    // 先证明工作台页**真的渲染了**，否则下面「横幅不见」可能只是白屏假绿
    // （初版就在 networkidle 后立刻断言 count=0，此时横幅尚未挂载，注掉
    //  routeAllowed 也不报红）
    await expect(
      page.getByText("统一处理 E账户对账", { exact: false })
    ).toBeVisible({ timeout: 90_000 });

    // 站外横幅必须消失；工作台页自带的域内提示仍在（两者是不同组件）
    await expect(banner).toHaveCount(0);
    await page.waitForTimeout(1500);
    await expect(page.locator(".recon-banner")).toHaveCount(0);
  });
});
