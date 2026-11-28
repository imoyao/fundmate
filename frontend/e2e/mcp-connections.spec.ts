import { expect, test, type Page } from "@playwright/test";

import { injectSupabaseSession } from "./support/session";

/**
 * 数据连接页回归网：入口 → 两种连接方式 → 断开。
 *
 * 三类只有真浏览器能证的事：
 * 1. **入口真的可达**：头像菜单里新增的「数据连接」能跳到 hidden 路由（hidden 路由
 *    不进侧边栏，单测里的路由表断言证明不了菜单项真的挂上了）；
 * 2. **OAuth 是真的整页跳转**：点「连接」→ 调 begin 端点 → `window.location.assign`
 *    用的是后端返回的 URL。桩里故意返回一个**站内** URL，这样跳转后仍在本应用，
 *    既能断言 URL 被消费，又不会把用例变成对同花顺站点的可用性测试；
 * 3. **API Key 不回显**：保存后输入框清空，且请求体里带的是用户刚填的值。
 *
 * 防假绿：catch-all 404 先注册（后注册的路由优先匹配），避免别的 /api/ 请求意外
 * 返回真实数据把某个断言喂绿；每次都先坐实页面确实渲染了目标卡片再操作。
 */

test.describe.configure({ timeout: 300_000 });

type Connection = {
  provider: string;
  auth_type: "oauth2" | "static_token";
  status: string;
  expires_at: string | null;
  updated_at: string | null;
  last_error_kind: string | null;
  key_version: number;
};

type StubOptions = {
  connections?: Connection[];
  /** OAuth begin 返回的授权地址；默认回跳本页并带成功 query */
  authorizationUrl?: string;
};

async function stubMcpApi(
  page: Page,
  baseURL: string,
  options: StubOptions = {}
) {
  const staticCalls: Array<{ provider: string; api_key: string }> = [];
  const beginCalls: Array<{ provider: string }> = [];
  const deletePaths: string[] = [];

  // 先注册兜底：Playwright 路由后注册者优先，具体端点会覆盖它
  await page.route(
    url => new URL(url).pathname.startsWith("/api/"),
    route => route.fulfill({ status: 404, json: { data: null, message: "" } })
  );

  await page.route(
    url => new URL(url).pathname === "/api/mcp/connections/",
    route =>
      route.fulfill({
        json: { data: options.connections ?? [], message: "ok" }
      })
  );

  await page.route(
    url => new URL(url).pathname === "/api/mcp/connections/static/",
    route => {
      staticCalls.push(JSON.parse(route.request().postData() ?? "{}"));
      return route.fulfill({
        json: {
          data: { provider: "qieman", auth_type: "static_token" },
          message: "ok"
        }
      });
    }
  );

  // DELETE 只匹配 `/connections/<provider>/`：不能用裸 startsWith，
  // 否则会把 `/connections/`（GET 列表）和 `/connections/static/`（POST）一并吃掉。
  await page.route(
    url => {
      const path = new URL(url).pathname;
      return (
        path.startsWith("/api/mcp/connections/") &&
        path !== "/api/mcp/connections/" &&
        path !== "/api/mcp/connections/static/"
      );
    },
    route => {
      if (route.request().method() !== "DELETE") return route.continue();
      deletePaths.push(new URL(route.request().url()).pathname);
      return route.fulfill({
        json: { data: { provider: "qieman", connected: false }, message: "ok" }
      });
    }
  );

  await page.route(
    url => new URL(url).pathname === "/api/mcp/oauth/begin/",
    route => {
      beginCalls.push(JSON.parse(route.request().postData() ?? "{}"));
      return route.fulfill({
        json: {
          data: {
            authorization_url:
              options.authorizationUrl ??
              `${baseURL}/#/settings/mcp-connections?mcp_connected=1&provider=tzzb`,
            state: "e2e-state",
            expires_in: 300
          },
          message: "ok"
        }
      });
    }
  );

  return { staticCalls, beginCalls, deletePaths };
}

test.describe("数据连接页", () => {
  test("头像菜单有入口，页面展示两种连接方式的卡片", async ({
    context,
    page
  }) => {
    const baseURL = test.info().project.use.baseURL as string;
    await injectSupabaseSession(context, baseURL);
    const calls = await stubMcpApi(page, baseURL);

    await page.goto("/");
    await page.locator(".el-dropdown-link").first().click();
    await page.getByText("数据连接", { exact: true }).click();

    await expect(page).toHaveURL(/\/settings\/mcp-connections/);
    await expect(page.getByRole("heading", { name: "数据连接" })).toBeVisible();
    await expect(page.locator('[data-provider="tzzb"]')).toBeVisible();
    await expect(page.locator('[data-provider="qieman"]')).toBeVisible();
    await expect(calls.beginCalls).toHaveLength(0);
  });

  test("API Key 型：填 Key 后调 static 端点，保存后不回显", async ({
    context,
    page
  }) => {
    const baseURL = test.info().project.use.baseURL as string;
    await injectSupabaseSession(context, baseURL);
    const calls = await stubMcpApi(page, baseURL);

    await page.goto("/#/settings/mcp-connections");
    const card = page.locator('[data-provider="qieman"]');
    await expect(card.getByRole("button", { name: "连接" })).toBeVisible();
    await card.getByRole("button", { name: "连接" }).click();

    const input = card.locator('input[type="password"]');
    await input.fill("sk-e2e-secret");
    await card.getByRole("button", { name: "保存" }).click();

    await expect.poll(() => calls.staticCalls.length).toBe(1);
    expect(calls.staticCalls[0]).toEqual({
      provider: "qieman",
      api_key: "sk-e2e-secret"
    });
    await expect(page.getByText("API Key 已保存")).toBeVisible();
    await expect(input).toHaveCount(0);
  });

  test("OAuth 型：调 begin 端点并跳到后端返回的授权地址", async ({
    context,
    page
  }) => {
    const baseURL = test.info().project.use.baseURL as string;
    await injectSupabaseSession(context, baseURL);
    const calls = await stubMcpApi(page, baseURL, {
      authorizationUrl: `${baseURL}/#/settings/mcp-connections?mcp_connected=1&provider=tzzb`
    });

    await page.goto("/#/settings/mcp-connections");
    const card = page.locator('[data-provider="tzzb"]');
    await expect(card.getByRole("button", { name: "连接" })).toBeVisible();
    await card.getByRole("button", { name: "连接" }).click();

    await expect.poll(() => calls.beginCalls.length).toBe(1);
    expect(calls.beginCalls[0]).toEqual({ provider: "tzzb" });
    await expect(page).toHaveURL(/mcp_connected=1/);
    await expect(page.getByText("同花顺投资账本已授权连接")).toBeVisible();
  });

  test("已连接的服务显示断开按钮，点击调 DELETE 端点", async ({
    context,
    page
  }) => {
    const baseURL = test.info().project.use.baseURL as string;
    await injectSupabaseSession(context, baseURL);
    const calls = await stubMcpApi(page, baseURL, {
      connections: [
        {
          provider: "qieman",
          auth_type: "static_token",
          status: "active",
          expires_at: null,
          updated_at: "2026-11-27T10:00:00",
          last_error_kind: null,
          key_version: 1
        }
      ]
    });

    await page.goto("/#/settings/mcp-connections");
    const card = page.locator('[data-provider="qieman"]');
    await expect(card.locator('[data-state="connected"]')).toBeVisible();
    await card.getByRole("button", { name: "断开连接" }).click();

    await expect.poll(() => calls.deletePaths.length).toBe(1);
    expect(calls.deletePaths[0]).toBe("/api/mcp/connections/qieman/");
    await expect(page.getByText("已断开连接")).toBeVisible();
  });

  // #3303：token 5 分钟寿命是常态，过期卡片必须把「重新连接」摆成主按钮，
  // 且断开入口仍在（#3296 语义：过期恰恰是最需要断开的时刻）
  test("授权已过期的卡片：problem 徽章 + 一键重连调 begin，断开入口保留", async ({
    context,
    page
  }) => {
    const baseURL = test.info().project.use.baseURL as string;
    await injectSupabaseSession(context, baseURL);
    const calls = await stubMcpApi(page, baseURL, {
      connections: [
        {
          provider: "tzzb",
          auth_type: "oauth2",
          status: "active",
          expires_at: new Date(Date.now() - 60_000).toISOString(),
          updated_at: "2026-11-28T17:00:00",
          last_error_kind: null,
          key_version: 1
        }
      ]
    });

    await page.goto("/#/settings/mcp-connections");
    const card = page.locator('[data-provider="tzzb"]');
    await expect(card.locator('[data-state="problem"]')).toBeVisible();
    await expect(card.getByText("授权已过期")).toBeVisible();
    // hint 行与卡片底部 tip 都含「静默续期」字样，锚定 hint 行避免严格模式双命中
    await expect(
      card.locator(".mcp-card__hint").getByText(/可一键静默续期/)
    ).toBeVisible();

    await card.getByRole("button", { name: "重新连接" }).click();
    await expect.poll(() => calls.beginCalls.length).toBe(1);
    await expect(card.getByRole("button", { name: "断开连接" })).toBeVisible();
  });

  // #3303：临期（60 秒内）在「已连接」卡片上就给续期入口，不等翻成过期态
  test("临期卡片：connected 徽章旁出现「立即续期」，点击调 begin", async ({
    context,
    page
  }) => {
    const baseURL = test.info().project.use.baseURL as string;
    await injectSupabaseSession(context, baseURL);
    const calls = await stubMcpApi(page, baseURL, {
      connections: [
        {
          provider: "tzzb",
          auth_type: "oauth2",
          status: "active",
          expires_at: new Date(Date.now() + 30_000).toISOString(),
          updated_at: "2026-11-28T17:00:00",
          last_error_kind: null,
          key_version: 1
        }
      ]
    });

    await page.goto("/#/settings/mcp-connections");
    const card = page.locator('[data-provider="tzzb"]');
    await expect(card.locator('[data-state="connected"]')).toBeVisible();
    await expect(card.getByText(/点「立即续期」保持连接/)).toBeVisible();
    await expect(card.getByText("授权有效期至")).toBeHidden();

    await card.getByRole("button", { name: "立即续期" }).click();
    await expect.poll(() => calls.beginCalls.length).toBe(1);
  });
});
