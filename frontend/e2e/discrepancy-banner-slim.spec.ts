import { expect, test, type Page, type Route } from "@playwright/test";
import { injectSupabaseSession } from "./support/session";

/**
 * 全局「数据需要核对」提醒回归网（#2866 改版：三条横幅 → 一条紧凑提醒）。
 *
 * 钉住四件只有真渲染才暴露的事：
 * ① 三类问题（域 B 对账差异 / 域 F 交易记录信息不完整 / 域 G 缺账本流水）
 *    **合并成一条**，且只列有数据的类别；
 * ② 它是提醒 + 入口，不是详情页：不铺明细行、不提供「展开全部」、不放大段说明，
 *    高度必须真的紧凑（量 boundingBox，避免「换个不存在的类名数 0」这种恒真断言）；
 * ③ 点击「去查看」落到条目最多的那一类，且工作台页真渲染后站外提醒消失；
 * ④ 关闭后本次会话不再出现（含刷新）。另加一个三类全 0 的反向对照，证明
 *    「横幅出现」不是恒真。
 *
 * ⚠️ 桩路径必须与真实请求逐字一致：后端接口统一走 `/api/` 前缀，
 * vite 只代理 `/api`。漏写前缀会拿到 SPA 回退的 HTML（HTTP 200），
 * 页面表现是「横幅不出现」，且不报错（#2866 实测）。
 */

const DISCREPANCY_URL = /\/api\/reconciliation\/discrepancies/;
const DANGLING_URL = /\/api\/reconciliation\/dangling-refs\/$/;
const ORPHAN_URL = /\/api\/reconciliation\/orphan-ledger\/$/;

type PartKey = "B" | "F" | "G";

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
  symbol: string
): Record<string, unknown> {
  return {
    id,
    domain,
    symbol,
    discrepancy_type: "quantity",
    status: "pending",
    diff: 1000,
    first_detected_at: isoDaysAgo(30)
  };
}

/** 6 条域 B + 1 条域 A（域 A 不该被计入） */
const ROWS = [
  row(1, "B", "600519"),
  row(2, "B", "000001"),
  row(3, "B", "110011"),
  row(4, "B", "161725"),
  row(5, "B", "512880"),
  row(6, "B", "002594"),
  row(7, "A", "LEAK-A")
];

const DANGLING = {
  total: 637,
  fixable_count: 105,
  group_count: 122,
  batch_count: 4,
  null_symbol: 295,
  null_trade_date: 593,
  groups: [],
  batches: []
};

const ORPHAN = {
  total: 3,
  fixable_count: 2,
  blocked_count: 1,
  batch_count: 1,
  groups: [],
  batches: []
};

/** 兜底最宽、最先注册；后注册的具体桩优先匹配。未列出的类别落到 404 → 计数 0。
 *  返回的 paths 用来证明「取数真的跑完了」，否则 `toHaveCount(0)` 会在页面还没
 *  渲染时立刻通过，变成恒真空断言（#2866 变异实测踩过）。 */
async function mockApis(
  page: Page,
  parts: PartKey[] = ["B"]
): Promise<string[]> {
  const paths: string[] = [];
  const track = (route: Route): void => {
    paths.push(new URL(route.request().url()).pathname);
  };
  await page.route(/^https?:\/\/[^/]+\/api\//, route => {
    track(route);
    return route.fulfill({
      status: 404,
      json: { data: null, message: "e2e 未打桩" }
    });
  });
  if (parts.includes("B")) {
    await page.route(DISCREPANCY_URL, route => {
      track(route);
      return route.fulfill({ json: { data: ROWS, message: "" } });
    });
  }
  if (parts.includes("F")) {
    await page.route(DANGLING_URL, route => {
      track(route);
      return route.fulfill({ json: { data: DANGLING, message: "" } });
    });
  }
  if (parts.includes("G")) {
    await page.route(ORPHAN_URL, route => {
      track(route);
      return route.fulfill({ json: { data: ORPHAN, message: "" } });
    });
  }
  return paths;
}

test.describe("全局数据核对提醒（#2866 改版）", () => {
  test.setTimeout(180_000);

  test.beforeEach(async ({ context, baseURL }) => {
    await injectSupabaseSession(context, baseURL!);
  });

  test("三类问题合并成一条紧凑横幅：只列有数据的类别，不铺明细", async ({
    page
  }) => {
    await mockApis(page, ["B", "F", "G"]);
    await page.goto("/#/panorama");

    // 布局两分支互斥，只该出现一条
    const banner = page.locator(".recon-banner");
    await expect(banner).toHaveCount(1, { timeout: 90_000 });
    await expect(banner).toBeVisible();

    await expect(banner.locator(".recon-notice__title")).toHaveText(
      "有 3 类数据需要核对"
    );
    // 域 A 不计入：三类数字分别是 6 / 637 / 3
    await expect(banner.locator(".recon-notice__num")).toHaveText([
      "6",
      "637",
      "3"
    ]);
    await expect(banner.locator(".recon-notice__meta")).toContainText(
      "交易记录信息不完整"
    );
    await expect(banner.locator(".recon-notice__meta")).toContainText(
      "缺账本流水"
    );
    await expect(banner.locator(".recon-notice__meta")).not.toContainText(
      "LEAK-A"
    );

    // 只有标题 + 数字两行文案，且没有「展开全部」这类详情页功能
    await expect(banner.locator("p")).toHaveCount(2);
    await expect(banner.getByRole("button", { name: /展开全部/ })).toHaveCount(
      0
    );
    await expect(banner.getByRole("button", { name: /去查看/ })).toHaveCount(1);

    // 真的紧凑：旧版铺 5 行明细时高度 200+，新版两行应远低于 90px
    const box = await banner.boundingBox();
    expect(box).not.toBeNull();
    expect(box!.height).toBeLessThan(90);
  });

  test("点「去查看」直达条目最多的域 F，工作台真渲染后横幅消失", async ({
    page
  }) => {
    await mockApis(page, ["B", "F", "G"]);
    await page.goto("/#/panorama");

    const banner = page.locator(".recon-banner");
    await expect(banner).toBeVisible({ timeout: 90_000 });
    await banner.getByRole("button", { name: /去查看/ }).click();

    await expect(page).toHaveURL(/reconcile-workbench/);
    await expect(page).toHaveURL(/domain=F/);

    // 先证明工作台页**真的渲染了**，否则「横幅消失」可能只是白屏假绿
    await expect(
      page.getByText("统一处理 E账户对账", { exact: false })
    ).toBeVisible({ timeout: 90_000 });

    await expect(banner).toHaveCount(0);
    await page.waitForTimeout(1500);
    await expect(page.locator(".recon-banner")).toHaveCount(0);
  });

  test("只有一类时显示 1 类，点击落 domain=B", async ({ page }) => {
    await mockApis(page, ["B"]);
    await page.goto("/#/panorama");

    const banner = page.locator(".recon-banner");
    await expect(banner).toBeVisible({ timeout: 90_000 });
    await expect(banner.locator(".recon-notice__title")).toHaveText(
      "有 1 类数据需要核对"
    );
    await expect(banner.locator(".recon-notice__num")).toHaveText(["6"]);

    await banner.getByRole("button", { name: /去查看/ }).click();
    await expect(page).toHaveURL(/domain=B/);
  });

  test("关闭后本次会话不再出现（含刷新）", async ({ page }) => {
    await mockApis(page, ["B"]);
    await page.goto("/#/panorama");

    const banner = page.locator(".recon-banner");
    await expect(banner).toBeVisible({ timeout: 90_000 });

    await page.getByRole("button", { name: "关闭提示" }).first().click();
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

  test("反向对照：三类全 0 时横幅不出现", async ({ page }) => {
    const paths = await mockApis(page, []);
    await page.goto("/#/panorama");

    // 先证明取数真的跑完了再断言「没有横幅」：否则首屏渲染慢一点，
    // toHaveCount(0) 就会在组件挂载前通过，恒真到任何变异都抓不到。
    await expect
      .poll(
        () =>
          paths.filter(p => p.includes("/reconciliation/discrepancies")).length,
        { timeout: 60_000 }
      )
      .toBeGreaterThan(0);
    await page.waitForTimeout(1500);
    await expect(page.locator(".recon-banner")).toHaveCount(0);
  });
});
