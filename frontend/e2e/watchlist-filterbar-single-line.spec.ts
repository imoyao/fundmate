import { expect, test, type Page } from "@playwright/test";
import { injectSupabaseSession } from "./support/session";

/**
 * 自选页筛选行**单行不换行**回归网（#2329 正文第二个问题）。
 *
 * 症状（用户截图）：分组胶囊 + 品类胶囊 + 固定操作段挤在一行；当分组变多
 * （自定义分组累积）且品类全量外露时，右段（+ / 📁 / 📄 / 筛选）被**甩到第二行**，
 * 整页高度跳变、观感「怪异」。
 *
 * 根因（纯几何，静态检查与 jsdom 单测都看不见）：
 * `.filter-row` 是 `flex-wrap: wrap`，两个弹性区此前都是 `flex: 1 1 auto`
 * ⇒ `flex-basis: auto` ⇒ **hypothetical size = 内容宽**。而 flexbox 的换行判定
 * 发生在**收缩之前**：先按 hypothetical size 决定放哪一行，放不下就换行，
 * 压根不会先尝试收缩。于是判定条件是「两区内容宽 + 右段 > 容器宽」——
 * 实测只差约 60px，于是它随窗口宽度时有时无。
 *
 * 修复方向：`flex-basis` 改 0（`flex: 3 1 0%` / `flex: 2 1 0%`），hypothetical
 * size 恒为 0 ⇒ 换行判定永不成立，改由 `flex-grow` 分剩余空间、横向滚动兜底。
 *
 * 断言的是**不变式**（所有子项同一行），不是某个像素值——但必须先证明
 * 分组/品类**真的渲染出来了**，否则「没有第二行」会因为槽是空的而假绿
 * （与 section-header-action-overflow.spec.ts 同一纪律）。
 */

/** 故意取「侧边栏占位后可用宽度偏窄」的视口，贴近用户截图的临界状态 */
test.use({ viewport: { width: 1366, height: 900 } });

/**
 * 用户截图里的真实触发场景：**自定义分组** + 品类全量外露。
 *
 * ⚠️ 绝不能用默认的「持仓」分组当场景：#2329-a 已把持仓分组下的品类胶囊按
 * `narrowToHolding` 收窄到 5 项 + 「全部」，内容宽不够大 ⇒ **旧写法在该视口下
 * 也不换行** ⇒ 守门会假绿（探针实测 P1/P2 双双 MISS，只有去掉 max-width 的
 * P3 才咬住）。用户截图 3 恰恰是自定义分组（脚踏实地）那一档，必须复现它。
 */
const CUSTOM_GROUP_LABEL = "脚踏实地";

/** 10 个系统/自定义分组：复现用户「分组累积到 9 个」的真实形态 */
const GROUPS = [
  {
    id: 1,
    key: "all",
    name: "全部",
    label: "全部",
    is_system: true,
    count: 183
  },
  {
    id: 2,
    key: "holding",
    name: "持仓",
    label: "持仓",
    is_system: true,
    count: 142
  },
  {
    id: 3,
    key: "watching",
    name: "观察中",
    label: "观察中",
    is_system: true,
    count: 40
  },
  {
    id: 4,
    key: "favorite",
    name: "特别关注",
    label: "特别关注",
    is_system: true,
    count: 5
  },
  { id: 11, name: "仰望星空", is_system: false, count: 23 },
  { id: 12, name: "脚踏实地", is_system: false, count: 11 },
  { id: 13, name: "稳稳的幸福", is_system: false, count: 1 },
  { id: 14, name: "测试", is_system: false, count: 1 }
];

/** 全量外露类型：胶囊从 4 个涨到 11 个（#1285 加了 manager/portfolio 后的上限） */
const ALL_QUICK_FILTERS = [
  "stock",
  "fund",
  "etf",
  "bond",
  "index",
  "manager",
  "portfolio",
  "money_fund",
  "crypto",
  "reverse_repo"
];

async function stubWatchlist(page: Page) {
  // 兜底：未打桩的接口一律 404，避免经 vite 代理打到本机 8000 的真后端。
  // ⚠️ 必须用**锚定 host 的正则**（见 section-header-action-overflow 的教训）：
  // `**/api/**` 会把 vite 的源码模块请求（如 /src/api/watchlist.ts）一并匹配掉。
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
  // 快捷筛选外露类型：全量 10 个，制造最挤的形态
  await page.route(
    "**/api/users/preferences/watchlist_quick_filters/**",
    route =>
      route.fulfill({
        status: 200,
        json: {
          data: {
            value: { filters: ALL_QUICK_FILTERS },
            updated_at: new Date().toISOString()
          }
        }
      })
  );
}

test.describe("自选页筛选行单行不换行（#2329）", () => {
  // 冷启动时 vite 首次编译整套依赖可能超过默认 60s
  test.setTimeout(180_000);

  test.beforeEach(async ({ context, baseURL, page }) => {
    await injectSupabaseSession(context, baseURL!);
    await stubWatchlist(page);
  });

  test("分组 8 个 + 品类全量外露时，筛选行仍只有一行", async ({ page }) => {
    await page.goto("/#/watchlist");

    const row = page.locator(".filter-row");
    await expect(row).toBeVisible({ timeout: 90_000 });

    // ⚠️ 必须等胶囊**真的出现**再量：`.filter-row` 只受 `!batchMode` 控制，挂载即渲染，
    // 而 `.group-tab` 要等 fetchGroups() 返回后才出现。初稿在这里直接 count，
    // 拿到 0 就去断言行数——被自己的「防假绿」守卫拦下（Received: 0），是对的。
    await expect(row.locator(".group-tab").first()).toBeVisible({
      timeout: 30_000
    });
    await expect(row.locator(".quick-pill").first()).toBeVisible({
      timeout: 30_000
    });

    // 切到**自定义分组**：持仓分组下品类胶囊被 narrowToHolding 收窄，不复现用户截图的
    // 「分组多 + 品类全量外露」形态（见 CUSTOM_GROUP_LABEL 注释）。
    await row.locator(".group-tab", { hasText: CUSTOM_GROUP_LABEL }).click();
    // 等切换生效：胶囊从 6 项涨到 11 项
    await expect(row.locator(".quick-pill")).toHaveCount(
      ALL_QUICK_FILTERS.length + 1
    );

    // 先证明两个弹性区**真的渲染出了足够多的子项**——否则「只有一行」会因为
    // 槽是空的而假绿（用户截图恰恰是「内容太多」才触发）
    const groupTabCount = await row.locator(".group-tab").count();
    const pillCount = await row.locator(".quick-pill").count();
    expect(groupTabCount, "分组胶囊未渲染，用例会假绿").toBeGreaterThanOrEqual(
      6
    );
    expect(pillCount, "品类胶囊未渲染，用例会假绿").toEqual(
      ALL_QUICK_FILTERS.length + 1
    );

    const m = await measureFilterRow(page);

    // 断言不变式：筛选行的直接子项**全部落在同一条 flex 线上**
    // （修复前右段被甩到第二行，实测 lineCount=2、行高 74px）
    expect(
      m.lineCount,
      `筛选行换行了，各子项垂直中心=${JSON.stringify(m.centers)}`
    ).toBe(1);
    expect(m.rowHeight, `筛选行高度 ${m.rowHeight}px 提示已折行`).toBeLessThan(
      56
    );
  });

  test("窄屏仍保留「宁可换行也不挤没分组」的兜底（守门不是空转）", async ({
    page
  }) => {
    // 极端窄屏：两区都触到 120px 保底 + 右段仍放不下 ⇒ flex-wrap 应当换行。
    // 这条证明上一条的「只有一行」不是靠把 wrap 整个删掉换来的。
    await page.setViewportSize({ width: 700, height: 900 });
    await page.goto("/#/watchlist");
    const row = page.locator(".filter-row");
    await expect(row).toBeVisible({ timeout: 90_000 });
    await expect(row.locator(".group-tab").first()).toBeVisible({
      timeout: 30_000
    });

    const m = await measureFilterRow(page);
    // 分组区保底 120px 不得被压穿（#1281 的原意）
    expect(m.groupWrapWidth).toBeGreaterThanOrEqual(119);
    expect(m.pillsWrapWidth).toBeGreaterThanOrEqual(119);
    // 极窄下允许换行；这里只钉「不横向溢出页面」这一条更本质的不变式
    expect(m.rowRight).toBeLessThanOrEqual(m.viewportWidth + 1);
  });
});

/**
 * 量一组几何值。
 *
 * ⚠️ 判「是否换行」用**直接子项的垂直中心**去重后是否只剩一个值，
 * 而**不是 offsetTop**——`.filter-row` 是 `align-items: center`，同一 flex 线上
 * 高度不同的子项（32px 胶囊 vs 20px 分区分割线）top 本来就不同，用 offsetTop
 * 会在**单行时误判成多行**。本用例初稿就是这么写错的，靠验证台实测才发现：
 * 单行状态下 offsetTop 去重得到 3 个值（32 / 38 / 33），而真实行数是 1。
 *
 * 也不钉「行高 vs 某个魔数」——那依赖子元素高度、padding 与字号，
 * 换一次设计语言就得重调，调松了还会假绿。中心去重是结构性的不变式。
 */
async function measureFilterRow(page: Page) {
  return page.evaluate(() => {
    const row = document.querySelector<HTMLElement>(".filter-row");
    if (!row) throw new Error("未找到 .filter-row");
    const rowRect = row.getBoundingClientRect();

    const kids = Array.from(row.children) as HTMLElement[];
    const centers = kids.map(k => {
      const b = k.getBoundingClientRect();
      return Math.round(b.top + b.height / 2);
    });

    const gw = document.querySelector<HTMLElement>(".group-tabs-wrap");
    const pw = document.querySelector<HTMLElement>(".quick-pills-wrap");

    return {
      childCount: kids.length,
      lineCount: new Set(centers).size,
      centers,
      rowHeight: rowRect.height,
      rowRight: rowRect.right,
      viewportWidth: window.innerWidth,
      groupWrapWidth: gw ? gw.getBoundingClientRect().width : 0,
      pillsWrapWidth: pw ? pw.getBoundingClientRect().width : 0
    };
  });
}
