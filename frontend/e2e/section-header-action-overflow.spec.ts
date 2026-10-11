import { expect, test, type Page } from "@playwright/test";
import { injectSupabaseSession } from "./support/session";

/**
 * `SectionHeader` 操作槽收缩回归网（#2039）。
 *
 * 症状：资产总览（`/#/panorama`）右卡切到「收益日历」后，标题行右侧那排控件
 * （粒度 / 形态 / 口径 ×3 + 区间导航）**溢出卡片**，并叠到左侧的 ⓘ 口径图标上。
 *
 * 根因：`SectionHeader` 的 `__action` 曾写死 `flex-shrink: 0`，使它恒为 max-content
 * （这排控件实测宽 588px）。窄容器下负空间无处可去，全压给 `min-width: 0` 的
 * title-group，压到底之后整排控件就顶出卡片右边界。
 *
 * 这是一个**纯几何**缺陷——静态检查（typecheck / lint / 静态守门）一律看不见，
 * 单测的 jsdom 也不做 flex 布局。只有在真实浏览器里量 boundingClientRect 才能钉住。
 * 因此本用例断言的是不变式而非某个像素值：
 *   操作槽（`.section-header__action`）的右边缘不得超出标题行 / 卡片内容区右边缘。
 * 修复前该不变式被打破（action 顶到 588px，远超容器），修复后成立（收缩 + 折行）。
 */

/** 故意选一个「右卡半宽 + 侧边栏占位」后可用宽度明显小于控件排 max-content 的视口 */
test.use({ viewport: { width: 1100, height: 900 } });

test.describe("SectionHeader 操作槽在窄容器下不溢出（#2039）", () => {
  // 冷启动时 vite 首次编译整套依赖可能超过默认 60s
  test.setTimeout(180_000);

  test.beforeEach(async ({ context, baseURL, page }) => {
    await injectSupabaseSession(context, baseURL!);
    // 兜底：未打桩的接口一律 404，避免请求经 vite 代理打到本机 8000 端口的真后端，
    // 让用例失去自洽性。⚠️ 必须用**锚定 host 的正则**：`**/api/**` 会把 vite 的
    // 源码模块请求（如 /src/api/summary.ts）也一并匹配掉（见 product-detail-dedup 的教训）。
    await page.route(/^https?:\/\/[^/]+\/api\//, route =>
      route.fulfill({
        status: 404,
        json: { data: null, message: "e2e 未打桩", error_code: 40400 }
      })
    );
  });

  test("切到收益日历后，控件排不越出卡片右边界、仍全部可见", async ({
    page
  }) => {
    await page.goto("/#/panorama");
    // 切到日历态：开关按钮的 aria-label 会随之翻转（「打开」↔「返回」）
    const toggle = page.getByRole("button", { name: "打开收益日历" });
    await expect(toggle).toBeVisible({ timeout: 90_000 });
    await toggle.click();

    // 等 PnlCalendar 的控件排渲染完——控件排无条件渲染，与日历数据是否取到无关。
    // #2050：panorama 用 `host-header` 模式，PnlCalendar 不再画 SectionHeader，
    // 控件排在 `.pnl-calendar__controls` 里（而非旧的 `.section-header__action`）。
    const controls = page.locator(".pnl-calendar .pnl-calendar__controls");
    await expect(controls).toBeVisible({ timeout: 30_000 });

    // 先证明控件**真的渲染出来了**，否则「不溢出」会因为槽是空的而假绿
    const controlCount = await controls.locator("button").count();
    expect(controlCount).toBeGreaterThanOrEqual(5);

    const m = await measureHeader(page);
    // 1) 控件排右边缘不得超出卡片内容区右边缘（修复前控件恒为 588px，此处必红）
    expect(m.controlsRight).toBeLessThanOrEqual(m.cardContentRight + 1);
    // 2) 整排控件确实**折了行**（收缩到低于 max-content 才会折），
    //    否则说明只是恰好塞得下，断言就没有真正命中 #2039 的场景
    expect(m.controlsHeight).toBeGreaterThan(m.singleLineHeight);
  });

  test("不做任何操作时页面上不存在横向溢出的标题行（守门不是空转）", async ({
    page
  }) => {
    await page.goto("/#/panorama");
    await expect(
      page.getByRole("button", { name: "打开收益日历" })
    ).toBeVisible({ timeout: 90_000 });

    // 遍历当前页所有 SectionHeader：任何一条的 __action 都不得越出它自己的容器。
    // 这条不只盯收益日历，也覆盖页面上其它复用该组件的标题行——同一处 flex 声明的回退
    // 会同时波及它们，扫描比抽查便宜（AGENTS.md「扫描优先于抽查」）。
    const offenders = await page.evaluate(() => {
      const out: string[] = [];
      document
        .querySelectorAll<HTMLElement>(".section-header__action")
        .forEach((action, i) => {
          const header = action.closest<HTMLElement>(".section-header");
          if (!header) return;
          const ar = action.getBoundingClientRect();
          const hr = header.getBoundingClientRect();
          if (ar.width > 0 && ar.right > hr.right + 1) {
            out.push(
              `#${i}: action.right=${ar.right} > header.right=${hr.right}`
            );
          }
        });
      return out;
    });
    expect(offenders).toEqual([]);
  });
});

/** 量一组几何值：控件排 / 卡片内容区的右边缘，以及控件排行高 */
async function measureHeader(page: Page) {
  return page.evaluate(() => {
    const controls = document.querySelector<HTMLElement>(
      ".pnl-calendar .pnl-calendar__controls"
    );
    if (!controls) throw new Error("未找到收益日历的 .pnl-calendar__controls");
    const card = controls.closest<HTMLElement>("div.rounded-2xl");
    if (!card) throw new Error("未找到承载控件排的卡片");
    const controlsRect = controls.getBoundingClientRect();
    const cardRect = card.getBoundingClientRect();
    const padRight = parseFloat(getComputedStyle(card).paddingRight) || 0;
    // 单个控件（SegmentedControl / 按钮）的典型行高，用于判「是否折了行」
    const control = controls.querySelector<HTMLElement>("button");
    const singleLineHeight = control
      ? control.getBoundingClientRect().height
      : 0;
    return {
      controlsRight: controlsRect.right,
      controlsHeight: controlsRect.height,
      cardContentRight: cardRect.right - padRight,
      singleLineHeight
    };
  });
}
