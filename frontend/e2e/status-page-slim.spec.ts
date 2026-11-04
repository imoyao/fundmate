import { expect, test, type Page } from "@playwright/test";
import { injectSupabaseSession } from "./support/session";

/**
 * #980 批 B9 回归网：系统状态页拆分后的接线（441 → 149 行）。
 *
 * 口径（状态→文案/色调、组件行、整体横幅）搬进 `components/statusModel.ts`，
 * 有 25 例纯函数单测；`StatusBanner` / `StatusComponentList` 是排版。这里钉的是
 * **纯函数与模板之间的那几根线**：
 *
 * ① 横幅的 `v-if / v-else` 对：拆组件时最容易只搬 `v-if` 那半，把 `v-else` 的
 *    骨架屏落在页面上——症状是首屏一片空白（不是骨架屏），用户以为页面坏了。
 * ② 三行组件的色调 class（`component-row__dot--ok` 等）：色调算对了但没绑到 class，
 *    页面全绿也是「假绿」。
 * ③ 取数失败时**不渲染组件清单**（`v-if="health"`）：若清单仍渲染，会显示上一次
 *    的数据或一片空行，用户看到的是「组件都在、只是没名字」。
 */

const HEALTH_URL = /\/api\/health(\?|$)/;

function healthy(overrides: Record<string, unknown> = {}) {
  return {
    status: "ok",
    message: "",
    components: {
      database: { status: "healthy", dialect: "sqlite" },
      scheduler: {
        status: "healthy",
        enabled: true,
        last_success_run: "2026-10-27T06:06:39.184874"
      },
      llm: {
        status: "healthy",
        configured: true,
        provider: "deepseek",
        model: "chat"
      }
    },
    ...overrides
  };
}

async function mockHealth(page: Page, body: unknown, status = 200) {
  await page.route(/^https?:\/\/[^/]+\/api\//, route =>
    route.fulfill({ status: 404, json: { data: null, message: "e2e 未打桩" } })
  );
  await page.route(HEALTH_URL, route => route.fulfill({ status, json: body }));
}

test.describe("系统状态页拆分后回归（#980 批 B9）", () => {
  test.setTimeout(180_000);

  test.beforeEach(async ({ context, baseURL }) => {
    await injectSupabaseSession(context, baseURL!);
  });

  test("全部正常：绿色横幅 + 三行清单 + 状态点走 ok 色调", async ({ page }) => {
    await mockHealth(page, healthy());
    await page.goto("/#/status");

    const banner = page.locator(".status-banner");
    await expect(banner).toBeVisible({ timeout: 90_000 });
    await expect(banner).toHaveClass(/status-banner--ok/);
    await expect(banner).toContainText("所有组件运行正常");
    // 检查时刻来自 dayjs，格式 HH:mm:ss
    await expect(banner.locator(".status-banner__meta")).toHaveText(
      /检查于 \d{2}:\d{2}:\d{2}/
    );

    const rows = page.locator(".component-row");
    await expect(rows).toHaveCount(3);
    await expect(rows.nth(0)).toContainText("数据库");
    await expect(rows.nth(0)).toContainText("SQLITE");
    await expect(rows.nth(1)).toContainText("最近成功运行 2026-10-27 06:06");
    await expect(rows.nth(2)).toContainText("deepseek · chat");
    await expect(page.locator(".component-row__dot--ok")).toHaveCount(3);
    await expect(page.locator(".component-row__status--ok")).toHaveCount(3);
  });

  test("有降级：黄色横幅列出受影响组件，异常行带原因与 error 色调", async ({
    page
  }) => {
    await mockHealth(
      page,
      healthy({
        components: {
          database: {
            status: "unhealthy",
            dialect: "sqlite",
            message: "连接超时"
          },
          scheduler: {
            status: "degraded",
            enabled: true,
            last_success_run: null,
            message: "上次运行失败"
          },
          llm: { status: "healthy", configured: true, provider: "deepseek" }
        }
      })
    );
    await page.goto("/#/status");

    const banner = page.locator(".status-banner");
    await expect(banner).toBeVisible({ timeout: 90_000 });
    await expect(banner).toHaveClass(/status-banner--warn/);
    await expect(banner).toContainText("部分组件需要关注");
    await expect(banner.locator(".status-banner__desc")).toHaveText(
      "数据库：异常；数据调度：降级"
    );

    // 色调 class 绑上了（算对不等于画对）
    await expect(page.locator(".component-row__dot--error")).toHaveCount(1);
    await expect(page.locator(".component-row__dot--warn")).toHaveCount(1);
    await expect(page.locator(".component-row__status--error")).toHaveText(
      "异常"
    );
    // 异常才出原因行，「无消息即正常」
    await expect(page.locator(".component-row__hint")).toHaveCount(2);
    await expect(page.locator(".component-row__hint").first()).toHaveText(
      "连接超时"
    );
  });

  test("取数失败：红色横幅 + 重试按钮，且不渲染组件清单", async ({ page }) => {
    await mockHealth(page, { detail: "boom" }, 500);
    await page.goto("/#/status");

    const banner = page.locator(".status-banner");
    await expect(banner).toBeVisible({ timeout: 90_000 });
    await expect(banner).toHaveClass(/status-banner--error/);
    await expect(banner).toContainText("暂时无法获取状态");
    await expect(banner.getByRole("button", { name: "重试" })).toBeVisible();
    // 失败时 health 为 null：清单不出现（不是「空行清单」）
    await expect(page.locator(".component-row")).toHaveCount(0);
    await expect(page.locator(".component-list")).toHaveCount(0);
  });

  test("首屏取数中显示骨架屏，而不是空白", async ({ page }) => {
    await page.route(/^https?:\/\/[^/]+\/api\//, route =>
      route.fulfill({
        status: 404,
        json: { data: null, message: "e2e 未打桩" }
      })
    );
    // 健康接口拖 5s：这段时间里页面必须停在骨架屏（banner 为 null 的 v-else 分支）
    await page.route(HEALTH_URL, async route => {
      await new Promise(resolve => setTimeout(resolve, 5000));
      await route.fulfill({ json: healthy() });
    });
    await page.goto("/#/status", { waitUntil: "domcontentloaded" });

    await expect(page.locator(".el-skeleton")).toBeVisible({ timeout: 30_000 });
    await expect(page.locator(".status-banner")).toHaveCount(0);

    // 取数完成后骨架屏让位给横幅
    await expect(page.locator(".status-banner")).toBeVisible({
      timeout: 90_000
    });
    await expect(page.locator(".el-skeleton")).toHaveCount(0);
  });
});
