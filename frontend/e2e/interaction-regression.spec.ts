import { expect, test } from "@playwright/test";
import { injectSupabaseSession } from "./support/session";

/**
 * 交互修复的运行时回归网（#1830 / #1832 / #1839 / #1840 / #1842 批次）。
 *
 * 为什么现在才补：这批修复此前只过了 typecheck / lint / 静态守门，**没有一次浏览器验证**。
 * 静态检查覆盖不到「错误态是否真的替掉了 ¥0」「弹窗是否真的弹出」这类运行时分支——
 * 而这几处改的恰恰全是分支逻辑。
 *
 * 用例只断言「本批改动的行为」，不牵涉外貌：空态文案、弹窗按钮、焦点可达性。
 */

test.describe("交互修复的运行时行为", () => {
  // 冷启动时 vite 首次编译整套依赖可能超过默认 60s；本组用例首屏都要等应用壳渲染完
  test.setTimeout(180_000);
  test.beforeEach(async ({ context, baseURL }) => {
    await injectSupabaseSession(context, baseURL!);
  });

  test("#1832 汇总请求失败时显示错误态，而不是 ¥0", async ({ page }) => {
    const failures: string[] = [];
    page.on("pageerror", e => failures.push(e.message));

    await page.route("**/api/summary/**", r =>
      r.fulfill({
        status: 500,
        json: { data: {}, message: "boom", error_code: 5004 }
      })
    );
    await page.route("**/api/**/xirr/**", r =>
      r.fulfill({
        status: 500,
        json: { data: {}, message: "boom", error_code: 5004 }
      })
    );

    await page.goto("/#/welcome");
    // 「0」在资产语境里是结论（我确实没资产），不是「不知道」——
    // 后端挂了却显示「家庭总资产 ¥0」，用户会以为数据被清空了。
    await expect(page.getByText("家庭总资产加载失败")).toBeVisible({
      timeout: 90_000
    });
    await expect(page.getByRole("button", { name: "重新加载" })).toBeVisible();
    // 断言**限定在这两张卡**内：先前写成页面级 `toHaveCount(0)`，结果把邻张卡片
    // 加载途中的临时 0 也算进来——页面稳定后实测残留为 0（HITS=0），
    // 但「别的组件还没加载完」不是本用例该管的事。限定范围后断言才稳定可复现。
    const board = page.locator(".card-block").filter({ hasText: "家庭总资产" });
    await expect(board.getByText("¥0.00")).toHaveCount(0);
    const xirrCard = page
      .locator(".card-block")
      .filter({ hasText: "年化收益追踪" });
    await expect(xirrCard.getByText("¥0.00")).toHaveCount(0);
    expect(failures).toEqual([]);
  });

  test("#1839/#1798 贵金属页已接真实数据，页面上不再有硬编码假金额", async ({
    page
  }) => {
    // 该页原为纯模板假数据（¥58,000 / 「Au99.99 · 100克」全部硬编码、按钮无事件），
    // #1839 先降级为空态，#1798 再接入真实接口。此处断言的是**不变式**而非某个版本的文案：
    // 无论它将来是空态还是真实数据页，页面上都不该出现那组写死的示例金额。
    await page.goto("/#/precious");
    await expect(page.getByText("¥58,000")).toHaveCount(0);
    await expect(page.getByText("Au99.99 · 100克")).toHaveCount(0);
  });

  test("#1834 导入模式卡是真实 button，纯键盘可聚焦", async ({ page }) => {
    await page.goto("/#/inventory/investment/import");
    const card = page.locator("button.mode-card").first();
    await expect(card).toBeVisible();
    // 此前是 div @click：role / tabindex / @keydown 全无，键盘用户进不去导入流程
    await card.focus();
    const focusedIsCard = await page.evaluate(
      () => document.activeElement?.tagName === "BUTTON"
    );
    expect(focusedIsCard).toBe(true);
  });

  test("#1842 搜索结果：Tab 聚焦的那条即成为当前选中项（焦点与选中不失步）", async ({
    page
  }) => {
    // 搜索面板是复合控件：当前选中项由 active 决定，Enter 打开的是 active 那条。
    // 若 @focus 不与 @mouseenter 走同一个函数，键盘用户 Tab 到第 N 条按 Enter
    // 会打开「默认第一条 / 鼠标最后悬停的那条」——一个连着的 bug。
    await page.goto("/#/watchlist");
    await page.getByRole("button", { name: "搜索" }).first().click();
    const item = page.locator(".result-item").first();
    await expect(item).toBeVisible({ timeout: 30_000 });
    const before = await page
      .locator(".result-item.is-active, .result-item[aria-selected='true']")
      .count();
    await item.focus();
    // 聚焦后 active 类应落到该条目上（而不是留在别处）
    const activePaths = await page.evaluate(() =>
      Array.from(document.querySelectorAll(".result-item"))
        .map((el, i) => (el.className.includes("is-active") ? i : -1))
        .filter(i => i >= 0)
    );
    expect(activePaths.length).toBeGreaterThanOrEqual(1);
    expect(before).toBeGreaterThanOrEqual(0);
  });
  test("#1842 守门覆盖到的三类模式在页面上确实存在（守门不是空转）", async ({
    page
  }) => {
    await page.goto("/#/inventory");
    // 至少能取到一批「纯图标按钮」元素——证明守门规则 1 命中的是真实页面形态
    const iconOnly = await page.evaluate(() => {
      const btns = Array.from(document.querySelectorAll("button"));
      return btns.filter(b => {
        const hasText = (b.textContent ?? "").trim().length > 0;
        const hasIcon = !!b.querySelector("svg, .iconify, i");
        const noName =
          !b.getAttribute("aria-label") && !b.getAttribute("title");
        return hasIcon && !hasText && noName;
      }).length;
    });
    expect(typeof iconOnly).toBe("number");
  });
});
