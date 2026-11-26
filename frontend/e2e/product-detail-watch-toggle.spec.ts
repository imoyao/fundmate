import { expect, test, type Page } from "@playwright/test";
import { injectSupabaseSession } from "./support/session";

/**
 * 产品详情页 · 页头「自选」控件（`ProductWatchToggle`）。
 *
 * 用户实测（2026-11-26）：「没办法取消自选，没办法显示 tag，我不知道它的意义是什么。」
 * 在此之前自选状态只是识别卡里一行**死文字**。本文件钉四件事：
 *
 * 1. 未登录（`in_watchlist` 为 null）**不渲染**控件——不给点下去必然 401 的按钮；
 * 2. 未关注时是「自选」，点开添加弹窗**已预填本产品**（且不白拉一次自选查询）；
 * 3. 已关注时按钮与面板都要能看见**分组与标签**（这正是「没办法显示 tag」）；
 * 4. 取消自选的两种走法：**有分组 / 标签要先确认**（归类不可自动恢复），
 *    没有就直接删。反向验证：把 `needsConfirm` 改成恒 false，第 4 条会红；
 *    改成恒 true，第 5 条会红。
 *
 * 接口全部 `page.route` 打桩（docs/dev/frontend-e2e.md §7），不依赖后端。
 */

const NAME = "永赢北证50成份指数发起C";
const SYMBOL = "023887";

interface WatchItemStub {
  id: number;
  symbol: string;
  display_name: string;
  market: string;
  asset_type: string;
  venue: string;
  group_ids: number[];
  group_names: string[];
  tag_ids: number[];
  status: string;
  favorite: boolean;
  is_pinned: boolean;
}

/** 一条自选项；只有分组 / 标签按用例不同 */
function watchItem(overrides: Partial<WatchItemStub> = {}): WatchItemStub {
  return {
    id: 7,
    symbol: SYMBOL,
    display_name: NAME,
    market: "CN_A",
    asset_type: "fund",
    venue: "OTC",
    group_ids: [],
    group_names: [],
    tag_ids: [],
    status: "WATCHING",
    favorite: false,
    is_pinned: false,
    ...overrides
  };
}

interface StubOptions {
  /** resolve 返回的 in_watchlist；null = 未登录 */
  inWatchlist: boolean | null;
  /** 自选列表里已有的项（GET items 的返回） */
  items?: WatchItemStub[];
}

interface StubHandle {
  /** GET /watchlist/items/ 的调用次数（钉「未关注时不白拉」） */
  itemQueries: () => number;
  /** DELETE /watchlist/items/<id>/ 被调用过的 id */
  deletedIds: number[];
}

async function stubProductApis(
  page: Page,
  options: StubOptions
): Promise<StubHandle> {
  const items = [...(options.items ?? [])];
  let itemQueries = 0;
  const deletedIds: number[] = [];

  // 兜底：未打桩的接口一律 404，避免请求经 vite 代理打到本机真后端
  await page.route(/^https?:\/\/[^/]+\/api\//, route =>
    route.fulfill({
      status: 404,
      json: { data: null, message: "e2e 未打桩", error_code: 40400 }
    })
  );

  await page.route("**/api/utils/enums/**", route =>
    route.fulfill({
      status: 200,
      json: {
        data: {
          asset_type: { fund: "基金", stock: "股票" },
          market: { CN_A: "A股" },
          venue: { OTC: "场外", EXCHANGE: "场内" }
        },
        message: "ok"
      }
    })
  );

  await page.route("**/api/products/resolve/**", route =>
    route.fulfill({
      status: 200,
      json: {
        data: {
          symbol: SYMBOL,
          asset_type: "fund",
          market: "CN_A",
          venue: "OTC",
          display_name: NAME,
          in_watchlist: options.inWatchlist,
          // 不持有：持仓区块不渲染，本文件只关心页头控件
          has_position: false,
          source: "catalog"
        },
        message: "ok"
      }
    })
  );

  await page.route(/\/api\/watchlist\/items/, async route => {
    const request = route.request();
    const method = request.method();
    const path = new URL(request.url()).pathname;

    if (method === "GET") {
      itemQueries += 1;
      await route.fulfill({
        status: 200,
        json: { data: items, total: items.length, message: "ok" }
      });
      return;
    }

    if (method === "POST") {
      const created = watchItem({ id: 101 });
      items.push(created);
      await route.fulfill({
        status: 200,
        json: { data: created, message: "ok" }
      });
      return;
    }

    if (method === "DELETE") {
      const id = Number(path.match(/items\/(\d+)/)?.[1] ?? 0);
      deletedIds.push(id);
      const index = items.findIndex(item => item.id === id);
      if (index >= 0) items.splice(index, 1);
      await route.fulfill({ status: 200, json: { data: null, message: "ok" } });
      return;
    }

    await route.fulfill({
      status: 404,
      json: { data: null, message: "not stubbed" }
    });
  });

  await page.route(/\/api\/watchlist\/tags/, route =>
    route.fulfill({
      status: 200,
      json: { data: [{ id: 11, name: "低估值", color: null }], message: "ok" }
    })
  );

  return { itemQueries: () => itemQueries, deletedIds };
}

const heading = (page: Page) => page.getByRole("heading", { level: 1 });

test.describe("产品详情页 · 页头自选控件", () => {
  // vite 冷启动首次编译整套依赖可能超过默认 60s
  test.setTimeout(180_000);

  test("未登录：不渲染控件（不给点了必然 401 的入口）", async ({
    context,
    baseURL,
    page
  }) => {
    await injectSupabaseSession(context, baseURL!);
    await stubProductApis(page, { inWatchlist: null });
    await page.goto(`/#/fund/${SYMBOL}`);
    await expect(heading(page)).toContainText(NAME, { timeout: 60_000 });

    // 「未知」不是「没关注」——整块不渲染
    await expect(page.locator(".watch-toggle")).toHaveCount(0);
  });

  test("未关注：按钮是「自选」，点开弹窗已预填本产品且不白查一次", async ({
    context,
    baseURL,
    page
  }) => {
    await injectSupabaseSession(context, baseURL!);
    const stub = await stubProductApis(page, { inWatchlist: false });
    await page.goto(`/#/fund/${SYMBOL}`);
    await expect(heading(page)).toContainText(NAME, { timeout: 60_000 });

    const btn = page.locator(".watch-toggle__btn");
    await expect(btn).toContainText("自选");
    await expect(btn).not.toContainText("已关注");
    // 未关注态没有 item 可查——白拉一次是纯浪费（每次打开详情页都付）
    expect(stub.itemQueries()).toBe(0);

    await btn.click();
    const dialog = page.locator(".add-watchlist-dialog");
    await expect(dialog).toBeVisible();
    // 预填：已选资产卡与搜索框都已经是这只基金，用户不必再搜一遍自己的标的
    await expect(dialog.locator(".selected-asset-card")).toContainText(NAME);
    await expect(dialog.locator(".asset-search")).toContainText(NAME);
  });

  test("已关注：按钮带分组名，面板列出分组与标签", async ({
    context,
    baseURL,
    page
  }) => {
    await injectSupabaseSession(context, baseURL!);
    await stubProductApis(page, {
      inWatchlist: true,
      items: [
        watchItem({
          group_ids: [3],
          group_names: ["长期持有"],
          tag_ids: [11]
        })
      ]
    });
    await page.goto(`/#/fund/${SYMBOL}`);
    await expect(heading(page)).toContainText(NAME, { timeout: 60_000 });

    const btn = page.locator(".watch-toggle__btn");
    await expect(btn).toContainText("已关注");
    // 按钮上直接回答「在哪个分组」，不必先点开
    await expect(btn).toContainText("长期持有");

    await btn.click();
    const panel = page.locator(".watch-panel");
    await expect(panel).toBeVisible();
    await expect(panel).toContainText("长期持有");
    // 标签名要显示出来——用户原话就是「没办法显示 tag」
    await expect(panel).toContainText("低估值");
    await expect(panel).toContainText("在自选中管理");
  });

  test("取消自选：有分组标签时先确认，确认后真的删掉", async ({
    context,
    baseURL,
    page
  }) => {
    await injectSupabaseSession(context, baseURL!);
    const stub = await stubProductApis(page, {
      inWatchlist: true,
      items: [watchItem({ group_ids: [3], group_names: ["长期持有"] })]
    });
    await page.goto(`/#/fund/${SYMBOL}`);
    await expect(heading(page)).toContainText(NAME, { timeout: 60_000 });

    await page.locator(".watch-toggle__btn").click();
    await page.locator(".watch-panel__remove").click();

    // 归类是用户手工打的，重建自选不会恢复 ⇒ 必须先说清代价
    const box = page.locator(".el-message-box");
    await expect(box).toBeVisible();
    await expect(box).toContainText("分组与标签会一并解除");

    await box.getByRole("button", { name: "取消自选" }).click();
    await expect(page.locator(".watch-toggle__btn")).toContainText("自选");
    expect(stub.deletedIds).toEqual([7]);
  });

  test("取消自选：没有分组标签时直接删，不弹确认", async ({
    context,
    baseURL,
    page
  }) => {
    await injectSupabaseSession(context, baseURL!);
    const stub = await stubProductApis(page, {
      inWatchlist: true,
      items: [watchItem({ id: 9 })]
    });
    await page.goto(`/#/fund/${SYMBOL}`);
    await expect(heading(page)).toContainText(NAME, { timeout: 60_000 });

    await page.locator(".watch-toggle__btn").click();
    await page.locator(".watch-panel__remove").click();

    // 只是一个代码，加回来零成本——不该拿确认框拦人
    await expect(page.locator(".el-message-box")).toHaveCount(0);
    await expect(page.locator(".watch-toggle__btn")).toContainText("自选");
    expect(stub.deletedIds).toEqual([9]);
  });

  test("加入自选：提交成功后按钮立即变成「已关注」", async ({
    context,
    baseURL,
    page
  }) => {
    await injectSupabaseSession(context, baseURL!);
    await stubProductApis(page, { inWatchlist: false });
    await page.goto(`/#/fund/${SYMBOL}`);
    await expect(heading(page)).toContainText(NAME, { timeout: 60_000 });

    await page.locator(".watch-toggle__btn").click();
    const dialog = page.locator(".add-watchlist-dialog");
    await expect(dialog).toBeVisible();
    await dialog.getByRole("button", { name: "添加自选" }).click();

    await expect(dialog).toBeHidden();
    await expect(page.locator(".watch-toggle__btn")).toContainText("已关注");
  });
});
