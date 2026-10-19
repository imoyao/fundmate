import { expect, test } from "@playwright/test";

import { injectSupabaseSession } from "./support/session";

/**
 * #2338 回归网：**休市日（含工作日法定假日）一律不抓实时估值**。
 *
 * 缺陷形态（修复前）：盘中有闸门，但四条路径绕过它——`start()` 里 `fetchAndUpdate()`
 * 排在交易日判断之前、`manualRefresh()` 完全没有交易日判断、轮询 tick 只看本地星期 /
 * 小时（工作日法定假日被当交易日）、列表 watch 每刷新一次就 `manualRefresh()` 一轮。
 * 于是休息日打开自选页，网络面板里天天基金估值接口仍在周期性出现。
 *
 * 为什么必须 E2E：这里要证明的是「**一笔请求都没有发出去**」，而单测（vitest 是
 * node 环境、无 jsdom）测不到依赖 http / localStorage / 定时器的 composable，
 * 只能测到抽出来的纯函数与源码接线。请求层面的零，只有真浏览器能证。
 *
 * 防假绿的三条刻意设计（缺一条这个用例就是恒真的）：
 * 1. **先坐实「本该会发请求」的前提**：持仓行必须真的渲染出来（`getHoldings` 为空时
 *    取数直接 early return，那时「零请求」什么也证明不了），且交易日历接口必须真的
 *    被请求过（证明前端确实走到了 `canFetch()`，不是压根没跑到取数）；
 * 2. **正向对照**：同一用例后半段把日历桩改成交易日 + 把钟挪到另一个日期的交易时段，
 *    切页再切回（触发 `onActivated → start()`）后请求必须真的出现——证明闸门只是当天
 *    关闭，不是永久卡死；
 * 3. **只偏移时钟不冻结**（`setSystemTime` + `resume`）：与
 *    `realtime-polling-lifecycle.spec.ts` 同源，冻结会让 10s 估值缓存永不失效 /
 *    定时器不触发，两种都会让断言失真。
 *
 * 反向验证（写完必须做，否则不知道自己写的是不是恒真用例）：把 `canFetch()` 改成恒
 * `true`，本用例必须在「零请求」那一行报红——实测确实红。
 * 顺带一个反直觉的发现：**只把 `start()` 里的闸门拆掉，本用例仍是绿的**——首屏
 * `start()` 跑在 items 填充之前，`getHoldings()` 为空直接 early return，真正的取数
 * 触发点是列表数据到位后 `watch(items)` 调的 `manualRefresh()`。所以本用例实际守的是
 * 「`manualRefresh` 这条路径」，也正对应 #2338 根因表里的第 3、4 条（进页面 / 切分组
 * / 翻页都会重打一轮全量行情）。反向断言要跨 2 个档位而不是立刻断言，同样是因为
 * 这一拍延迟。
 */

test.describe.configure({ timeout: 420_000 });

test.use({ timezoneId: "Asia/Shanghai" });

/** 周六 10:00 CST：休市日，但落在交易时段内（旧逻辑只看星期/小时，这里必须被拦下） */
const CLOSED_DAY = new Date("2026-10-17T02:00:00Z");
/** 周三 10:00 CST：正向对照用，日期与休市日不同 ⇒ 交易日缓存不命中，重新查日历 */
const TRADING_TIME = new Date("2026-09-30T02:00:00Z");
/** 与 `REFRESH_INTERVAL_OPTIONS` 的最小档位一致 */
const REFRESH_MS = 15_000;
/** 让「切页瞬间已在途」的链落定 */
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

test.describe("休市日不抓实时估值（#2338 回归）", () => {
  test("休市日进自选页零行情请求，且刷新控件置灰；交易日仍恢复", async ({
    context,
    page,
    baseURL
  }) => {
    await injectSupabaseSession(context, baseURL!);

    await context.addInitScript(() => {
      localStorage.setItem("duoduobei_realtime_quotes_enabled", "true");
      localStorage.setItem("duoduobei_realtime_quotes_interval", "15");
    });
    await page.clock.setSystemTime(CLOSED_DAY);
    await page.clock.resume();

    let quoteHits = 0;
    let calendarHits = 0;
    page.on("request", req => {
      if (QUOTE_SOURCE_RE.test(req.url())) quoteHits++;
      if (/\/api\/utils\/trading-days\//.test(req.url())) calendarHits++;
    });

    // ── 桩：行情源（只数请求，但必须真的响应，否则脚本挂起）──
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
      route.fulfill({
        contentType: "application/javascript",
        body: `jsonpgz({"fundcode":"023887","name":"某某混合A","jzrq":"2026-10-04","dwjz":"0.95","gsz":"0.95","gszzl":"1.05","gztime":"2026-10-05 10:00"});`
      })
    );

    /** 休市 / 交易日由本开关切换：正向对照阶段翻成 true */
    let calendarIsTradingDay = false;

    // ── 桩：后端 ──
    await page.route(
      url => new URL(url).pathname.startsWith("/api/"),
      async route => {
        const url = new URL(route.request().url());
        const p = url.pathname;
        if (p === "/api/utils/config/") {
          return route.fulfill({
            json: { data: { realtime_quotes_enabled: true }, message: "" }
          });
        }
        if (p.startsWith("/api/utils/trading-days/")) {
          return route.fulfill({
            json: {
              data: { is_trading_day: calendarIsTradingDay },
              message: ""
            }
          });
        }
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
    await expect(page.locator(".sidebar-container")).toBeVisible({
      timeout: 150_000
    });
    // 前提一：持仓真的渲染出来（否则「零请求」只是因为没数据可取）
    await expect(page.getByText("023887").first()).toBeVisible({
      timeout: 120_000
    });
    // 前提二：交易日历真的被查过（否则「零请求」只是因为压根没走到 canFetch）
    await expect
      .poll(() => calendarHits, { timeout: 30_000 })
      .toBeGreaterThan(0);

    // ── 反向断言：跨过 2 个档位，行情请求必须一笔都没有 ──
    await page.waitForTimeout(REFRESH_MS * 2 + SETTLE_MS);
    expect(quoteHits).toBe(0);

    // ── 休市态表达：文案说明「休市」，刷新控件置灰（点了不取数就必须看得出来）──
    await expect(page.getByText("休市/收盘")).toBeVisible({ timeout: 30_000 });
    await expect(page.locator(".refresh-icon-btn")).toBeDisabled();

    // ── 正向对照：换成交易日 + 挪钟到另一天，重载 ⇒ 闸门只是当天关闭，不是永久卡死 ──
    // 用重载而不是「切页再切回」：切回走的是 keep-alive 的 onActivated → start()，
    // 实测在休市分支下这条路不再产生请求（首轮 start 已 early return，定时器从未建过），
    // 用它做对照会把「对照失败」误报成「闸门失效」。重载则是全新实例，等价于冷启动。
    calendarIsTradingDay = true;
    await page.clock.setSystemTime(TRADING_TIME);
    const calendarBefore = calendarHits;
    await page.reload({ waitUntil: "commit" });
    await expect(page.getByText("023887").first()).toBeVisible({
      timeout: 120_000
    });
    // 诊断 / 前提：钟真的挪到了另一天 ⇒ 交易日缓存不命中 ⇒ 日历被重新查询。
    // 少了这一条，「零请求」也可能是钟没生效、日历缓存仍命中 false 造成的假绿。
    await expect
      .poll(() => calendarHits, { timeout: 30_000 })
      .toBeGreaterThan(calendarBefore);
    await expect
      .poll(() => quoteHits, { timeout: REFRESH_MS + 30_000 })
      .toBeGreaterThan(0);
  });
});
