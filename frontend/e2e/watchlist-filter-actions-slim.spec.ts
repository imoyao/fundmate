import { expect, test, type Page } from "@playwright/test";
import { injectSupabaseSession } from "./support/session";

/**
 * 自选筛选条「分组操作区 + 清除筛选」拆分回归网（#980 批 B2）。
 *
 * 本批把 `WatchlistFilterBar.vue` 里分组操作的三枚图标按钮整体搬进
 * `components/FilterGroupActions.vue`，把类型快捷的两条派生规则搬进
 * `quickTypeModel.ts` 纯函数。四层等价性脚本只能证明「类名/选择器/声明没丢」，
 * **证明不了连线还对**——下面是四条只有在真实浏览器里才咬得住的接线：
 *
 * 1. `can-manage-items` 是否真的跟着当前分组变（props 透传断了，按钮会永远藏/永远露）。
 * 2. 「常驻 DOM + .is-hidden」这条**只隐不撤**的约定是否还在（改回 v-if 会让槽位塌缩、
 *    整行抖动，这正是当初修过的 bug）。
 * 3. `emit('add')` 是否还接得到父级的 GroupFormDialog。
 * 4. 类型快捷的「单选覆盖式」是否还成立（再点当前项 → 取消回「全部」）。
 */

/** 视口取常规桌面档：本用例不涉及换行临界，只要真实布局 */
test.use({ viewport: { width: 1440, height: 900 } });

/** 自定义分组（触发「管理本组产品」的唯一条件，见 FilterGroupActions 注释） */
const CUSTOM_GROUP_LABEL = "脚踏实地";

const GROUPS = [
  {
    id: 1,
    key: "all",
    name: "全部",
    label: "全部",
    is_system: true,
    count: 30
  },
  {
    id: 2,
    key: "holding",
    name: "持仓",
    label: "持仓",
    is_system: true,
    count: 12
  },
  { id: 11, name: CUSTOM_GROUP_LABEL, is_system: false, count: 4 }
];

/** 4 个外露类型：默认档（stock/fund/etf/bond），胶囊栏共 5 项含「全部」 */
const QUICK_FILTERS = ["stock", "fund", "etf", "bond"];

async function stubWatchlist(page: Page) {
  // 兜底：未打桩的接口一律 404，避免经 vite 代理打到本机 8000 的真后端。
  // ⚠️ 必须用**锚定 host 的正则**（`**/api/**` 会把 /src/api/*.ts 的模块请求也吃掉）。
  // ⚠️ 后注册者先匹配：具体 stub 必须在兜底**之后**注册。
  await page.route(/^https?:\/\/[^/]+\/api\//, route =>
    route.fulfill({
      status: 404,
      json: { data: null, message: "e2e 未打桩", error_code: 40400 }
    })
  );
  await page.route("**/api/watchlist/groups/**", route =>
    route.fulfill({ status: 200, json: { data: GROUPS } })
  );
  await page.route("**/api/watchlist/items/**", route =>
    route.fulfill({ status: 200, json: { data: [], total: 0 } })
  );
  await page.route("**/api/watchlist/tags/**", route =>
    route.fulfill({ status: 200, json: { data: [] } })
  );
  await page.route("**/api/watchlist/holding-gaps/**", route =>
    route.fulfill({ status: 200, json: { data: [] } })
  );
  await page.route(
    "**/api/users/preferences/watchlist_quick_filters/**",
    route =>
      route.fulfill({
        status: 200,
        json: {
          data: {
            value: { filters: QUICK_FILTERS },
            updated_at: new Date().toISOString()
          }
        }
      })
  );
}

/** 打开自选页并等筛选条与胶囊真的渲染出来（防「槽是空的」假绿） */
async function openWatchlist(page: Page) {
  await page.goto("/#/watchlist");
  const row = page.locator(".filter-row");
  await expect(row).toBeVisible({ timeout: 90_000 });
  await expect(row.locator(".group-tab").first()).toBeVisible({
    timeout: 30_000
  });
  await expect(row.locator(".quick-pill").first()).toBeVisible({
    timeout: 30_000
  });
  return row;
}

test.describe("自选筛选条：分组操作区与清除筛选（#980 批 B2）", () => {
  // 冷启动时 vite 首次编译整套依赖可能超过默认 60s
  test.setTimeout(180_000);

  test.beforeEach(async ({ context, baseURL, page }) => {
    await injectSupabaseSession(context, baseURL!);
    await stubWatchlist(page);
  });

  test("分组操作区三枚图标齐全，且「管理本组产品」在系统分组下只隐不撤", async ({
    page
  }) => {
    const row = await openWatchlist(page);

    // 拆出的子组件根必须是 .group-actions（样式与布局归属，别退化成裸 fragment）
    const actions = row.locator(".group-actions");
    await expect(actions).toBeVisible();
    await expect(actions.locator(".group-tab-add")).toBeVisible();
    await expect(actions.locator(".manage-groups-btn")).toBeVisible();

    // 默认分组是系统分组「持仓」⇒ 「管理本组产品」必须**在 DOM 里但不可见**。
    // 注意 toHaveCount(1) + toBeHidden()：只隐不撤，槽位宽度恒定（#2354 / #2199）。
    const manageItems = actions.locator(".manage-group-items-btn");
    await expect(manageItems).toHaveCount(1);
    await expect(manageItems).toBeHidden();

    // 槽位不变式：切到自定义分组前后，分组操作区总宽必须一致
    // （若哪天改回 v-if，宽度会瞬间变化 → 整行重排，用户看到「页面跳一下」）
    const beforeWidth = (await actions.boundingBox())?.width ?? 0;

    await row.locator(".group-tab", { hasText: CUSTOM_GROUP_LABEL }).click();
    await expect(manageItems).toBeVisible();

    const afterWidth = (await actions.boundingBox())?.width ?? 0;
    expect(beforeWidth, "分组操作区宽度在切换分组后变化，槽位被撤掉了").toBe(
      afterWidth
    );
  });

  test("点「+」打开新建分组弹窗（子组件 emit 仍接得到父级弹窗）", async ({
    page
  }) => {
    const row = await openWatchlist(page);
    await row.locator(".group-tab-add").click();
    await expect(page.locator(".el-dialog__title")).toHaveText("新建分组");
  });

  test("清除筛选常驻 DOM：无筛选时隐、点类型胶囊后显（槽位不塌缩）", async ({
    page
  }) => {
    const row = await openWatchlist(page);

    const clear = row.locator(".clear-filters-btn");
    // 无任何筛选：按钮在 DOM 里但不可见
    await expect(clear).toHaveCount(1);
    await expect(clear).toBeHidden();
    const hiddenWidth = (await row.locator(".filter-bar__right").boundingBox())
      ?.width;

    // 施加类型筛选（点 ETF 胶囊）→ 清除按钮出现
    await row.locator(".quick-pill", { hasText: "ETF" }).click();
    await expect(clear).toBeVisible();

    // 右段宽度不变：按钮只切 opacity/visibility，不参与宽度变化
    const shownWidth = (await row.locator(".filter-bar__right").boundingBox())
      ?.width;
    expect(hiddenWidth, "清除按钮显隐改变了右段宽度，槽位被撤掉了").toBe(
      shownWidth
    );
  });

  test("首屏首个列表请求必须带上分组条件（#2329 不变量，拆分不改时序）", async ({
    page
  }) => {
    // 本批把整段 onMounted 搬进了 composables/useWatchlistPageInit.ts，**搬运最容易
    // 搬坏的就是顺序**：#2329 修的就是「并发发出 groups 与 items」——那一刻
    // allGroups 还是 []，系统分组的过滤条件会被静默丢掉，首屏「持仓」Tab 亮着
    // 却展示「全部」的内容（用户实测混进「基金经理」这类非持仓行）。
    //
    // 断言的是**数据层的可观测结果**，不是请求的发出顺序：初稿按 `page.on("request")`
    // 的先后做断言，实测同一份代码两次跑出不同的请求序（`groups,items,...` vs
    // `groups,groups`）——浏览器侧的请求派发顺序本身不保证稳定，那样的守卫会时红时绿。
    // 而「首个列表请求带了什么查询参数」是 fetchParams 在调用那一刻同步算出来的，确定性。
    const itemUrls: string[] = [];
    page.on("request", req => {
      const url = req.url();
      if (url.includes("/api/watchlist/items/")) itemUrls.push(url);
    });

    await openWatchlist(page);
    await expect
      .poll(() => itemUrls.length, { timeout: 15_000 })
      .toBeGreaterThan(0);

    const first = new URL(itemUrls[0]);
    expect(
      first.searchParams.get("status"),
      `首个列表请求未带分组条件（时序被打乱）：${itemUrls[0]}`
    ).toBe("HOLDING");
  });

  test("类型胶囊单选覆盖式：点其它类型为覆盖，再点当前项取消回「全部」", async ({
    page
  }) => {
    const row = await openWatchlist(page);

    const etfPill = row.locator(".quick-pill", { hasText: "ETF" });
    const bondPill = row.locator(".quick-pill", { hasText: "可转债" });
    const allPill = row.locator(".quick-pill", { hasText: "全部" });

    // 初始：「全部」高亮
    await expect(allPill).toHaveAttribute("aria-pressed", "true");

    // 点 ETF → 只 ETF 高亮（覆盖式，不是追加）
    await etfPill.click();
    await expect(etfPill).toHaveAttribute("aria-pressed", "true");
    await expect(allPill).toHaveAttribute("aria-pressed", "false");

    // 再点可转债 → 覆盖，ETF 取消高亮（证明 nextQuickSelection 走的是 [value] 分支）
    await bondPill.click();
    await expect(bondPill).toHaveAttribute("aria-pressed", "true");
    await expect(etfPill).toHaveAttribute("aria-pressed", "false");

    // 再点当前项 → 取消回「全部」
    await bondPill.click();
    await expect(allPill).toHaveAttribute("aria-pressed", "true");
    await expect(bondPill).toHaveAttribute("aria-pressed", "false");
  });
});
