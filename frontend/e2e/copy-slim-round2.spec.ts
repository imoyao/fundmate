import { expect, test, type Page } from "@playwright/test";
import { injectSupabaseSession } from "./support/session";

/**
 * 第二轮文案收敛回归网：删掉标语 / 同义说明之后，页面必须仍然看得懂、
 * 功能入口一个不少。
 *
 * 判据刻意分两半：
 * 1. 旧文案与旧类名不许回来。**类名取旧代码里真实存在的**（`.login-sub`、
 *    `.setting-row__desc`、`.field-block__desc`），否则 `toHaveCount(0)` 是恒真空断言；
 * 2. 关键控件仍在（输入框、修改 / 保存、退出）。只数「文案没了」的用例
 *    挡不住「连字段一起删掉」这种回归。
 */

/** 打桩：profile 页只需 /me 有值就能整页渲染，其余 API 一律兜底 */
async function stubProfileApis(page: Page) {
  await page.route(/^https?:\/\/[^/]+\/api\//, route =>
    route.fulfill({ status: 200, json: { data: null, message: "ok" } })
  );
  await page.route(/^https?:\/\/[^/]+\/api\/auth\/me\/$/, route =>
    route.fulfill({
      status: 200,
      json: {
        data: {
          id: 1,
          supabase_id: "e2e-user",
          username: "tester",
          nickname: "测试用户",
          avatar: null,
          email: "tester@example.com",
          role: "owner",
          role_label: "所有者",
          family: { id: 1, name: "默认家庭" }
        },
        message: "ok"
      }
    })
  );
}

test.describe("说明文案收敛（第二轮）", () => {
  test.setTimeout(180_000);

  test("登录页（窄屏）：品牌副标与登录提示不常驻，表单仍可用", async ({
    page
  }) => {
    await page.setViewportSize({ width: 480, height: 900 });
    await page.goto("/#/login");

    const brand = page.locator(".login-mobile-brand");
    await expect(brand).toBeVisible();
    await expect(brand.getByRole("heading", { level: 1 })).toContainText(
      "看见你的"
    );

    // 旧实现：h1 下面又写了一遍同义副标；页脚还有一句和 placeholder 完全一样的提示
    await expect(page.locator(".login-form .login-sub")).toHaveCount(0);
    await expect(page.locator(".login-hint")).toHaveCount(0);

    // 信息由 placeholder 承担，登录入口一个不少
    await expect(page.getByPlaceholder("邮箱或用户名")).toBeVisible();
    await expect(page.getByPlaceholder("密码（至少8位）")).toBeVisible();
    await expect(
      page.getByRole("button", { name: "登录", exact: true })
    ).toBeVisible();
  });

  test("个人中心：说明小字不常驻，五个字段与退出入口仍在", async ({
    context,
    baseURL,
    page
  }) => {
    await injectSupabaseSession(context, baseURL!);
    await stubProfileApis(page);
    await page.goto("/#/profile");

    await expect(page.getByRole("heading", { name: "账号安全" })).toBeVisible({
      timeout: 90_000
    });

    // 旧实现里的 5 条小字：三处诗意副标 + 两处字段说明
    await expect(page.locator(".setting-row__desc")).toHaveCount(0);
    await expect(page.locator(".danger-zone__desc")).toHaveCount(0);
    await expect(page.locator(".field-block__desc")).toHaveCount(0);
    await expect(page.getByText("我们不说再见", { exact: false })).toHaveCount(
      0
    );
    await expect(page.getByText("它会陪你见证", { exact: false })).toHaveCount(
      0
    );

    // 删掉包裹层之后，字段名直接可定位；语义锚同时给 e2e / Agent 用
    const emailRow = page.locator('[data-field="email"]');
    await expect(emailRow).toContainText("登录邮箱");
    await expect(emailRow).toContainText("tester@example.com");
    await expect(
      page.locator('[data-field="password"] .modify-link')
    ).toBeVisible();
    await expect(page.locator('[data-field="nickname"] input')).toBeVisible();
    await expect(page.locator('[data-field="username"] input')).toBeVisible();
    await expect(
      page
        .locator('[data-action="logout"]')
        .getByRole("button", { name: "退出" })
    ).toBeVisible();
  });
});
