import { expect, test, type Page } from "@playwright/test";
import { injectSupabaseSession } from "./support/session";

/**
 * #980 批 B7 回归网：重置密码页拆分后的接线。
 *
 * 页面被拆成「深海背景装饰 + 左侧品牌叙事区」两个子组件，外壳与三态表单留在页面里。
 * 拆分时最容易坏掉、而类型检查与 lint 都看不见的有三处：
 *
 * 1. **`min-[969px]:flex` 与 968px 媒体查询是一对**，但它们跑到了两个文件里：
 *    显隐阈值在子组件的 `<aside>` 上，`.login-form` 的「移动端回归页面本体」在
 *    父文件的裸 `@media (width <= 968px)` 里（该条带 `breakpoint-allow`，是
 *    `guard_breakpoints.py` 的存量基线）。任何一边被挪走，两侧就会在不同阈值换挡。
 * 2. **装饰层必须不可点**：`.login-bg-decor` 是整屏 `fixed inset-0` 的一层，
 *    少写 `pointer-events: none` 就会挡住整页所有点击（表单直接点不动）。
 *    这个错误在 DOM 里完全看不出来，只能靠命中测试发现。
 * 3. **三态机的文案**：checking / ready / expired 三态的可见文案都搬在那段模板里，
 *    拆组件时若把 `v-if` 链剪错，页面会停在「正在验证链接…」而不报错。
 */

/** 宽视口：aside 显示（≥969px） */
const WIDE = { width: 1440, height: 900 };
/** 窄视口：aside 隐藏（<969px） */
const NARROW = { width: 800, height: 900 };

async function stubApi(page: Page) {
  // 本页不调业务接口，但兜底一层，避免请求经 vite 代理打到本机真后端
  await page.route(/^https?:\/\/[^/]+\/api\//, route =>
    route.fulfill({ status: 404, json: { data: null, message: "e2e 未打桩" } })
  );
}

test.describe("重置密码页拆分后回归（#980 批 B7）", () => {
  test.setTimeout(180_000);

  test.beforeEach(async ({ context, baseURL }) => {
    await injectSupabaseSession(context, baseURL!);
  });

  test("宽视口：装饰层齐全且不可点，品牌区文案照旧", async ({ page }) => {
    await page.setViewportSize(WIDE);
    await stubApi(page);
    await page.goto("/#/reset-password");

    // 装饰层：4 圈涟漪 + 3 颗气泡，全部 aria-hidden
    const decor = page.locator(".login-bg-decor");
    await expect(decor).toBeVisible({ timeout: 90_000 });
    await expect(decor).toHaveAttribute("aria-hidden", "true");
    await expect(decor.locator(".login-ripple")).toHaveCount(4);
    await expect(decor.locator(".login-bubble")).toHaveCount(3);
    // ⚠️ 整屏 fixed 覆盖层必须不拦点击；少了它表单点不动，而 DOM 看起来完全正常
    await expect(decor).toHaveCSS("pointer-events", "none");

    // 品牌叙事区：文案与落款
    const aside = page.locator(".login-brand");
    await expect(aside).toBeVisible();
    await expect(aside).toContainText("重置密码");
    await expect(aside).toContainText("通过邮件链接安全地设置新密码");
    await expect(aside).toContainText("潮有涨落，壳有深浅。算得清，才无患。");
    // 鹦鹉螺插画是 v-html 注入的 SVG（不是图片资源）
    await expect(aside.locator(".login-brand-bg svg")).toHaveCount(1);

    // 三态之一：初始 checking
    await expect(
      page.getByRole("button", { name: /正在验证链接/ })
    ).toBeVisible();
    await expect(page.getByText("请稍候，正在确认你的身份")).toBeVisible();
  });

  test("窄视口：品牌区隐藏、表单卡片回归页面本体（两个阈值成对）", async ({
    page
  }) => {
    await page.setViewportSize(NARROW);
    await stubApi(page);
    await page.goto("/#/reset-password");

    const form = page.locator(".login-form");
    await expect(form).toBeVisible({ timeout: 90_000 });

    // aside 被 `min-[969px]:flex` 收掉：窄视口下不可见
    await expect(page.locator(".login-brand")).toBeHidden();

    // 968px 媒体查询的三个声明必须仍在生效（等于证明这条裸断点没被搬到子组件）
    await expect(form).toHaveCSS("padding-top", "0px");
    await expect(form).toHaveCSS("border-top-width", "0px");
    await expect(form).toHaveCSS("box-shadow", "none");
  });

  test("30 秒内没等到 PASSWORD_RECOVERY ⇒ 转 expired 态并给回登录出口", async ({
    page
  }) => {
    await page.setViewportSize(WIDE);
    await stubApi(page);
    // 冻结时钟后再进页面：页面 onMounted 里那个 30s 兜底计时器才有确定行为
    await page.clock.install();
    await page.goto("/#/reset-password");

    await expect(
      page.getByRole("button", { name: /正在验证链接/ })
    ).toBeVisible({ timeout: 90_000 });

    await page.clock.fastForward(31_000);

    await expect(page.getByText("链接无效或已过期，请重新发起")).toBeVisible();
    // 回登录出口必须在（expired 态唯一可走的路）。不断言点击后的最终 URL：
    // 本用例注入了 session，`/login` 的守卫会把已登录用户重定向走，跳到哪里
    // 取决于守卫配置而不是本页——那是另一件事，不该混进拆分回归网。
    await expect(page.getByRole("button", { name: "返回登录" })).toBeVisible();
  });
});
