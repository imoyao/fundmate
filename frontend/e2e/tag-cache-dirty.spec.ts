import { expect, test } from "@playwright/test";

import { injectSupabaseSession } from "./support/session";

/**
 * 标签栏空白块回归网（2026-10-30 用户截图）。
 *
 * 缺陷形态：顶部标签栏出现一个**没有文字的标签块**——宽度只剩关闭按钮、能点、
 * 控制台报 `Cannot read properties of undefined (reading 'length')`。
 *
 * 成因：开启「标签页缓存」后 `multiTags` 存在 localStorage（`responsive-tags`），
 * 这份数组**跨版本存活**；历史条目没有 `meta.title` 时，旧渲染 `{{ item.meta.title }}`
 * 会画出一个空白块，旧判空 `tagVal?.meta?.title.length` 还会在 `.length` 上抛错。
 *
 * 为什么必须是 E2E：脏数据只存在于**用户本地缓存**，单测与干净的 CI 环境永远造不出来。
 * 这里主动把脏缓存塞进 localStorage，复现用户现场。
 */

const TAGS_KEY = "responsive-tags";
const CONFIGURE_KEY = "responsive-configure";

test("历史脏标签缓存：不渲染空白块，且缓存被自愈写回", async ({
  context,
  page,
  baseURL
}) => {
  const pageErrors: string[] = [];
  page.on("pageerror", e => pageErrors.push(e.message));

  await injectSupabaseSession(context, baseURL!);

  // 复刻用户现场：开启标签缓存 + 缓存里混着「没有标题」的历史条目
  await page.addInitScript(
    ([tagsKey, cfgKey]) => {
      localStorage.setItem(cfgKey, JSON.stringify({ multiTagsCache: true }));
      localStorage.setItem(
        tagsKey,
        JSON.stringify([
          { path: "/welcome", name: "Welcome", meta: { title: "首页" } },
          {
            path: "/watchlist",
            name: "Watchlist",
            meta: { title: "我的自选" }
          },
          // ↓ 截图里那个空白标签：有 path、meta 在、title 缺失
          { path: "/asset/strategies", name: "Strategies", meta: {} },
          // ↓ 标题是空字符串：同样渲染成空白块
          {
            path: "/asset/recurring",
            name: "AssetRecurring",
            meta: { title: "" }
          }
        ])
      );
    },
    [TAGS_KEY, CONFIGURE_KEY]
  );

  await page.goto("/#/welcome");
  await page.waitForSelector(".sidebar-container", { timeout: 30_000 });
  await expect(
    page.locator(".scroll-container .tag-title").first()
  ).toBeVisible();

  // 判据一：渲染出来的每个标签都有文字（不能有空白块）
  const titles = (
    await page.locator(".scroll-container .tag-title").allInnerTexts()
  ).map(s => s.trim());
  expect(titles).toEqual(["首页", "我的自选"]);

  // 判据二：脏条目被清洗并写回缓存（只清一次，不会每次刷新又长回来）
  const cached = await page.evaluate(
    key => JSON.parse(localStorage.getItem(key) ?? "[]"),
    TAGS_KEY
  );
  expect(cached.map((t: any) => t.path)).toEqual(["/welcome", "/watchlist"]);

  // 判据三：不再有「读不到 title」的运行时异常
  expect(pageErrors).toEqual([]);
});
