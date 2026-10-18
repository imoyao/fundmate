import { expect, test } from "@playwright/test";
import { injectSupabaseSession } from "./support/session";

/**
 * 「问这个」行内入口（#1764）：持仓 / 自选行 → 账本精灵页预填。
 *
 * 对齐卡面验收：
 * 1. 行末入口点击后 `/#/agent/chat` 输入框已预填该标的提问模板，且**未发出任何请求**；
 * 2. 发送后首轮载荷携带标的代码（与该标的严格对应的载荷侧断言）；
 * 3. 刷新 `/agent/chat` 后上下文不产生错配——lay-content 以 fullPath 为 key，
 *    query 刻意保留（摘除会重挂载清空会话），刷新重预填的仍是**同一标的**。
 *
 * 为什么 mock 而不打真后端：本仓 E2E 的既有取舍是「不依赖后端」
 * （docs/dev/frontend-e2e.md）——本用例验证的是「入口 → 路由 query → 接收端
 * 预填 → 零发送」的纯前端链路，必须确定性；桩形状沿用
 * realtime-polling-lifecycle.spec.ts 的 catch-all + 分支模式。
 */

/** 自选行（display_name 是 WatchlistItem 的展示名，接收端 name 取它） */
const WATCH_ROW = {
  id: 1,
  symbol: "023887",
  name: "某某混合A",
  display_name: "某某混合A",
  asset_type: "fund",
  venue: "OTC",
  market: "CN",
  status: "WATCHING",
  is_pinned: false,
  favorite: false,
  group_ids: [],
  tag_ids: [],
  current_price: 0.95,
  change_pct: 1.05
};

/** 持仓行（盘点页 · 持仓明细表） */
const POSITION_ROW = {
  id: 11,
  symbol: "600519",
  name: "贵州茅台",
  type_label: "股票",
  asset_type: "stock",
  market: "CN_SH",
  account_name: "招商证券",
  quantity: 1_000_000,
  avg_price: 1500,
  current_price: 1600,
  currency: "CNY",
  price_date: null
};

test.describe("「问这个」行内入口（#1764）", () => {
  // 冷启动首次编译整套依赖可能超过默认 20s（同 interaction-regression）
  test.setTimeout(180_000);

  test.beforeEach(async ({ context, baseURL }) => {
    await injectSupabaseSession(context, baseURL!);
  });

  /** catch-all 桩：agentHits 记录对话接口命中数（验收「未发出任何请求」）；
   *  POST 对话分支另存载荷（验收「发送后首轮与标的严格对应」：载荷必须含代码） */
  function stubApi(
    page: import("@playwright/test").Page,
    rows: { items?: unknown[]; positions?: unknown[] }
  ) {
    let agentHits = 0;
    const chatPayloads: string[] = [];
    page.on("request", req => {
      if (/\/api\/agent\/chat\/?$/.test(new URL(req.url()).pathname)) {
        agentHits++;
      }
    });
    return page
      .route(
        url => new URL(url).pathname.startsWith("/api/"),
        async route => {
          const p = new URL(route.request().url()).pathname;
          if (
            /\/api\/agent\/chat\/?$/.test(p) &&
            route.request().method() === "POST"
          ) {
            chatPayloads.push(route.request().postData() ?? "");
            return route.fulfill({
              json: {
                data: {
                  type: "result",
                  content: "已根据所问标的整理完毕（E2E 桩响应）。",
                  data: {},
                  session_id: "sess-e2e-ask-1"
                },
                message: "ok"
              }
            });
          }
          if (p === "/api/watchlist/items/") {
            const isFirst =
              Number(
                new URL(route.request().url()).searchParams.get("page") ?? 1
              ) === 1;
            return route.fulfill({
              json: {
                data: isFirst && rows.items ? rows.items : [],
                total: isFirst && rows.items ? rows.items.length : 0,
                page: 1,
                per_page: 200,
                message: ""
              }
            });
          }
          if (p.startsWith("/api/positions")) {
            return route.fulfill({
              json: {
                data: rows.positions ?? [],
                total: rows.positions?.length ?? 0,
                page: 1,
                per_page: 20,
                message: ""
              }
            });
          }
          // 策略端点：消费方是 `!data || data.items.length` 判空（数组会让
          // data.items 为 undefined → render 抛 TypeError → 整页崩溃），
          // 桩必须回 data: null 的信封形状。
          if (p.startsWith("/api/strategy/")) {
            return route.fulfill({
              json: { data: null, total: 0, message: "" }
            });
          }
          return route.fulfill({ json: { data: [], total: 0, message: "" } });
        }
      )
      .then(() => ({ agentHits: () => agentHits, chatPayloads }));
  }

  test("自选行入口：预填 + 轻提示 + 零发送；刷新无残留", async ({ page }) => {
    const { agentHits, chatPayloads } = await stubApi(page, {
      items: [WATCH_ROW]
    });

    await page.goto("/#/watchlist", { waitUntil: "commit" });
    await expect(page.locator(".sidebar-container")).toBeVisible({
      timeout: 150_000
    });
    await expect(page.getByText("023887").first()).toBeVisible({
      timeout: 120_000
    });

    // EP 固定右列会克隆单元格（一份在固定包装层可见、一份主表内是占位），取可见的那份
    const btn = page.locator('button[aria-label="问这个"]:visible').first();
    await btn.hover();
    await btn.click();
    await expect(page).toHaveURL(/\/#\/agent\/chat\?/, { timeout: 60_000 });

    // 轻提示：进入后 3s 内可见（挂载即弹，断言在跳转后立刻开始等待）
    await expect(
      page.getByText("已带上 某某混合A（023887）上下文")
    ).toBeVisible({
      timeout: 60_000
    });
    // 预填模板逐字对齐卡面示例，且未自动发送
    await expect(page.getByPlaceholder(/Enter 发送/)).toHaveValue(
      "某某混合A（023887）最近的收益情况怎么样？",
      { timeout: 60_000 }
    );
    expect(agentHits()).toBe(0);

    // 主动发送（用户动作）：载荷必须携带标的代码——首轮与该标的严格对应的载荷侧断言
    await page.getByPlaceholder(/Enter 发送/).press("Enter");
    await expect(page.getByText("E2E 桩响应")).toBeVisible({
      timeout: 60_000
    });
    expect(chatPayloads).toHaveLength(1);
    expect(chatPayloads[0]).toContain("023887");

    // 刷新：query 保留（fullPath-keyed 布局下摘除会重挂载清空会话），
    // 重预填的仍是同一标的——不存在「串到别的标的」的错配
    await page.reload({ waitUntil: "commit" });
    await expect(page.getByPlaceholder(/Enter 发送/)).toHaveValue(
      "某某混合A（023887）最近的收益情况怎么样？",
      { timeout: 60_000 }
    );
    expect(agentHits()).toBe(1); // 仅这一次主动发送；刷新重预填不自动发送
  });

  test("持仓行入口：盘点页 → 精灵页预填且零发送", async ({ page }) => {
    const { agentHits } = await stubApi(page, { positions: [POSITION_ROW] });

    await page.goto("/#/inventory", { waitUntil: "commit" });
    await expect(page.locator(".sidebar-container")).toBeVisible({
      timeout: 150_000
    });
    // 持仓明细表渲染出该行（场景 A 默认激活）
    await expect(page.getByText("贵州茅台").first()).toBeVisible({
      timeout: 120_000
    });

    const btn = page.getByLabel("问这个：贵州茅台");
    await btn.hover();
    await btn.click();
    await expect(page).toHaveURL(/\/#\/agent\/chat\?/, { timeout: 60_000 });
    await expect(page.getByPlaceholder(/Enter 发送/)).toHaveValue(
      "贵州茅台（600519）最近的收益情况怎么样？",
      { timeout: 60_000 }
    );
    expect(agentHits()).toBe(0);
  });
});
