import { expect, test, type Page } from "@playwright/test";
import { injectSupabaseSession } from "./support/session";

/**
 * 详情页页内导航回归网（#1968 子卡：顶部锚点胶囊 + xl 右目录 rail）。
 *
 * 钉七条不变式：
 * 1. **无死链**：导航项只列 DOM 里真实渲染的区块——走势对 manager 整卡不渲染、
 *    交易记录对非可交易品类不渲染，这些都不能出现在胶囊里（点了原地不动即为死链）；
 * 2. 点击胶囊平滑滚动到目标区块，active 态随动；
 * 3. scroll-spy：滚动时 active 跟随当前区块；**触底时当前项 = 最后一项**
 *    （maxScroll 截断下最后一项永远到不了定位线，老判据会把高亮永久停在倒数第二项；
 *    点胶囊路径由 goTo 的 pinnedId 意图保证，不走兜底）；
 * 4. 逐项点击（正序 + 逆序）：停稳后 active 必须是点击项——钉住「定位线零容差
 *    导致的亚像素回跳」（实测约一半概率中招，用户看到「胶囊来回弹跳」），
 *    也钉住 maxScroll 截断：点倒数第二项滚到底后高亮必须留在点击项，
 *    不能被触底兜底改写成最后一项；
 * 5. 数据在飞时点击下方区块：布局突变（走势卡长高 300+px）后落点不漂移
 *    （原生 smooth 的终点只算一次，实测过冲 800+px）；
 * 6. 响应式两级：<xl 胶囊可见 + rail 隐藏；xl+ 反之；
 * 7. xl+ 右 rail 与胶囊列同一批条目（两级是同一状态的两个投影）。
 *
 * 接口全部 page.route 打桩，不依赖后端（docs/dev/frontend-e2e.md §7）。
 *
 * 反向验证：删掉 detail.vue 里 <ProductPageNav> 挂载 → 本文件全红；
 * 把 useProductPageNav 的 items 过滤改成静态清单 → 经理页用例红（死链回归）；
 * 去掉 <ProductTransactionSection> 的 has_position 条件 → 「无持仓」用例红
 * （空卡 + 无用请求 + 胶囊死重量三样回归）；
 * updateActive 的 EPSILON 改回 0 → 逐项点击用例红（亚像素回跳回归）；
 * 去掉触底兜底 → scroll-spy 用例的触底断言红（点胶囊路径已由 pinnedId 兜住）；
 * goTo 不设 pinnedId（停稳后按位置终算一次）→ 逐项点击逆序列红
 * （点「关联标的」滚到底后高亮被兜底改写成「更多数据」）；
 * goTo 换回原生 scrollTo({behavior:'smooth'}) → 数据在飞机用例红（过期目标回归）。
 */

const NAME = "永赢北证50成份指数发起C";
const SYMBOL = "023887";

/** 把某个滚动容器滚到指定 scrollTop：fixedHeader 模式下真正滚动的是
 *  `.app-main .el-scrollbar__wrap`，非 fixed 模式是 window——两种都兜住。 */
async function scrollBy(page: Page, top: number) {
  await page.evaluate(y => {
    const wrap = document.querySelector<HTMLElement>(
      ".app-main .el-scrollbar__wrap"
    );
    if (wrap && wrap.scrollHeight > wrap.clientHeight + 1) {
      wrap.scrollTop = y;
    } else {
      window.scrollTo(0, y);
    }
  }, top);
}

/** 把目标区块顶边送到定位线（胶囊底边）附近，返回滚动后的 scrollTop */
async function scrollSectionUnderLine(page: Page, id: string) {
  const top = await page.evaluate(anchorId => {
    const el = document.getElementById(anchorId);
    if (!el) return null;
    const wrap = document.querySelector<HTMLElement>(
      ".app-main .el-scrollbar__wrap"
    );
    const scroller =
      wrap && wrap.scrollHeight > wrap.clientHeight + 1 ? wrap : null;
    // 与 useProductPageNav.spyLine 同源：吸顶胶囊底边 + 8px
    const nav = document.querySelector<HTMLElement>(".page-nav");
    const navH = nav && nav.offsetHeight > 0 ? nav.offsetHeight : 0;
    const base = scroller ? scroller.getBoundingClientRect().top : 0;
    const line = base + navH + 8;
    const target = el.getBoundingClientRect().top - line;
    const next = (scroller ? scroller.scrollTop : window.scrollY) + target;
    if (scroller) scroller.scrollTop = next;
    else window.scrollTo(0, next);
    return next;
  }, id);
  expect(top).not.toBeNull();
  return top as number;
}

/** 等滚动停稳：连续 5 帧（约 80ms）scrollTop 无变化才算停。
 *  不能靠「连续两次轮询值相等」——平滑滚动尚未启动时两次轮询都是旧值，
 *  会误判停稳（v2 探针就这么误判过，测出一堆假漂移）。rAF 逐帧看，
 *  滚动一旦启动就会打破连续相等。 */
async function waitScrollSettle(page: Page) {
  await page.evaluate(() => {
    const w = window as unknown as { __navSettled?: boolean };
    const wrap = document.querySelector<HTMLElement>(
      ".app-main .el-scrollbar__wrap"
    );
    const read = () => (wrap ? wrap.scrollTop : window.scrollY);
    let last = read();
    let still = 0;
    w.__navSettled = false;
    const tick = () => {
      const cur = read();
      still = Math.abs(cur - last) < 0.5 ? still + 1 : 0;
      last = cur;
      if (still >= 5) {
        w.__navSettled = true;
        return;
      }
      requestAnimationFrame(tick);
    };
    requestAnimationFrame(tick);
  });
  await page.waitForFunction(
    () =>
      (window as unknown as { __navSettled?: boolean }).__navSettled === true,
    null,
    { timeout: 15_000 }
  );
}

async function stubProductApis(page: Page, opts?: { hasPosition?: boolean }) {
  const hasPosition = opts?.hasPosition ?? true;
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
          asset_type: { fund: "基金" },
          market: { CN_A: "A股" },
          venue: { OTC: "场外" }
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
          in_watchlist: true,
          has_position: hasPosition,
          source: "position"
        },
        message: "ok"
      }
    })
  );
  await page.route("**/api/products/fund-profile/**", route =>
    route.fulfill({
      status: 200,
      json: {
        data: {
          fund_code: SYMBOL,
          name: NAME,
          fund_type: "指数型-股票",
          company: "永赢基金管理有限公司",
          unit_nav: 0.8234,
          nav_date: "2026-10-09",
          change_pct: 0.402,
          source: "天天基金"
        },
        message: "ok"
      }
    })
  );
  await page.route("**/api/products/fund-holdings-detail/**", route =>
    route.fulfill({
      status: 200,
      json: {
        data: {
          applicable: true,
          has_industry: true,
          has_holding: true,
          industries: [
            {
              scheme: "csrc",
              scheme_label: "证监会门类",
              is_primary: true,
              report_period: "2026Q2",
              report_date: "2026-06-30",
              total_ratio: 89.0,
              items: [
                { industry_code: "C", industry_name: "制造业", ratio: 30.5 }
              ]
            }
          ],
          holdings: {
            rows: [
              {
                rank: 1,
                stock_code: "600519",
                stock_name: "贵州茅台",
                ratio: 9.87
              }
            ],
            basis: "top10",
            basis_label: "前十大（季报）",
            report_period: "2026Q2",
            report_date: "2026-06-30",
            shown_total_ratio: 9.87
          },
          as_of: "2026-06-30",
          source: "东方财富"
        },
        message: "ok"
      }
    })
  );
  await page.route("**/api/positions/**", route =>
    route.fulfill({
      status: 200,
      json: { data: [], total: 0, page: 1, per_page: 100, message: "ok" }
    })
  );
}

test.describe("详情页页内导航（#1968）", () => {
  test.setTimeout(180_000);

  test.beforeEach(async ({ context, baseURL, page }) => {
    await injectSupabaseSession(context, baseURL!);
    await stubProductApis(page);
    // 胶囊形态的用例统一用 <xl 视口：xl（1280）起让位给右目录 rail，
    // 默认 1280 会正好踩在断点上（ pills 被 display:none）。
    await page.setViewportSize({ width: 1100, height: 900 });
  });

  test("基金页：胶囊只列真实渲染的区块（无死链）", async ({ page }) => {
    await page.goto(`/#/fund/${SYMBOL}`);
    // 等持仓明细到位（异步取数后才出现的锚点）
    await expect(page.locator(".holding-section")).toBeVisible({
      timeout: 60_000
    });

    const nav = page.locator(".page-nav");
    await expect(nav).toBeVisible();
    await expect(nav.locator(".page-nav__pill")).toHaveText([
      "我的持仓",
      "走势",
      "交易记录",
      "基金资料",
      "业绩与风险",
      "行业与持仓",
      "关联标的",
      "高级洞察 Pro",
      "更多数据"
    ]);

    // 每个胶囊都必须有对应锚点——死链是这条不变式的反面
    // （items 由 DOM 扫描生成，数量必然相等；静态清单回归会让它不相等）
    const counts = await page.evaluate(() => ({
      pills: document.querySelectorAll(".page-nav__pill").length,
      anchors: document.querySelectorAll('.product-detail__main [id^="nav-"]')
        .length
    }));
    expect(counts.pills).toBe(counts.anchors);
  });

  test("高级洞察 Pro 占位：区块渲染 + 徽标来自状态位（#2272）", async ({
    page
  }) => {
    // #2272（#994 Phase 1 接口骨架 + 付费墙壳）。钉三件事：
    // ① 区块真的渲染了——#2029 同款静默消失防线：detail.vue 的 import 被删时
    //    Vue 只发 warning，父级透传的 id 静默丢弃，页面无可见报错；
    // ② 徽标（Phase N 建设中）来自后端状态位而非前端硬编码（不编造"已上线"）；
    // ③ 付费墙遮罩与禁用态升级按钮在（flag 默认开，无支付体系）。
    // 反向验证：删 detail.vue 的 import → ①红；把徽标文案改成前端常量 →
    // ②红（本用例改打桩值即红）。
    const pageErrors: string[] = [];
    page.on("pageerror", e => pageErrors.push(e.message));

    // beforeEach 的 catch-all 对未打桩路由回 404（组件走降级：无徽标）；
    // 后注册的 route 优先，这里覆盖 pro 端点给真状态位
    await page.route("**/api/products/pro/**", route =>
      route.fulfill({
        status: 200,
        json: {
          data: {
            symbol: SYMBOL,
            asset_type: "fund",
            pro_enabled: true,
            paywall_required: false,
            modules: {
              performance: { available: false, phase: 2 },
              risk: { available: false, phase: 2 },
              allocation: { available: false, phase: 3 },
              report: { available: false, phase: 4 }
            }
          },
          message: "ok"
        }
      })
    );

    await page.goto(`/#/fund/${SYMBOL}`);
    const pro = page.locator("#nav-pro");
    await expect(pro).toBeVisible({ timeout: 60_000 });

    // 四模块占位卡 + 徽标文案逐条与打桩的 phase 一致（2/2/3/4，见 #994 排期）——
    // 校验全部四条而非第一条：只查第一条时，前端把徽标写死成常量同样能绿
    await expect(pro.locator(".pro-module")).toHaveCount(4);
    await expect(pro.locator(".pro-module__badge")).toHaveText([
      "Phase 2 建设中",
      "Phase 2 建设中",
      "Phase 3 建设中",
      "Phase 4 建设中"
    ]);

    // 付费墙：遮罩在、升级按钮禁用（一期无支付体系，点了不许有幻觉）
    await expect(pro.locator(".pro-paywall")).toBeVisible();
    await expect(pro.getByRole("button", { name: "升级 Pro" })).toBeDisabled();

    // 导航胶囊收录该区块（与锚点同在，无死链）
    await expect(
      page.locator(".page-nav").getByRole("button", { name: "高级洞察 Pro" })
    ).toHaveCount(1);

    expect(pageErrors).toEqual([]);
  });

  test("无持仓：交易记录不渲染、不进导航、不发请求", async ({ page }) => {
    // #2104 行为修正：交易流水是用户自己的账本数据，与「我的持仓」同条件——
    // 仅当前持有时渲染。未持有用户不该看到一张「暂无交易记录」空卡，
    // 也不该为它打一次无用请求，导航胶囊更不该多一项死重量。
    // 反向验证：把 detail.vue 的 v-if 去掉 → 本用例红（空卡 + 死链回归）。
    const txnRequests: string[] = [];
    page.on("request", req => {
      // 只认真 API：dev server 下前端模块 src/api/transactions.ts 的路径
      // 也含 "transactions" 字样，宽松子串匹配会误抓
      if (/\/api\/transactions(\?|$|\/)/.test(new URL(req.url()).pathname)) {
        txnRequests.push(req.url());
      }
    });
    // beforeEach 已按「有持仓」打过桩；后注册的 route 优先，覆盖 resolve
    await stubProductApis(page, { hasPosition: false });

    await page.goto(`/#/fund/${SYMBOL}`);
    await expect(page.locator(".page-nav")).toBeVisible({ timeout: 60_000 });

    // 胶囊里没有「交易记录」，锚点也不存在
    await expect(page.locator(".page-nav__pill")).not.toHaveText([
      "我的持仓",
      "走势",
      "交易记录",
      "基金资料",
      "业绩与风险",
      "行业与持仓",
      "关联标的",
      "更多数据"
    ]);
    expect(
      await page.locator(".page-nav__pill", { hasText: "交易记录" }).count()
    ).toBe(0);
    expect(await page.locator("#nav-transactions").count()).toBe(0);

    // 持仓区块同样不渲染（has_position=false），与交易记录同源
    expect(await page.locator("#nav-position").count()).toBe(0);

    // 没有为交易记录发过请求
    expect(txnRequests).toEqual([]);
  });

  test("有持仓：交易记录表格渲染公共组件列集与行内容（#2104 统一）", async ({
    page
  }) => {
    // #2104：详情页 / 账本 Tab / 持仓抽屉三处交易表统一为
    // components/TransactionTable（同一组件、同一口径）。本用例钉 compact 模式
    // （详情页）的渲染契约：列集、日期口径（trade_date 优先）、
    // 「共 N 条」文案、零 pageerror。
    // 反向验证：TransactionTable 列定义回归（如漏账户列、日期改认
    // confirm_date）→ 本用例红。
    const pageErrors: string[] = [];
    page.on("pageerror", e => pageErrors.push(e.message));

    await page.route(/\/api\/transactions(\/|\?|$)/, route =>
      route.fulfill({
        status: 200,
        json: {
          data: [
            {
              id: 9001,
              type: "buy",
              trade_date: "2026-03-02",
              confirm_date: "2026-03-03",
              quantity: 1000.5,
              price: 0.9123,
              amount: 912.71,
              fee: 1.5,
              account_name: "华泰证券",
              position_name: NAME,
              asset_type: "fund"
            },
            {
              id: 9002,
              type: "dividend",
              trade_date: "2026-06-10",
              confirm_date: "2026-06-11",
              quantity: 0,
              price: 0,
              amount: 56.78,
              fee: 0,
              account_name: "华泰证券",
              position_name: NAME,
              asset_type: "fund"
            }
          ],
          total: 2,
          page: 1,
          per_page: 10,
          message: "ok"
        }
      })
    );

    await page.goto(`/#/fund/${SYMBOL}`);
    const table = page.locator("#transaction-detail-table");
    await expect(table).toBeVisible({ timeout: 60_000 });

    // compact 列集（顺序即契约）：无产品列/手续费/操作列
    await expect(table.locator(".el-table__header th")).toHaveText([
      "交易日期",
      "类型",
      "价格",
      "数量",
      "金额",
      "账户"
    ]);

    // 行数与桩一致（证明桩接上；没接上会走 404 错误态，表格根本不渲染）
    await expect(table.locator(".el-table__body tbody tr")).toHaveCount(2);

    // 首行：trade_date 优先（不是 confirm_date 的 03-03）、类型中文、金额带 ¥
    const firstRow = table.locator(".el-table__body tbody tr").first();
    await expect(firstRow).toContainText("2026-03-02");
    await expect(firstRow).toContainText("买入");
    await expect(firstRow).toContainText("¥912.71");
    await expect(firstRow).toContainText("华泰证券");

    // 容器文案：共 N 条（渐进披露的基数）
    await expect(page.locator(".transaction-section__count")).toHaveText(
      "共 2 条"
    );

    expect(pageErrors).toEqual([]);
  });

  test("基金经理字段缺失：降级为「—」，不抛错不消失（#2191）", async ({
    page
  }) => {
    // #2191：模板曾裸取 profile.managers.length，fund-profile 响应缺该字段时
    // 渲染抛 TypeError。Vue 把渲染错误吞进子组件（父级透传的 #nav-fund 锚点
    // 可能还在），整块基金资料渲染成空、页面无可见报错——本用例钉两条：
    // ① 基金经理行降级为「—」（与基金类型/规模等字段同一契约，见
    //    FundProfileResult「字段缺失一律为 null，前端据此降级」）；
    // ② 加载全程零 pageerror。
    // 反向验证：把模板改回 profile.managers.length → 本用例红。
    const pageErrors: string[] = [];
    page.on("pageerror", e => pageErrors.push(e.message));

    await page.goto(`/#/fund/${SYMBOL}`);
    await expect(page.locator(".page-nav")).toBeVisible({ timeout: 60_000 });

    // 先证明桩接上了：区块必须渲染真实内容而非「暂无可展示」空态——
    // 取数失败时下面的断言会假绿，所以先钉死这一条
    const fund = page.locator("#nav-fund");
    await expect(fund).toBeVisible();
    await expect(fund.locator(".fund-section__hint")).toHaveCount(0);

    await expect(
      fund.locator(".fund-section__fact", { hasText: "基金经理" })
    ).toContainText("—");

    expect(pageErrors).toEqual([]);
  });

  test("点击胶囊滚动到目标区块且 active 随动", async ({ page }) => {
    await page.goto(`/#/fund/${SYMBOL}`);
    await expect(page.locator(".page-nav")).toBeVisible({ timeout: 60_000 });
    await expect(page.locator(".page-nav__pill.is-active")).toHaveText(
      "我的持仓"
    );

    await page.getByRole("button", { name: "业绩与风险" }).click();
    // 平滑滚动到位：目标区块顶边应落在定位线（滚动容器顶沿 + 胶囊高 + 8）附近。
    // 用 waitForFunction 等滚动停稳，不用固定 sleep——平滑滚动时长随距离变。
    await page.waitForFunction(
      () => {
        const el = document.getElementById("nav-performance");
        if (!el) return false;
        const nav = document.querySelector<HTMLElement>(".page-nav");
        const wrap = document.querySelector<HTMLElement>(
          ".app-main .el-scrollbar__wrap"
        );
        const base = wrap ? wrap.getBoundingClientRect().top : 0;
        const line = base + (nav?.offsetHeight ?? 0) + 8;
        return Math.abs(el.getBoundingClientRect().top - line) < 80;
      },
      null,
      { timeout: 10_000 }
    );
    await expect(page.locator(".page-nav__pill.is-active")).toHaveText(
      "业绩与风险"
    );
  });

  test("scroll-spy：滚动时 active 跟随当前区块", async ({ page }) => {
    await page.goto(`/#/fund/${SYMBOL}`);
    await expect(page.locator(".holding-section")).toBeVisible({
      timeout: 60_000
    });
    await expect(page.locator(".page-nav__pill.is-active")).toHaveText(
      "我的持仓"
    );

    // 滚到「业绩与风险」：它的顶边刚到定位线下方 → active 必须是它
    await scrollSectionUnderLine(page, "nav-performance");
    await expect(page.locator(".page-nav__pill.is-active")).toHaveText(
      "业绩与风险",
      {
        timeout: 5_000
      }
    );

    // 滚到最底部：active 必须是最后一项。最后一项下方没有更多内容把它推过
    // 定位线（maxScroll 截断，实测差 400-600px），按「越过线」判据它永远
    // 选不上——触底时用户看的就是最后一项（主流目录同款行为）。
    // 老判据（最后一个越过定位线的区块）在这里会把高亮永久停在倒数第二项，
    // 那正是用户报的「点最右侧胶囊，高亮不动」。
    await scrollBy(page, 999_999);
    const lastLabel = await page
      .locator(".page-nav__pill")
      .last()
      .textContent();
    await expect(page.locator(".page-nav__pill.is-active")).toHaveText(
      lastLabel!.trim()
    );
  });

  test("逐项点击：停稳后 active 必须是点击项（正序 + 逆序）", async ({
    page
  }) => {
    // 不变式：点击任意胶囊，滚动停稳后高亮必须落在点击项上。
    // 老实现有两个缺陷都会让它红：
    // 1. 定位线零容差 + 落点正好压在线上 → ±0.5px 亚像素抖动让高亮退回
    //    前一项（实测约一半概率中招，用户看到「胶囊来回弹跳、概率性跳对」）；
    // 2. 触底时 maxScroll 截断 → 点最后一项，高亮永远停在倒数第二项。
    // 反向验证：updateActive 的 EPSILON 改回 0 / 去掉触底兜底 → 本用例红。
    await page.goto(`/#/fund/${SYMBOL}`);
    await expect(page.locator(".holding-section")).toBeVisible({
      timeout: 60_000
    });
    const labels = await page
      .locator(".page-nav__pill")
      .evaluateAll(els => els.map(el => el.textContent?.trim() ?? ""));
    expect(labels.length).toBeGreaterThan(2);

    // 正序：从顶部出发逐项往下点（下行跳转 + 触底截断）
    for (const label of labels) {
      await scrollBy(page, 0);
      await page.getByRole("button", { name: label }).click();
      await waitScrollSettle(page);
      await expect(page.locator(".page-nav__pill.is-active")).toHaveText(label);
    }
    // 逆序：从底部出发逐项往上点（上行跳转；首项回顶部后应落在第一项）
    for (const label of [...labels].reverse()) {
      await scrollBy(page, 999_999);
      await page.getByRole("button", { name: label }).click();
      await waitScrollSettle(page);
      await expect(page.locator(".page-nav__pill.is-active")).toHaveText(label);
    }
  });

  test("数据在飞时点击：走势卡长高后落点不漂移", async ({ page }) => {
    // 老缺陷（过期目标）：点击时走势卡还是「正在读取…」的矮态，数据到位后
    // 长成 300px 图表，下方区块整体下移——原生 scrollTo({behavior:'smooth'})
    // 的终点只算一次，按旧布局算的目标整体失效，实测过冲 800+px。
    // 不变式：动画每帧重读目标位置，布局突变后仍收敛到定位线。
    // 反向验证：goTo 换回原生 smooth → 本用例红。
    const trendDates: string[] = [];
    const trendValues: number[] = [];
    for (let i = 30; i > 0; i--) {
      const d = new Date(Date.UTC(2026, 8, 30 - i));
      trendDates.push(d.toISOString().slice(0, 10));
      trendValues.push(+(0.8 + i * 0.001).toFixed(4));
    }
    // 走势数据延迟 2.5s 返回：点击时卡片必在加载态，数据在动画途中到位
    await page.route("**/api/products/trend/**", async route => {
      await new Promise(r => setTimeout(r, 2500));
      await route.fulfill({
        status: 200,
        json: {
          data: {
            symbol: SYMBOL,
            kind: "nav",
            dates: trendDates,
            values: trendValues,
            source: "天天基金",
            basis: "单位净值",
            range: "3M",
            requested_days: 90,
            available_days: 90,
            ohlc: []
          },
          message: "ok"
        }
      });
    });

    await page.goto(`/#/fund/${SYMBOL}`);
    await expect(page.locator(".page-nav")).toBeVisible({ timeout: 60_000 });
    // 走势卡还在加载态（矮）——此刻它下方的区块都还没被推下去
    await expect(page.locator(".trend-section__hint")).toBeVisible();

    // 点走势卡下方的区块：按旧布局算的目标在数据到位后必然过期
    await page.getByRole("button", { name: "基金资料" }).click();

    // 数据到位：卡片长高（v-chart 300px），布局突变发生
    await expect(page.locator(".trend-section__chart")).toBeVisible({
      timeout: 15_000
    });
    // echarts autoresize 落定后再测（布局稳定后的残差才是跳转质量）
    await page.waitForTimeout(400);
    await waitScrollSettle(page);

    const residual = await page.evaluate(() => {
      const el = document.getElementById("nav-fund");
      if (!el) return Number.NaN;
      const nav = document.querySelector<HTMLElement>(".page-nav");
      const wrap = document.querySelector<HTMLElement>(
        ".app-main .el-scrollbar__wrap"
      );
      const base = wrap ? wrap.getBoundingClientRect().top : 0;
      const line = base + (nav?.offsetHeight ?? 0) + 8;
      return el.getBoundingClientRect().top - line;
    });
    expect(Math.abs(residual)).toBeLessThan(8);
    await expect(page.locator(".page-nav__pill.is-active")).toHaveText(
      "基金资料"
    );
  });

  test("触底：点最后一项，高亮与滚动都到底（maxScroll 截断兜底）", async ({
    page
  }) => {
    // 老缺陷：最后一项下方没有内容把它推过定位线（maxScroll 截断，实测差
    // 400-600px），按「越过线」判据它永远选不上——点最右侧胶囊滚到底，
    // 高亮却停在倒数第二项。不变式：滚到底时当前项就是最后一项，
    // 且滚动确实到了底（不是「差一截但高亮对了」）。
    // 2026-10-14 修正断言几何：e2e mock 数据下页面比真实环境高，最后一项
    // **够得着**定位线——把它送到线上（不到底）才是正确行为。故不变式是
    // 「二选一」：送到定位线，或触底（页面太矮、maxScroll 截断）。
    await page.goto(`/#/fund/${SYMBOL}`);
    await expect(page.locator(".holding-section")).toBeVisible({
      timeout: 60_000
    });
    const lastLabel = (await page
      .locator(".page-nav__pill")
      .last()
      .textContent())!.trim();

    await page.getByRole("button", { name: lastLabel }).click();
    await waitScrollSettle(page);

    await expect(page.locator(".page-nav__pill.is-active")).toHaveText(
      lastLabel
    );
    const state = await page.evaluate(() => {
      const wrap = document.querySelector<HTMLElement>(
        ".app-main .el-scrollbar__wrap"
      );
      // 与 useProductPageNav.scan 同源：容器内真实渲染的 nav-* 锚点，
      // 最后一项 = DOM 序最后一个（即最后那颗胶囊）
      const main = document.querySelector<HTMLElement>(".product-detail__main");
      const last = main?.querySelectorAll<HTMLElement>('[id^="nav-"]');
      const lastEl = last && last.length > 0 ? last[last.length - 1] : null;
      if (!wrap || !lastEl) return { atLine: false, atBottom: false };
      const nav = document.querySelector<HTMLElement>(".page-nav");
      const line =
        wrap.getBoundingClientRect().top + (nav?.offsetHeight ?? 0) + 8;
      return {
        atLine: Math.abs(lastEl.getBoundingClientRect().top - line) < 8,
        atBottom: wrap.scrollTop >= wrap.scrollHeight - wrap.clientHeight - 1
      };
    });
    // 「送到定位线」与「触底」二选一即兑现点击意图；两者都不满足才是漂移
    expect(state.atLine || state.atBottom).toBe(true);
  });

  test("响应式两级：<xl 胶囊 / xl+ 右 rail，条目一致", async ({ page }) => {
    await page.goto(`/#/fund/${SYMBOL}`);
    await expect(page.locator(".page-nav")).toBeVisible({ timeout: 60_000 });
    await expect(page.locator(".page-toc")).toBeHidden();
    // 等异步区块（持仓明细）到位，条目才齐——否则两个断点抓到的快照条目数不同
    await expect(page.locator(".holding-section")).toBeVisible({
      timeout: 60_000
    });

    const pillTexts = await page
      .locator(".page-nav__pill")
      .evaluateAll(els => els.map(el => el.textContent?.trim() ?? ""));

    await page.setViewportSize({ width: 1400, height: 900 });
    await expect(page.locator(".page-nav")).toBeHidden();
    const toc = page.locator(".page-toc");
    await expect(toc).toBeVisible();
    // 无视觉标题，但必须有可访问名称（aria-label）——读屏用户靠它认出这个
    // aside 是什么；视觉标题与 aria-label 并存会让读屏听到两次「本页目录」
    await expect(toc).toHaveAttribute("aria-label", "本页目录");
    await expect(toc.locator(".page-toc__link")).toHaveText(pillTexts);

    // rail 是 sticky 的：滚过两个不同深度时位置不变（都进入吸顶态后比对）
    await scrollBy(page, 1500);
    await page.waitForTimeout(300);
    const stuck1 = await toc.boundingBox();
    await scrollBy(page, 2600);
    await page.waitForTimeout(300);
    const stuck2 = await toc.boundingBox();
    expect(Math.abs((stuck2?.y ?? 0) - (stuck1?.y ?? 0))).toBeLessThan(5);
  });

  test("经理页：不渲染的区块不进导航（无死链）", async ({ page }) => {
    // 组件渲染空（v-if 全不中）时父级仍传 id，Vue 的 attribute fallthrough 会
    // 静默丢弃——这条监听钉住「不刷 (id) 相关告警」。只认 (id)：devtools 的
    // data-insp-path 对多根组件同样会告警，那是全应用既有噪声，与本需求无关。
    const attrWarnings: string[] = [];
    page.on("console", msg => {
      if (msg.type() === "warning" && msg.text().includes("(id)")) {
        attrWarnings.push(msg.text());
      }
    });

    // resolve 改判经理品类；走势端点返回 kind 空串（无序列源 → 整卡不渲染）
    await page.route("**/api/products/resolve/**", route =>
      route.fulfill({
        status: 200,
        json: {
          data: {
            symbol: "MGR0001",
            asset_type: "manager",
            market: null,
            venue: null,
            display_name: "测试经理",
            in_watchlist: false,
            has_position: false,
            source: "search"
          },
          message: "ok"
        }
      })
    );
    await page.route("**/api/products/trend/**", route =>
      route.fulfill({
        status: 200,
        json: {
          data: { kind: "", values: [], dates: [], source: "", basis: "" },
          message: "ok"
        }
      })
    );

    await page.goto(`/#/manager/MGR0001`);
    await expect(page.locator(".mgr-section")).toBeVisible({ timeout: 60_000 });
    await page.waitForTimeout(1500);
    await expect(page.locator(".trend-section")).toHaveCount(0);

    const nav = page.locator(".page-nav");
    // 走势（无序列）/ 交易记录（不可交易）/ 基金三张卡（非基金品类）都不该出现
    await expect(nav.locator(".page-nav__pill")).toHaveText([
      "基金经理",
      "关联标的"
    ]);
    await expect(nav.getByRole("button", { name: "走势" })).toHaveCount(0);
    await expect(nav.getByRole("button", { name: "交易记录" })).toHaveCount(0);
    expect(attrWarnings).toHaveLength(0);
  });
});
