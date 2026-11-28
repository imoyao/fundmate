import { expect, test, type Page } from "@playwright/test";
import { injectSupabaseSession } from "./support/session";

/**
 * 复盘页「组合档」接线回归网（D2 / D135）。
 *
 * ## 为什么必须真点一次
 *
 * 组合档在页面上表现正常、`vue-tsc` 全绿、单测也绿，仍可能有三种静默失效——
 * 它们都只在**真渲染 + 真发请求**时暴露，且都表现为「看起来没数据」而不是报错：
 *
 * 1. **切换器下拉恒空**：`ScopeBar` 内部按档位在 `ledgers` / `portfolios` 之间挑。
 *    宿主若把「已按档位切过一次」的单份清单喂进 `:ledgers`，组合档读到的是没被
 *    赋值的 `portfolios` ⇒ 下拉空着并显示「暂无组合」。
 * 2. **档位开了、区块没收到**：页面逐块写 `:ledger-id` 时组合 id 无人接收，区块
 *    退回家庭级 —— 标签写着「组合」，数字是全家的（#2595 原形）。
 * 3. **组合 id 被当账户 id 发出去**：半迁移态最危险，后端要么 400、要么命中另一
 *    个账户，数字错得毫无痕迹。
 *
 * 判据落在**请求 URL** 上（第 2、3 条）而不是 DOM 文案上：文案能靠标签写对而数字
 * 是错的，URI 里的 `portfolio_id` / `ledger_id` 不会骗人。
 *
 * 接口一律打桩（`e2e` 不依赖后端，见 `playwright.config.ts` 注释）：
 * `/api/ledgers/`、`/api/portfolios/` 给出清单，其余 `/api/` 一律 404——
 * 各区块自己降级成空态，不影响本次要验的接线。
 */

const LEDGERS = [
  { id: 1, name: "支付宝-基金" },
  { id: 2, name: "天天基金-基金" }
];

const PORTFOLIOS = [
  { id: 7, name: "稳健组合" },
  { id: 8, name: "进攻组合" }
];

/**
 * 打桩并返回「本页发出的所有 /api/ 请求 URL」。
 *
 * ⚠️ 路由必须锚定 host 并**先注册 catch-all**：Playwright 后注册的处理器先匹配，
 * 宽 glob 还会把 vite 的源码模块请求（`/src/api/ledger.ts`）一起拦掉、页面直接白屏。
 */
async function stubApis(page: Page): Promise<string[]> {
  const urls: string[] = [];
  page.on("request", req => {
    const u = req.url();
    if (u.includes("/api/")) urls.push(u);
  });

  await page.route(/^https?:\/\/[^/]+\/api\//, route =>
    route.fulfill({
      status: 404,
      json: { data: null, message: "e2e 未打桩", error_code: 40400 }
    })
  );
  await page.route(/^https?:\/\/[^/]+\/api\/ledgers\/?(\?.*)?$/, route =>
    route.fulfill({ status: 200, json: { data: LEDGERS } })
  );
  await page.route(/^https?:\/\/[^/]+\/api\/portfolios\/?(\?.*)?$/, route =>
    route.fulfill({ status: 200, json: { data: PORTFOLIOS } })
  );
  return urls;
}

/** 打开复盘页并等口径切换条渲染（骨架屏互斥，`scopeKinds.length > 1` 才出现） */
async function openAnalysis(page: Page) {
  await page.goto("/#/analysis");
  const bar = page.locator(".analysis-scope .scope-bar");
  await expect(bar).toBeVisible({ timeout: 90_000 });
  return bar;
}

/**
 * 首个用例要等 vite 冷编译整页（本机实测 35~52s），贴着默认 60s 超时；CI 机器更慢，
 * 故本文件统一放宽——这里验的是接线，不该由冷启动速度决定红绿。
 */
test.describe.configure({ timeout: 150_000 });

test.beforeEach(async ({ context, baseURL }) => {
  await injectSupabaseSession(context, baseURL!);
});

test("口径切换器三档齐全，第三档是「组合」", async ({ page }) => {
  await stubApis(page);
  const bar = await openAnalysis(page);

  const tabs = bar.locator('[role="tab"]');
  await expect(tabs).toHaveCount(3);
  await expect(tabs.nth(0)).toHaveText("全家庭");
  await expect(tabs.nth(1)).toHaveText("单账户");
  // 这一档就是本 PR 开出来的：能力表十块全部三档，交集才包含 portfolio
  await expect(tabs.nth(2)).toHaveText("组合");
});

test("切到组合档：下拉列出组合，而不是「暂无组合」", async ({ page }) => {
  await stubApis(page);
  const bar = await openAnalysis(page);

  await bar.locator('[role="tab"]', { hasText: "组合" }).click();

  // 组合清单已预热（`Promise.allSettled` 同时取账户与组合），切档即刻可选
  const select = bar.locator(".scope-bar__select");
  await expect(select).toBeVisible();
  // 空态提示不该出现——它只在「这一档确实没有对象」时才对
  await expect(bar.locator(".scope-bar__empty")).toHaveCount(0);

  await select.click();
  const options = page.locator(".el-select-dropdown__item");
  await expect(options).toHaveCount(2);
  await expect(options.nth(0)).toHaveText("稳健组合");
  await expect(options.nth(1)).toHaveText("进攻组合");
});

test("选中组合后：区块按组合取数（portfolio_id），且不把组合 id 当账户 id", async ({
  page
}) => {
  const urls = await stubApis(page);
  const bar = await openAnalysis(page);

  // 首屏是家庭档，区块照常渲染（此时没有「请先选择」的提示）
  await expect(page.locator(".analysis-scope-empty")).toHaveCount(0);

  await bar.locator('[role="tab"]', { hasText: "组合" }).click();

  // 切到组合档但还没选组合：一个区块都不渲染，只留一句「请选择」。
  // 这条是「不让人对着错数」的现场判据——空 props 在面板里等于家庭级，
  // 若此时仍渲染区块，「组合」标签下摆的就是全家的钱（#2595 原形）。
  await expect(page.locator(".analysis-scope-empty")).toBeVisible();

  await bar.locator(".scope-bar__select").click();
  await page
    .locator(".el-select-dropdown__item", { hasText: "稳健组合" })
    .click();

  // 净值走势直接渲染（不在 LazySection 里），选完即发快照请求
  await expect
    .poll(
      () =>
        urls.filter(
          u =>
            u.includes("/api/summary/snapshots/") &&
            u.includes("portfolio_id=7")
        ).length,
      { timeout: 30_000, message: "组合档没有按 portfolio_id 取快照" }
    )
    .toBeGreaterThan(0);

  // 反向：任何请求都不该出现 ledger_id=7（组合 id 落到账户参数上的错法）
  expect(
    urls.filter(u => u.includes("ledger_id=7")),
    "组合 id 被当成账户 id 发了出去"
  ).toEqual([]);
});
