import { expect, test, type Page } from "@playwright/test";
import { injectSupabaseSession } from "./support/session";

/**
 * 详情页页内导航回归网（#1968 子卡：顶部锚点胶囊 + xl 右目录 rail）。
 *
 * 钉五条不变式：
 * 1. **无死链**：导航项只列 DOM 里真实渲染的区块——走势对 manager 整卡不渲染、
 *    交易记录对非可交易品类不渲染，这些都不能出现在胶囊里（点了原地不动即为死链）；
 * 2. 点击胶囊平滑滚动到目标区块，active 态随动；
 * 3. scroll-spy：滚动容器滚动时 active 跟随当前区块；
 * 4. 响应式两级：<xl 胶囊可见 + rail 隐藏；xl+ 反之；
 * 5. xl+ 右 rail 与胶囊列同一批条目（两级是同一状态的两个投影）。
 *
 * 接口全部 page.route 打桩，不依赖后端（docs/dev/frontend-e2e.md §7）。
 *
 * 反向验证：删掉 detail.vue 里 <ProductPageNav> 挂载 → 本文件全红；
 * 把 useProductPageNav 的 items 过滤改成静态清单 → 经理页用例红（死链回归）。
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

async function stubProductApis(page: Page) {
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
          has_position: true,
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
      "第三方数据"
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

    // 滚到最底部：active 应等于「最后一个顶边在定位线上方」的区块
    // （不能写死期望值——最底部能滚到哪由内容高度决定，写死会随数据漂移；
    // 判据与 useProductPageNav.updateActive 一致）
    await scrollBy(page, 999_999);
    const bottom = await page.evaluate(() => {
      const nav = document.querySelector<HTMLElement>(".page-nav");
      const wrap = document.querySelector<HTMLElement>(
        ".app-main .el-scrollbar__wrap"
      );
      const base = wrap ? wrap.getBoundingClientRect().top : 0;
      const line = base + (nav?.offsetHeight ?? 0) + 8;
      const anchors = Array.from(
        document.querySelectorAll<HTMLElement>(
          '.product-detail__main [id^="nav-"]'
        )
      );
      let idx = 0;
      anchors.forEach((el, i) => {
        if (el.getBoundingClientRect().top <= line) idx = i;
      });
      const pills = Array.from(
        document.querySelectorAll<HTMLElement>(".page-nav__pill")
      );
      return pills[idx]?.textContent?.trim() ?? "";
    });
    await expect(page.locator(".page-nav__pill.is-active")).toHaveText(bottom);
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
    await expect(toc.getByText("本页目录")).toBeVisible();
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
