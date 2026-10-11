import { expect, test } from "@playwright/test";
import { injectSupabaseSession } from "./support/session";

/**
 * `PnlCalendar` 宿主标题行回归网（#2050）。
 *
 * 症状：资产总览（`/#/panorama`）右卡切到「收益日历」后，口径 ⓘ 图标独占一行
 * （夹在宿主 `<h3>` 标题与 PnlCalendar 的控件排之间），窄容器下被控件行挤断
 * 只剩残影。
 *
 * 根因：旧 `hideTitle` 只抑制 PnlCalendar 的 `<h2>` 文字，`SectionHeader` 的
 * `#info` 插槽（ⓘ）与 `#action` 插槽（控件）仍照常渲染。宿主 `<h3>` 与 PnlCalendar
 * 的 SectionHeader 是两个独立块级元素，ⓘ 落在 SectionHeader 行的左侧、控件排在
 * 右侧，窄容器下控件行占满整行宽度，ⓘ 被挤成 `text-overflow: ellipsis` 残影。
 *
 * 修复（#2050）：用 `hostHeader` 模式替代 `hideTitle`——PnlCalendar 完全不画
 * SectionHeader，只输出控件排（`.pnl-calendar__controls`）；宿主用
 * `PnlCalendarCaliberIcon` 在自画 `<h3>` 旁边补上 ⓘ，三者（标题 + ⓘ + 控件）
 * 一行排开。
 *
 * 本用例断言两个不变式：
 *   1. panorama 切到收益日历后，PnlCalendar 内部**不存在** `.section-header`
 *      （hostHeader 模式生效，没有残留的孤立标题行）。
 *   2. 口径 ⓘ 图标（`.pnl-calendar-caliber-icon`）与宿主 `<h3>` 标题文字在
 *      **同一行**（`y` 坐标重叠），而非独占一行。
 */

test.use({ viewport: { width: 1100, height: 900 } });

test.describe("PnlCalendar 宿主标题行（#2050）", () => {
  test.setTimeout(180_000);

  test.beforeEach(async ({ context, baseURL, page }) => {
    await injectSupabaseSession(context, baseURL!);
    await page.route(/^https?:\/\/[^/]+\/api\//, route =>
      route.fulfill({
        status: 404,
        json: { data: null, message: "e2e 未打桩", error_code: 40400 }
      })
    );
  });

  test("panorama 切到收益日历后，PnlCalendar 内无 SectionHeader、ⓘ 与标题同行", async ({
    page
  }) => {
    await page.goto("/#/panorama");
    const toggle = page.getByRole("button", { name: "打开收益日历" });
    await expect(toggle).toBeVisible({ timeout: 90_000 });
    await toggle.click();

    // 等控件排渲染完（证明 PnlCalendar 确实挂出来了，下面的断言不是在空态上跑）
    const controls = page.locator(".pnl-calendar .pnl-calendar__controls");
    await expect(controls).toBeVisible({ timeout: 30_000 });

    // 1) PnlCalendar 内部不应存在 SectionHeader（hostHeader 模式生效）
    const sectionHeaderCount = await page
      .locator(".pnl-calendar .section-header")
      .count();
    expect(sectionHeaderCount).toBe(0);

    // 2) 口径 ⓘ 图标应可见
    const caliberIcon = page.locator(".pnl-calendar-caliber-icon");
    await expect(caliberIcon).toBeVisible({ timeout: 10_000 });

    // 3) ⓘ 与宿主 <h3> 标题在同行：两者的垂直中心点应接近（差值 < 行高的一半）
    const geometry = await page.evaluate(() => {
      const icon = document.querySelector<HTMLElement>(
        ".pnl-calendar-caliber-icon"
      );
      const h3 = document
        .querySelector<HTMLElement>(".summary-card__toggle")
        ?.closest<HTMLElement>("div.flex")
        ?.querySelector<HTMLElement>("h3");
      if (!icon) throw new Error("未找到 .pnl-calendar-caliber-icon");
      if (!h3) throw new Error("未找到宿主 <h3> 标题");
      const iconRect = icon.getBoundingClientRect();
      const h3Rect = h3.getBoundingClientRect();
      return {
        iconCenterY: iconRect.top + iconRect.height / 2,
        h3CenterY: h3Rect.top + h3Rect.height / 2,
        iconTop: iconRect.top,
        h3Top: h3Rect.top,
        h3Height: h3Rect.height
      };
    });
    // 同行判据：两者垂直中心点差值小于 <h3> 行高的一半
    const centerDiff = Math.abs(geometry.iconCenterY - geometry.h3CenterY);
    expect(centerDiff).toBeLessThan(geometry.h3Height / 2);
  });

  test("welcome 页 PnlCalendar 仍自画 SectionHeader（hostHeader 默认 false 不回归）", async ({
    page
  }) => {
    await page.goto("/#/welcome");
    // welcome 页的 PnlCalendar 不传 hostHeader，应自画完整 SectionHeader
    const sectionHeader = page.locator(".pnl-calendar .section-header");
    await expect(sectionHeader).toBeVisible({ timeout: 90_000 });
    // 且不应存在宿主模式的控件排
    const controlsCount = await page
      .locator(".pnl-calendar .pnl-calendar__controls")
      .count();
    expect(controlsCount).toBe(0);
  });
});
