import { expect, test, type Page } from "@playwright/test";

import { injectSupabaseSession } from "./support/session";

/**
 * 「添加自选」弹窗回归网（#980 拆分后补的第一层行为判据）。
 *
 * 为什么这个弹窗此前没有测试：它的逻辑全是组件内闭包（搜索映射、查重时序、分组标签
 * 并集、提交事务），vitest 是 node 环境、无 jsdom，测不到。E2E 是唯一能证「拆完之后
 * 还是同一个东西」的层面——本轮把它从 1070 行拆成 4 个文件 + 1 个 composable，
 * 判据不能只有「模板逐字一致」：**props / v-model / emit 的接线只有跑起来才知道接没接对**。
 *
 * 因此这两个用例刻意不测「样式对不对」，只测三件拆分最容易打断的事：
 *
 * 1. **选择 → 卡片**（父 ↔ 搜索子组件的 v-model 双向）；
 * 2. **已在自选 → 隐藏置顶 / 换掉提交按钮**（父 ↔ 识别/编排子组件的 `alreadyExists` 派生）；
 * 3. **提交载荷**（父层事务没被子组件拆散：symbol / name / venue / add_reason / is_pinned）。
 *
 * 顺带钉住两条易被「顺手优化」破坏的既有口径：
 * - 组合类标的不展示平台原生码（`ZHxxxx` / `tgCode`）——见 @/constants/advisorPlatform；
 * - 无市场实体的标的 `venue` 必须是空串**原样透传**，不得兜底成 EXCHANGE（#1662）。
 */

const SEARCH_RESULTS = [
  {
    code: "ZH123456",
    name: "长赢指数投资",
    asset_type: "portfolio",
    market: "",
    venue: "",
    extra: { platform: "QIEMAN", host: "银行螺丝钉" }
  },
  {
    code: "159915",
    name: "创业板ETF",
    asset_type: "etf",
    market: "SZ",
    venue: "EXCHANGE",
    extra: {}
  }
];

const EXISTING_ROW = {
  id: 42,
  symbol: "159915",
  name: "创业板ETF",
  market: "SZ",
  asset_type: "etf",
  venue: "EXCHANGE",
  is_pinned: false
};

interface StubHandle {
  /** POST /api/watchlist/items/ 的请求体（JSON 字符串），按发生顺序 */
  createdBodies: string[];
}

/**
 * 打桩：`**\/api/**` 会连 vite 的源码模块请求一起吞掉（product-detail-dedup 踩过），
 * 故一律用锚定 host 的正则。未列出的接口回空信封，保证用例不依赖本机后端。
 */
async function stubApi(
  page: Page,
  opts: { existingSymbols?: string[] } = {}
): Promise<StubHandle> {
  const createdBodies: string[] = [];

  await page.route(/^https?:\/\/[^/]+\/api\//, async route => {
    const req = route.request();
    const url = new URL(req.url());
    const path = url.pathname;
    const method = req.method();

    if (path === "/api/search/assets/") {
      return route.fulfill({
        json: { data: SEARCH_RESULTS, message: "ok", error_code: 0 }
      });
    }
    if (path === "/api/watchlist/groups/") {
      return route.fulfill({
        json: {
          data: [
            { id: 7, name: "长期持有", color: "#3b82f6", is_system: false }
          ],
          message: "ok"
        }
      });
    }
    if (path === "/api/watchlist/tags/") {
      return route.fulfill({
        json: {
          data: [{ id: 3, name: "打新", color: "#f59e0b" }],
          message: "ok"
        }
      });
    }
    // 查重：`checkAssetExists` 打的就是「带 symbol 的 items 列表」
    if (path === "/api/watchlist/items/" && method === "GET") {
      const symbol = url.searchParams.get("symbol");
      const hit = !!symbol && (opts.existingSymbols ?? []).includes(symbol);
      return route.fulfill({
        json: {
          data: hit ? [EXISTING_ROW] : [],
          total: hit ? 1 : 0,
          page: 1,
          per_page: 1,
          message: ""
        }
      });
    }
    if (path === "/api/watchlist/items/" && method === "POST") {
      createdBodies.push(req.postData() ?? "");
      return route.fulfill({
        json: {
          data: { ...EXISTING_ROW, id: 901, symbol: "ZH123456" },
          message: "ok"
        }
      });
    }
    return route.fulfill({ json: { data: [], total: 0, message: "" } });
  });

  return { createdBodies };
}

/** 打开弹窗并选中一条搜索结果，返回弹窗定位器 */
async function openAndPick(page: Page, name: string) {
  await page.goto("/#/watchlist", { waitUntil: "commit" });
  const entry = page.getByRole("button", { name: "添加自选", exact: true });
  await expect(entry).toBeVisible({ timeout: 150_000 });
  await entry.click();

  const dialog = page.locator(".add-watchlist-dialog");
  await expect(dialog).toBeVisible();

  // EP 的可搜索下拉把「占位文案」渲染成 `.el-select__placeholder` 的 span，
  // input 上没有 placeholder 属性（getByPlaceholder 因此等不到），只能按容器取内部 input。
  const search = dialog.locator(".asset-search");
  await expect(search).toBeVisible();
  await search.click();
  await search.locator("input").first().fill(name);

  // 选项浮层被 teleport 到 body，只能从 page 级定位（popper-class 是拆分时原样搬走的）
  const option = page
    .locator(".add-asset-option-popper .el-select-dropdown__item")
    .filter({ hasText: name });
  await expect(option.first()).toBeVisible({ timeout: 30_000 });
  await option.first().click();
  return dialog;
}

test.describe.configure({ mode: "serial" });

test.describe("添加自选弹窗（#980 拆分）", () => {
  test.beforeEach(async ({ context, baseURL }) => {
    await injectSupabaseSession(context, baseURL!);
  });

  test("组合类标的：卡片三列正确、不出现平台原生码、提交载荷原样透传", async ({
    page
  }) => {
    test.setTimeout(240_000);
    const stub = await stubApi(page);

    const dialog = await openAndPick(page, "长赢指数投资");

    // ① 选择 → 卡片：这一步断的是父组件 ↔ 搜索子组件的 v-model 接线
    const card = dialog.locator(".selected-asset-card");
    await expect(card).toBeVisible({ timeout: 15_000 });
    await expect(card.locator(".selected-asset-card__name")).toHaveText(
      "长赢指数投资"
    );
    await expect(card.locator(".selected-asset-card__sub")).toHaveText(
      "且慢 · 银行螺丝钉"
    );

    // ② 组合类硬约束：平台原生码对用户无意义，不得出现在任何位置
    await expect(dialog).not.toContainText("ZH123456");

    // ③ `alreadyExists=false` 时置顶开关必须在（编排子组件的 showPin 接线）
    await expect(card.locator(".el-switch").first()).toBeVisible();
    // ④ 分组 / 标签两个选择器由编排子组件渲染（含行内「+」新建入口）
    await expect(card.locator(".tag-select")).toBeVisible();
    await expect(card.locator('button[aria-label="新建分组"]')).toBeVisible();

    // ⑤ 提交载荷：父层事务未被拆散
    await dialog.getByPlaceholder("为什么关注？（选填）").fill("e2e 拆分回归");
    await dialog.getByRole("button", { name: "添加自选", exact: true }).click();

    await expect.poll(() => stub.createdBodies.length).toBe(1);
    const body = JSON.parse(stub.createdBodies[0]);
    expect(body).toMatchObject({
      symbol: "ZH123456",
      name: "长赢指数投资",
      market: "",
      asset_type: "portfolio",
      // #1662：无市场实体的标的原样透传空串，不得兜底成 EXCHANGE
      venue: "",
      add_reason: "e2e 拆分回归",
      is_pinned: false
    });

    // ⑥ 提交成功后弹窗关闭（markClean → visible=false 这条顺序没被拆坏）
    await expect(dialog).toBeHidden({ timeout: 15_000 });
  });

  test("已在自选：隐藏置顶开关、提交按钮换成提示，且不发创建请求", async ({
    page
  }) => {
    test.setTimeout(240_000);
    const stub = await stubApi(page, { existingSymbols: ["159915"] });

    const dialog = await openAndPick(page, "创业板ETF");

    // 资产已存在于自选（查重走异步，等它落定）
    await expect(dialog.getByText("该资产已在自选列表中")).toBeVisible({
      timeout: 15_000
    });

    const card = dialog.locator(".selected-asset-card");
    // 有市场实体的标的（ETF/EXCHANGE）→ 场所标签「场内」照旧展示
    await expect(card.locator(".venue-tag")).toHaveText("场内");
    // `alreadyExists=true` → showPin=false：置顶开关不得渲染
    await expect(card.locator(".el-switch")).toHaveCount(0);
    // 主行改显「已在自选」标签
    await expect(card.getByText("已在自选")).toBeVisible();

    // 提交按钮消失 ⇒ 不可能发出创建请求（反向保护，避免用例空转）
    await expect(
      dialog.getByRole("button", { name: "添加自选", exact: true })
    ).toHaveCount(0);
    expect(stub.createdBodies).toHaveLength(0);
  });
});
