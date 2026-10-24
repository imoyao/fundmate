import { expect, test, type Page } from "@playwright/test";
import { injectSupabaseSession } from "./support/session";

/**
 * AI 批量导入弹窗回归网（#980 拆分后补的第一层行为判据）。
 *
 * 为什么这个弹窗此前没有测试：它的逻辑全在组件闭包里（额度三态派生、识别失败的四路
 * 错误文案、已存在探测的串行时序、导入载荷的兜底规则），vitest 是 node 环境、无 jsdom，
 * 测不到。本轮把它从 951 行拆成 3 个组件 + 4 个 composable + 1 个纯函数模块，
 * 判据不能只有「模板逐字一致」——**props / v-model / emit 的接线只有跑起来才知道接没接对**。
 *
 * 因此这两个用例只测拆分最容易打断的两件事：
 * 1. **额度三态的派生**（`useOcrQuota`）：弹窗顶部通栏的文案 / 按钮可用性同源，拆开后两边
 *    读的是同一个 ref，不该出现「提示说用尽、按钮还能点」；
 * 2. **识别 → 候选 → 导入载荷**（`useOcrRecognize` + `OcrCandidateList` + `useOcrImport`）：
 *    已存在置灰、默认勾选、分组 id 进请求体、完成后复位为「开始识别」。
 */

const PARSE_ITEMS = [
  {
    code: "110011",
    name: "易方达中小盘",
    symbol: "110011",
    type: "fund",
    venue: "OTC"
  },
  {
    code: "159915",
    name: "创业板ETF",
    symbol: "SZ159915",
    type: "etf",
    market: "SZ",
    venue: "EXCHANGE"
  }
];

interface StubHandle {
  /** POST /api/watchlist/items/ 的请求体（JSON 字符串），按发生顺序 */
  createdBodies: string[];
}

/**
 * 打桩：锚定 host 的正则（`**\/api/**` 会连 vite 的源码模块请求一起吞掉，
 * product-detail-dedup 踩过）。未列出的接口回空信封，保证用例不依赖本机后端。
 */
async function stubApi(
  page: Page,
  opts: { remaining: number; existingSymbols?: string[] }
): Promise<StubHandle> {
  const createdBodies: string[] = [];

  await page.route(/^https?:\/\/[^/]+\/api\//, async route => {
    const req = route.request();
    const url = new URL(req.url());
    const path = url.pathname;
    const method = req.method();

    if (path === "/api/usage/ocr_import/" && method === "GET") {
      return route.fulfill({
        json: {
          data: { remaining: opts.remaining, quota: 5 },
          message: "ok"
        }
      });
    }
    if (path === "/api/watchlist/groups/" && method === "GET") {
      return route.fulfill({
        json: {
          data: [
            { id: 7, name: "长期持有", color: "#3b82f6", is_system: false },
            { id: 1, name: "全部", color: null, is_system: true }
          ],
          message: "ok"
        }
      });
    }
    if (path === "/api/ocr/parse/" && method === "POST") {
      return route.fulfill({
        json: {
          data: {
            items: PARSE_ITEMS,
            usage: { remaining: opts.remaining - 1 }
          },
          message: "ok"
        }
      });
    }
    // 查重：逐条打「带 symbol 的 items 列表」
    if (path === "/api/watchlist/items/" && method === "GET") {
      const symbol = url.searchParams.get("symbol");
      const hit = !!symbol && (opts.existingSymbols ?? []).includes(symbol);
      return route.fulfill({
        json: {
          data: hit
            ? [
                {
                  id: 42,
                  symbol: "SZ159915",
                  name: "创业板ETF",
                  asset_type: "etf",
                  venue: "EXCHANGE"
                }
              ]
            : [],
          total: hit ? 1 : 0,
          page: 1,
          per_page: 1,
          message: ""
        }
      });
    }
    if (path === "/api/watchlist/items/" && method === "POST") {
      createdBodies.push(req.postData() ?? "");
      return route.fulfill({ json: { data: { id: 901 }, message: "ok" } });
    }
    return route.fulfill({ json: { data: [], total: 0, message: "" } });
  });

  return { createdBodies };
}

/** 打开弹窗（自选页头部的「AI 导入」圆形按钮） */
async function openDialog(page: Page) {
  await page.goto("/#/watchlist", { waitUntil: "commit" });
  const entry = page.getByRole("button", { name: "AI 导入" });
  await expect(entry).toBeVisible({ timeout: 150_000 });
  await entry.click();
  const dialog = page.locator(".ocr-import-dialog");
  await expect(dialog).toBeVisible();
  return dialog;
}

test.describe("AI 批量导入弹窗", () => {
  // 首个用例要等 dev server 冷启动 + 自选页首帧（同 add-watchlist-modal 的取舍）
  test.describe.configure({ mode: "serial" });

  test("识别 → 已存在置灰 → 勾选分组 → 导入载荷口径正确", async ({
    page,
    context,
    baseURL
  }) => {
    test.setTimeout(240_000);
    await injectSupabaseSession(context, baseURL!);
    const stub = await stubApi(page, {
      remaining: 4,
      existingSymbols: ["SZ159915"]
    });

    const dialog = await openDialog(page);

    // 额度 4/5 → 紧张态（<=2 才是「紧张」，4 应为正常态，不显示提示）
    await expect(dialog.getByText("今日 AI 导入额度剩余")).toBeVisible();
    await expect(dialog.getByText("额度紧张，谨慎使用")).toHaveCount(0);

    // 切到「粘贴文本」：分段控件是 role=tab，不是 button
    await dialog.getByRole("tab", { name: "粘贴文本" }).click();
    const textarea = dialog.getByPlaceholder("在此粘贴基金/股票代码，一行一个");
    await expect(textarea).toBeVisible();
    await textarea.fill("110011 易方达中小盘\n159915 创业板ETF");

    await dialog.getByRole("button", { name: "开始识别" }).click();

    // 候选：2 条；已存在的置灰且默认不勾 → 只剩 1 条可导入
    await expect(dialog.getByText("识别到 2 条，可勾选导入")).toBeVisible({
      timeout: 30_000
    });
    const existsRow = dialog.locator(".candidate-row.is-exists");
    await expect(existsRow).toHaveCount(1);
    await expect(existsRow.getByText("已在自选")).toBeVisible();
    await expect(existsRow.locator("input[type=checkbox]")).toBeDisabled();
    await expect(
      dialog.getByRole("button", { name: "导入选中（1）" })
    ).toBeVisible();

    // 分组：只列自定义分组（系统分组「全部」不应作为可选项出现）
    await dialog.locator(".import-groups__select").click();
    const option = page.locator(".el-select-dropdown__item", {
      hasText: "长期持有"
    });
    await expect(option).toBeVisible();
    await option.click();
    await expect(
      page.locator(".el-select-dropdown__item", { hasText: "全部" })
    ).toHaveCount(0);
    await page.keyboard.press("Escape");

    await dialog.getByRole("button", { name: "导入选中（1）" }).click();

    // 载荷：symbol 走后端反查的标准化代码、类型/渠道透传、分组进 group_ids
    await expect.poll(() => stub.createdBodies.length).toBe(1);
    const body = JSON.parse(stub.createdBodies[0]);
    expect(body).toMatchObject({
      symbol: "110011",
      name: "易方达中小盘",
      asset_type: "fund",
      venue: "OTC",
      add_reason: "AI 批量导入",
      group_ids: [7]
    });

    // 导入成功后：提示一条成功，父层收到 imported 即关闭弹窗并刷新自选列表
    await expect(page.getByText("导入成功 1 条")).toBeVisible();
    await expect(dialog).toBeHidden();
  });

  test("额度用尽：通栏说清原因，识别按钮不可点（派生量同源）", async ({
    page,
    context,
    baseURL
  }) => {
    test.setTimeout(240_000);
    await injectSupabaseSession(context, baseURL!);
    await stubApi(page, { remaining: 0 });

    const dialog = await openDialog(page);

    await expect(dialog.getByText("额度已用尽，请明日再试")).toBeVisible();
    await expect(dialog.locator(".usage-banner.is-used-up")).toHaveCount(1);

    // 即使有内容，识别按钮也必须不可点（额度判断在读内容之前）
    await dialog.getByRole("tab", { name: "粘贴文本" }).click();
    await dialog
      .getByPlaceholder("在此粘贴基金/股票代码，一行一个")
      .fill("110011 易方达中小盘");
    await expect(
      dialog.getByRole("button", { name: "开始识别" })
    ).toBeDisabled();
  });
});
