import { expect, test, type Page } from "@playwright/test";
import { injectSupabaseSession } from "./support/session";

/**
 * 对话页的「单滚动 + 贴底输入区」契约（2026-11 反馈「下拉滚动条太多」的回归网）。
 *
 * 背景：上一版把页面高度钉死、让 `.chat-list` 自己滚，于是外层 el-scrollbar
 * （页脚 / 对账横幅都在它的内容流里）多出一条滚动条，页面上同时出现三条。
 * 现在回到 design.md 的单一滚动：页面自己滚，输入区 sticky 贴底。
 *
 * 判据只认机器可验的四条，避免「看着像」：
 * 1. 消息列**不是**滚动容器（overflow-y 为 visible）；
 * 2. 长会话滚到顶时，dock 的底边仍等于视口底（sticky 生效，没被顶到折线以下）；
 * 3. **输入胶囊的位置不随内容量变化**（2026-11-26 反馈「输入框随时漂移」：
 *    `.chat-list` 少一个 flex-grow 就会让 dock 紧跟内容、下方留白，实测空态 781px、
 *    发一条后 433px，上移 348px）；
 * 4. **对账横幅出现时外层不多出滚动条**，且贴底输入区不位移（横幅在 el-scrollbar
 *    的内容流里、不在视口高预算内；页面按 lay-content 实测的 `--app-banner-height`
 *    减掉它。漏减实测溢出 56px、外层立刻多一条滚动条）。
 */

const items = Array.from({ length: 7 }, (_, i) => ({
  session_id: `sess-scroll-${i}`,
  title: `滚动契约会话 ${i + 1}`,
  goal: "分析账户收益",
  preview: `滚动契约会话 ${i + 1}`,
  turn_count: 1,
  created_at: "2026-11-20T10:00:00+08:00",
  updated_at: "2026-11-20T10:05:00+08:00"
}));

const LONG_TURNS = 12;

/**
 * 除会话列表外的接口一律 404 ⇒ 对账横幅不会出现。
 *
 * 为什么每个几何用例都要调：横幅是**异步**出现的（getMe + 差异列表），
 * 而它一旦出现就会让页面少 59px。断「胶囊位置」的用例若碰上它在中途出现，
 * 会量到 55px 的假漂移（本轮实测：同一份代码，有后端数据时红、无数据时绿）。
 * 后注册的桩优先匹配，所以本函数必须在各用例的具体桩**之前**调用。
 */
async function mockNoBanner(page: Page): Promise<void> {
  await page.route(/^https?:\/\/[^/]+\/api\//, route =>
    route.fulfill({ status: 404, json: { data: null, message: "e2e 未打桩" } })
  );
}

/**
 * 等字体与布局结算完再量像素。
 *
 * 首屏 webfont 落地会让 hero 高度变化 2~3px（实测 page 719 → 716），
 * 而胶囊位置是像素级断言；不等这一下，容差 1px 会时红时绿。
 * 这不是「等接口」，是等渲染本身稳定——横幅的显隐由 mockNoBanner 钉死。
 */
async function settle(page: Page): Promise<void> {
  await page.evaluate(async () => {
    await document.fonts.ready;
  });
  await page.waitForTimeout(250);
}

test("空态：消息列不自成滚动容器（只有外层一条）", async ({
  page,
  context,
  baseURL
}) => {
  await injectSupabaseSession(context, baseURL!);
  await mockNoBanner(page);
  await page.route(/\/api\/agent\/sessions\/?(?:\?.*)?$/, route =>
    route.fulfill({
      json: { data: items, total: items.length, page: 1, per_page: 50 }
    })
  );

  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/#/agent/chat");
  await expect(page.getByText("7 条")).toBeVisible();

  const overflowY = await page.evaluate(
    () =>
      getComputedStyle(document.querySelector(".chat-list") as HTMLElement)
        .overflowY
  );
  expect(overflowY).toBe("visible");
});

test("长会话：滚到顶后 dock 仍贴视口底", async ({ page, context, baseURL }) => {
  await injectSupabaseSession(context, baseURL!);
  await mockNoBanner(page);
  await page.route(
    /\/api\/agent\/sessions\/sess-scroll-0\/?(?:\?.*)?$/,
    route =>
      route.fulfill({
        json: {
          data: {
            session_id: "sess-scroll-0",
            title: "滚动契约会话 1",
            goal: "分析账户收益",
            turn_count: LONG_TURNS,
            created_at: "2026-11-20T10:00:00+08:00",
            updated_at: "2026-11-20T10:05:00+08:00",
            messages: Array.from({ length: LONG_TURNS }, (_, i) => ({
              user: `第 ${i + 1} 问：我的持仓现在值多少钱？`,
              assistant: `第 ${i + 1} 轮回答：持仓成本 15200.00 元，当前浮亏 8.4%。补两句让内容够长，确保页面产生纵向滚动。`
            }))
          }
        }
      })
  );
  await page.route(/\/api\/agent\/sessions\/?(?:\?.*)?$/, route =>
    route.fulfill({
      json: { data: items, total: items.length, page: 1, per_page: 50 }
    })
  );

  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/#/agent/chat");
  await expect(page.getByText("7 条")).toBeVisible();
  await page.locator(".session-history__item").first().click();
  await expect(
    page.getByText(`第 ${LONG_TURNS} 轮回答`, { exact: false })
  ).toBeVisible();

  // 滚到顶：dock 若没 sticky，会被内容顶到视口之外
  await page.evaluate(() => {
    const wrap = document.querySelector(
      ".app-main .el-scrollbar__wrap"
    ) as HTMLElement;
    wrap.scrollTop = 0;
  });
  await page.waitForTimeout(300);

  const box = await page.evaluate(() => {
    const dock = document.querySelector(".chat-dock") as HTMLElement;
    const r = dock.getBoundingClientRect();
    const wrap = document.querySelector(
      ".app-main .el-scrollbar__wrap"
    ) as HTMLElement;
    return {
      dockBottom: Math.round(r.bottom),
      dockTop: Math.round(r.top),
      viewportBottom: window.innerHeight,
      pageScrolls: wrap.scrollHeight > wrap.clientHeight
    };
  });

  // 页面确实需要滚动（否则这条用例证明不了 sticky）
  expect(box.pageScrolls).toBe(true);
  // dock 完整落在视口内，且底边贴住视口底（±1px 容差给亚像素）
  expect(Math.abs(box.dockBottom - box.viewportBottom)).toBeLessThanOrEqual(1);
  expect(box.dockTop).toBeLessThan(box.viewportBottom);
});

test("输入框不随内容量漂移：空态与单轮会话的胶囊位置相同", async ({
  page,
  context,
  baseURL
}) => {
  await injectSupabaseSession(context, baseURL!);
  await mockNoBanner(page);

  // 一轮的短会话：内容远不足一屏——正是「dock 紧跟内容、下方留白」的复现条件
  await page.route(
    /\/api\/agent\/sessions\/sess-scroll-1\/?(?:\?.*)?$/,
    route =>
      route.fulfill({
        json: {
          data: {
            session_id: "sess-scroll-1",
            title: "滚动契约会话 2",
            goal: "分析账户收益",
            turn_count: 1,
            created_at: "2026-11-20T10:00:00+08:00",
            updated_at: "2026-11-20T10:05:00+08:00",
            messages: [{ user: "问一句", assistant: "答一句" }]
          }
        }
      })
  );
  await page.route(/\/api\/agent\/sessions\/?(?:\?.*)?$/, route =>
    route.fulfill({
      json: { data: items, total: items.length, page: 1, per_page: 50 }
    })
  );

  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/#/agent/chat");
  await expect(page.getByText("7 条")).toBeVisible();
  await expect(page.locator(".recon-banner")).toHaveCount(0);
  await settle(page);

  // 量「胶囊」而不是 dock 容器：状态行出现时 dock 会向上长，但胶囊不该动
  const pillTop = () =>
    page
      .locator(".chat-input-pill")
      .evaluate(el => Math.round(el.getBoundingClientRect().top));

  const emptyTop = await pillTop();
  await page.locator(".session-history__item").nth(1).click();
  await expect(page.getByText("答一句")).toBeVisible();
  const shortTop = await pillTop();

  expect(Math.abs(shortTop - emptyTop)).toBeLessThanOrEqual(1);
});

/**
 * 对账横幅 ↔ 页面高度预算（2026-11 反馈的遗留项）。
 *
 * 横幅挂在布局层、在 el-scrollbar 的内容流里；对话页按视口算 min-height 时必须把它
 * 一起减掉，否则总量比可用高度多出横幅那一截 ⇒ 外层多一条滚动条、贴底输入区被顶出折线。
 *
 * 用「同一页面 A/B」而不是两个独立用例：基线必须先证明**没有**横幅，
 * 否则「有横幅时也没溢出」可能只是因为桩没生效（恒真空断言）。
 */
test("对账横幅出现时：外层不多出滚动条，贴底输入区不位移", async ({
  page,
  context,
  baseURL
}) => {
  await injectSupabaseSession(context, baseURL!);

  const pad = (n: number) => String(n).padStart(2, "0");
  const d = new Date();
  d.setDate(d.getDate() - 30);
  const staleAt = `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T06:06:39`;

  // 兜底先注册（后注册的优先匹配）：除会话列表外一律 404 ⇒ 首屏不该有横幅
  await page.route(/^https?:\/\/[^/]+\/api\//, route =>
    route.fulfill({ status: 404, json: { data: null, message: "e2e 未打桩" } })
  );
  await page.route(/\/api\/agent\/sessions\/?(?:\?.*)?$/, route =>
    route.fulfill({
      json: { data: items, total: items.length, page: 1, per_page: 50 }
    })
  );

  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/#/agent/chat");
  await expect(page.getByText("7 条")).toBeVisible();
  await expect(page.locator(".recon-banner")).toHaveCount(0);
  await settle(page);

  const measure = () =>
    page.evaluate(() => {
      const el = (s: string) => document.querySelector(s) as HTMLElement | null;
      const wrap = el(".app-main .el-scrollbar__wrap");
      const banner = el(".recon-banner");
      const pill = el(".chat-input-pill");
      return {
        bannerH: banner?.offsetHeight ?? 0,
        // 外层还有没有第二条滚动条：这是本用例要钉死的量
        overflow: wrap ? wrap.scrollHeight - wrap.clientHeight : -1,
        pillBottom: pill ? Math.round(pill.getBoundingClientRect().bottom) : -1,
        viewportBottom: window.innerHeight
      };
    });

  const baseline = await measure();
  expect(baseline.bannerH).toBe(0);
  expect(baseline.overflow).toBeLessThanOrEqual(1);

  // 挂上三类问题的桩并重载（重载后横幅才重新取数）
  await page.route(/\/api\/reconciliation\/discrepancies/, route =>
    route.fulfill({
      json: {
        data: [
          {
            id: 1,
            domain: "B",
            symbol: "600519",
            discrepancy_type: "quantity",
            status: "pending",
            diff: 1000,
            first_detected_at: staleAt
          }
        ],
        message: ""
      }
    })
  );
  await page.route(/\/api\/reconciliation\/dangling-refs\/$/, route =>
    route.fulfill({
      json: {
        data: {
          total: 3,
          fixable_count: 2,
          group_count: 1,
          batch_count: 1,
          null_symbol: 1,
          null_trade_date: 2,
          groups: [],
          batches: []
        },
        message: ""
      }
    })
  );
  await page.route(/\/api\/reconciliation\/orphan-ledger\/$/, route =>
    route.fulfill({
      json: {
        data: {
          total: 2,
          fixable_count: 1,
          blocked_count: 1,
          batch_count: 1,
          groups: [],
          batches: []
        },
        message: ""
      }
    })
  );

  await page.reload();
  await expect(page.locator(".recon-banner")).toBeVisible({ timeout: 60_000 });
  await settle(page); // 等 ResizeObserver 量完、页面高度回写后再量

  const withBanner = await measure();
  // 先证桩真的生效：横幅在场且占了高度
  expect(withBanner.bannerH).toBeGreaterThan(0);
  // ① 外层不多出滚动条（容差 1px 给亚像素）
  expect(withBanner.overflow).toBeLessThanOrEqual(1);
  // ② 贴底输入区不位移：横幅只挤压页面顶部，不会把输入框推下折线
  expect(
    Math.abs(withBanner.pillBottom - baseline.pillBottom)
  ).toBeLessThanOrEqual(1);
  expect(withBanner.pillBottom).toBeLessThanOrEqual(withBanner.viewportBottom);
});
