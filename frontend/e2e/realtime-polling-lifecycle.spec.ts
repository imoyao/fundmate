import { expect, test } from "@playwright/test";

import { injectSupabaseSession } from "./support/session";

/**
 * #1104 公共层回归网：**keep-alive 页切走后必须停轮询**。
 *
 * 缺陷形态（修复前）：`useRealtimeQuotes` 只挂了 `onBeforeUnmount` 停定时器，
 * 而 `/watchlist`、`/panorama`、`/dividends` 都是 `keepAlive: true`
 * （`router/modules/home.ts`）——切走时组件被缓存**不卸载**，`onBeforeUnmount` 不触发，
 * 于是「离开自选页后行情接口仍按档位持续打」，而此时新页面自己的实例也在轮询，等于双份。
 * 消费者每多一处（持仓双线接进账户详情 / 组合 / 策略）这个放大越明显。
 *
 * 本用例为什么必须用 E2E：出问题的是「路由 keep-alive × 组件生命周期钩子 × 轮询定时器」
 * 的联动，组件级单测要跑起来就得把 keep-alive 与路由整层 mock 掉——正好把出问题的那层挖掉
 * （同 `explore-sidebar.spec.ts` 的判断）。
 *
 * 五条刻意的设计，否则用例不成立（前四条踩过）：
 * 1. **客户端跳转，不能 `page.goto`**：整页重载会真的卸载组件，缺陷复现不出来。
 *    故用点击侧边栏菜单的方式切页，让 keep-alive 缓存真实发生。
 * 2. **只偏移系统时间（`clock.setSystemTime`），不冻结时钟**：轮询 tick 内会判断
 *    「是否 9:30–15:00 的工作日」，必须把时间挪进交易时段，且显式钉 `timezoneId`
 *    （否则 CI 的 UTC 与本机 CST 结论不同）。但时钟必须继续走：
 *    - `clock.setFixedTime` 连 `Date.now()` 一起冻住，而 `fetchFundValuationLastBatch`
 *      有 10s 内存缓存（`VALUATION_CACHE_TTL`，key = 代码列表）：时间不走 ⇒ 缓存永不失效
 *      ⇒ tick 照跳却不再发请求，反向断言会因「根本没有请求」而**假绿**（实测踩中）；
 *    - `clock.install`（暂停态）会让定时器全部不触发，路由守卫里的异步等待直接挂住、
 *      页面根本不渲染（实测 sidebar 20s 不可见 / `load` 150s 超时）。
 *    `setSystemTime` 只把「现在」整体平移，定时器按真实节奏跑，两个坑都绕开。
 * 3. **`waitUntil: "commit"`**：不等 `load`（dev server 首次编译 + 冻结时钟都容易让它迟到），
 *    改用具体选择器确认页面已渲染。
 * 4. **正负两段对照**：先证明「停在自选页时请求在涨」，再证明「切走后不涨」。
 *    少了前一段，定时器没跑起来 / 取数被缓存拦掉都会静默通过。
 * 5. **行情源自己桩**：断言的是「请求次数」，必须让请求真的发出去，故桩 3 个行情源 +
 *    让自选列表返回一条**真实持仓行**（`getHoldings` 在有持仓时才取数，持仓为空会
 *    early return，用例将永远为绿）。
 */

test.describe.configure({ timeout: 420_000 });

test.use({ timezoneId: "Asia/Shanghai" });

/** 周三 10:00 CST（交易时段内） */
const TRADING_TIME = new Date("2026-09-30T02:00:00Z");
/** 与 `REFRESH_INTERVAL_OPTIONS` 的最小档位一致 */
const REFRESH_MS = 15_000;
/** 等一轮「改钟之后」的取数落定 */
const SETTLE_MS = 3000;

/** 三个行情源（天天基金批量估值 / 腾讯批量 / 天天基金单只降级） */
const QUOTE_SOURCE_RE =
  /qt\.gtimg\.cn|fundcomapi\.tiantianfunds\.com|fundgz\.1234567/;

/** 一条「真实持仓」自选行：字段名与 `useWatchlistValuation.getHoldings` 的判据对齐 */
const HOLDING_ROW = {
  id: 1,
  symbol: "023887",
  name: "某某混合A",
  asset_type: "fund",
  venue: "OTC",
  market: "CN",
  status: "HOLDING",
  holding_quantity: 12000,
  holding_cost_price: 0.83,
  holding_pnl: 1440,
  holding_pnl_percent: 14.46,
  current_price: 0.95,
  change_pct: 1.05,
  price_at_added: 0.9,
  is_pinned: false,
  favorite: false,
  tags: []
};

test.describe("实时轮询生命周期（#1104 公共层回归）", () => {
  test("自选页切走后不再打行情接口（keep-alive 失活必须停轮询）", async ({
    context,
    page,
    baseURL
  }) => {
    await injectSupabaseSession(context, baseURL!);

    await context.addInitScript(() => {
      localStorage.setItem("showbuy_realtime_quotes_enabled", "true");
      localStorage.setItem("showbuy_realtime_quotes_interval", "15");
    });
    // 先平移系统时间到交易时段，再 resume：`setSystemTime` 会把定时器切到「手动推进」态，
    // 不 resume 的话路由守卫里的异步等待永远不 resolve、页面根本不渲染（实测 sidebar 不可见）。
    // resume 之后时间照常流动（只是整体平移），`Date.now()` 与 `setInterval` 都是真实节奏。
    await page.clock.setSystemTime(TRADING_TIME);
    await page.clock.resume();

    let quoteHits = 0;
    page.on("request", req => {
      if (QUOTE_SOURCE_RE.test(req.url())) quoteHits++;
    });

    // ── 桩：行情源。返回体内容不重要（本用例只数请求），但必须真的响应，否则脚本挂起 ──
    await page.route("**/fundcomapi.tiantianfunds.com/**", async route => {
      const cb = new URL(route.request().url()).searchParams.get("callback");
      await route.fulfill({
        contentType: "application/javascript",
        body: `${cb}({"data":[],"ErrCode":0});`
      });
    });
    await page.route("**/qt.gtimg.cn/**", route =>
      route.fulfill({ contentType: "application/javascript", body: "" })
    );
    await page.route("**/fundgz.1234567.com.cn/**", route =>
      route.fulfill({ contentType: "application/javascript", body: "" })
    );

    // ── 桩：后端。只需三条精确响应，其余给空信封（本用例不依赖后端）──
    await page.route(
      url => new URL(url).pathname.startsWith("/api/"),
      async route => {
        const url = new URL(route.request().url());
        const p = url.pathname;
        // 平台总闸：必须明确 true。返回空信封会让 `realtime_quotes_enabled` 变 undefined，
        // 前端按「平台关闭」处理并 stop()，轮询根本不会起来。
        if (p === "/api/utils/config/") {
          return route.fulfill({
            json: { data: { realtime_quotes_enabled: true }, message: "" }
          });
        }
        if (p.startsWith("/api/utils/trading-days/")) {
          return route.fulfill({
            json: { data: { is_trading_day: true }, message: "" }
          });
        }
        // 自选列表：一条真实持仓行（`status: HOLDING` + 数量 > 0 才会进 getHoldings）
        if (p === "/api/watchlist/items/") {
          const isFirstPage = Number(url.searchParams.get("page") ?? 1) === 1;
          return route.fulfill({
            json: {
              data: isFirstPage ? [HOLDING_ROW] : [],
              total: isFirstPage ? 1 : 0,
              page: 1,
              per_page: 200,
              message: ""
            }
          });
        }
        return route.fulfill({ json: { data: [], total: 0, message: "" } });
      }
    );

    await page.goto("/#/watchlist", { waitUntil: "commit" });
    // dev server 冷启动（首次编译整页依赖）在这个仓库实测要 20s+，别用默认 20s 的断言超时
    await expect(page.locator(".sidebar-container")).toBeVisible({
      timeout: 150_000
    });
    // 等桩数据真的渲染出来：`getHoldings` 依赖它，持仓为空时轮询取数会 early return，
    // 于是「没有行情请求」既可能是缺陷也可能是没数据——必须先把这个前提坐实。
    await expect(page.getByText("023887").first()).toBeVisible({
      timeout: 120_000
    });

    // ── 正向对照一：等一个档位，必须打出行情请求 ──
    await expect
      .poll(() => quoteHits, { timeout: REFRESH_MS + 20_000 })
      .toBeGreaterThan(0);

    // ── 正向对照二：再等一个档位，请求必须继续涨（定时器确实在跳；10s 估值缓存已过期）──
    const firstRound = quoteHits;
    await expect
      .poll(() => quoteHits, { timeout: REFRESH_MS + 20_000 })
      .toBeGreaterThan(firstRound);

    // ── 客户端跳转（不是整页重载）：/watchlist 被 keep-alive 缓存，新页挂载 ──
    await page
      .locator(".sidebar-container")
      .getByText("资产总览", { exact: true })
      .click();
    await expect(page).toHaveURL(/#\/panorama/);

    // 让「切页瞬间已发出、尚在途中」的那一轮落定，再记基线
    await page.waitForTimeout(SETTLE_MS);
    const afterNav = quoteHits;

    // ── 反向断言：跨过 2 个档位，请求数必须一动不动 ──
    await page.waitForTimeout(REFRESH_MS * 2 + SETTLE_MS);
    expect(quoteHits).toBe(afterNav);

    // ── 回程：切回自选页必须恢复轮询（失活只是暂停，不是把功能停掉）──
    const beforeBack = quoteHits;
    await page
      .locator(".sidebar-container")
      .getByText("我的自选", { exact: true })
      .click();
    await expect(page).toHaveURL(/#\/watchlist/);
    await expect
      .poll(() => quoteHits, { timeout: REFRESH_MS + 20_000 })
      .toBeGreaterThan(beforeBack);
  });
});
