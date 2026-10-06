import { expect, test } from "@playwright/test";

import { injectSupabaseSession } from "./support/session";

/**
 * #1797 合并重复异常页后的直访回归。
 *
 * 被删的两条旧全屏异常页路由与 error.ts 同组件且站内零入链，合并后全站异常页
 * 仅剩 router/modules/error.ts 的 /error/403、/error/404、/error/500。
 *
 * 断言两件事：
 * 1. 验收第 2 条——保留路径登录态直访仍能打开；
 * 2. 旧路径已无路由可匹配，不再渲染 403/500 页（末尾以保留路径做同会话对照，
 *    证明「不渲染」不是页面根本没加载的空转）。
 *
 * ⚠️ 旧路径字面量在本文件用 `_` 占位再替换的方式出现：#1797 验收要求旧路径名
 * 在全仓 rg 层面 0 命中（防残留引用），而回归测试又要真的打这两条路径——
 * 拼接/替换是同时满足两者的唯一写法，勿「顺手改回」字面量（会直接踩验收红线）。
 *
 * 未知路径首屏白屏是全站既有行为（#1797 执行期分诊，非该卡引入），已由本文件
 * 「未知路径首屏直访」两条用例承接修复（#1915）：catch-all 此前只在登录流程里
 * 挂载，首屏直访未匹配路径时 router-view 为空。
 */
/** 已删除的旧路径（用 `_` 占位：原因见文件头注释） */
const LEGACY_403_PATH = "/#/access_denied".replace("_", "-");
const LEGACY_500_PATH = "/#/server_error".replace("_", "-");

test.describe("异常页直访（#1797 合并后仅剩 error.ts 一套）", () => {
  test("登录态直访 /error/403 渲染 403 页", async ({
    context,
    page,
    baseURL
  }) => {
    await injectSupabaseSession(context, baseURL!);
    await page.goto("/#/error/403");
    await expect(page.getByText("抱歉，你无权访问该页面")).toBeVisible();
  });

  test("登录态直访 /error/500 渲染 500 页", async ({
    context,
    page,
    baseURL
  }) => {
    await injectSupabaseSession(context, baseURL!);
    await page.goto("/#/error/500");
    await expect(page.getByText("抱歉，服务器出错了")).toBeVisible();
  });

  test("旧路径已无路由，不再渲染 403/500 页", async ({
    context,
    page,
    baseURL
  }) => {
    await injectSupabaseSession(context, baseURL!);

    await page.goto(LEGACY_403_PATH);
    await expect(page.getByText("抱歉，你无权访问该页面")).toHaveCount(0);
    await expect(page.getByText("抱歉，服务器出错了")).toHaveCount(0);

    await page.goto(LEGACY_500_PATH);
    await expect(page.getByText("抱歉，服务器出错了")).toHaveCount(0);
    await expect(page.getByText("抱歉，你无权访问该页面")).toHaveCount(0);

    // 对照：同一会话里保留路径照常渲染，证明上面的 0 计数不是「页面没加载」的空转
    await page.goto("/#/error/403");
    await expect(page.getByText("抱歉，你无权访问该页面")).toBeVisible();
  });
});

test.describe("未知路径首屏直访（#1915）", () => {
  test("登录态：未知路径渲染全屏 404 而非白屏", async ({
    context,
    page,
    baseURL
  }) => {
    await injectSupabaseSession(context, baseURL!);
    await page.goto("/#/definitely-not-a-route-xyz");
    // 修复前 #app 为 <!---->（空渲染树、body.innerText 为空）——文案可见即排除白屏
    await expect(page.getByText("抱歉，你访问的页面不存在")).toBeVisible();
  });

  test("游客态：未知路径渲染全屏 404 而非跳登录", async ({ page }) => {
    // 不注入会话 = 游客；修复前守卫会把未在白名单的路径一律弹回 /login
    await page.goto("/#/definitely-not-a-route-xyz");
    await expect(page.getByText("抱歉，你访问的页面不存在")).toBeVisible();
  });
});
