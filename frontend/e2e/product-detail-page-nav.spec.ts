import { expect, test, type Page } from "@playwright/test";
import { injectSupabaseSession } from "./support/session";
import { fundProfileFixture, withoutFields } from "./fixtures/productDetail";

/**
 * 详情页页内导航回归网（#1968 子卡；2026-11-25 形态变更为**页头右上角下拉**）。
 *
 * ## 形态为什么又变了
 *
 * 上一版是两级投影：`<xl` 顶部锚点胶囊、`xl+` 右侧目录 rail。投顾组合页把区块拆成
 * 六个之后两个投影都出了问题——胶囊占掉正文上方一整行且会挤成两行横滑；rail 固定
 * 吃掉 160px 内容宽，而「方向对照」的五列网格 + 双条形完全靠宽度才能读。
 * 现在收进页头右上角（`components/PageTocMenu`），正文拿回完整内容宽；
 * 「现在在哪一节」由按钮上的当前项名称持续回答，不需要一整列常驻。
 *
 * **状态与滚动机制一行没改**（仍是 `usePageNav`：DOM 扫描出条目、scroll-spy、
 * 自绘 rAF 跳转），变的只是投影——所以下面这些不变式照旧成立，判据从
 * `.page-nav__pill` 迁到 `.toc-menu__btn` / `.toc-menu__item`：
 *
 * 1. **无死链**：导航项只列 DOM 里真实渲染的区块——走势对 manager 整卡不渲染、
 *    交易记录对非可交易品类不渲染，这些都不能出现在目录里（点了原地不动即为死链）；
 * 2. 点击目录项平滑滚动到目标区块，**按钮上的当前项名称**随动；
 * 3. scroll-spy：滚动时当前项跟随当前区块；**触底时当前项 = 最后一项**
 *    （maxScroll 截断下最后一项永远到不了定位线，老判据会把高亮永久停在倒数第二项）；
 * 4. 逐项点击（正序 + 逆序）：停稳后当前项必须是点击项——钉住「定位线零容差
 *    导致的亚像素回跳」，也钉住 maxScroll 截断；
 * 5. 数据在飞时点击下方区块：布局突变（走势卡长高 300+px）后落点不漂移；
 * 6. **面板几何**：绝对定位的浮层不许撑破视口（窄屏尤其），且各宽度都可用；
 * 7. **开合语义**：aria-expanded / aria-haspopup、`aria-current="location"`、
 *    Esc 关闭并回焦、点外部关闭——浮层的可访问性只能在真浏览器里验。
 *
 * 接口全部 page.route 打桩，不依赖后端（docs/dev/frontend-e2e.md §7）。
 *
 * 反向验证：
 * - 删掉 detail.vue 里 `<PageTocMenu>` 挂载 → 本文件全红（按钮不存在）；
 * - 把 useProductPageNav 的 items 过滤改成静态清单 → 经理页用例红（死链回归）；
 * - 去掉 `<ProductTransactionSection>` 的 has_position 条件 → 「无持仓」用例红；
 * - `updateActive` 的 EPSILON 改回 0 → 逐项点击用例红（亚像素回跳回归）；
 * - 去掉触底兜底 → scroll-spy 用例的触底断言红；
 * - `goTo` 不设 pinnedId → 逐项点击逆序列红；
 * - `goTo` 换回原生 `scrollTo({behavior:'smooth'})` → 数据在飞机用例红；
 * - `scrollGeometry.scrollerProbe` 退回只认 `.page-nav` → 「落点压在定位线」断言红
 *   （实测残差 −81px：整条定位线少算一个页头高度，区块顶边被塞到页头下面）。
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

/**
 * 定位线（视口坐标）＝滚动容器顶沿 + 8px，与 `usePageNav` 的 `spyLine()` 同源。
 *
 * **没有胶囊后增量为 0**：旧形态下胶囊吸顶、占掉自己那一行高度；现在导航在页头里，
 * 随内容一起滚走，滚动区顶沿就是定位线。三处判据（送线上 / 落点残差 / 触底几何）
 * 都各自在浏览器里现算这两行——不抽成字符串常量（那要靠 eval 才用得上），
 * 也不抽成外部函数（`page.evaluate` 的回调是序列化执行的，拿不到模块作用域）。
 */
async function scrollSectionUnderLine(page: Page, id: string) {
  const top = await page.evaluate(anchorId => {
    const el = document.getElementById(anchorId);
    if (!el) return null;
    const wrap = document.querySelector<HTMLElement>(
      ".app-main .el-scrollbar__wrap"
    );
    const scroller =
      wrap && wrap.scrollHeight > wrap.clientHeight + 1 ? wrap : null;
    const line = (wrap ? wrap.getBoundingClientRect().top : 0) + 8;
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

/** 触发按钮上的当前项名称 = 「现在在哪一节」（旧形态是 `pill.is-active`） */
function activeLabel(page: Page) {
  return page.locator(".toc-menu__btn .toc-menu__label");
}

async function openMenu(page: Page, real = false) {
  const btn = page.locator(".toc-menu__btn");
  await expect(btn).toBeVisible();
  if ((await btn.getAttribute("aria-expanded")) !== "true") {
    if (real) await btn.click();
    else await btn.dispatchEvent("click");
  }
  await expect(page.locator(".toc-menu__panel")).toBeVisible();
}

/** 读目录条目（开 → 读 → 关，不在页面上留浮层） */
async function navLabels(page: Page, real = false): Promise<string[]> {
  await openMenu(page, real);
  const labels = await page
    .locator(".toc-menu__item")
    .evaluateAll(els => els.map(el => el.textContent?.trim() ?? ""));
  await page.keyboard.press("Escape");
  await expect(page.locator(".toc-menu__panel")).toHaveCount(0);
  return labels;
}

/**
 * 点目录项跳转（下拉形态的代价：每次都得先展开浮层）。
 *
 * `real = false` 时用 `dispatchEvent("click")` 而不是 `.click()`——**这是判据的一部分**：
 * Playwright 的真实点击会先把目标滚进可视区，而触发按钮在页头里（随内容滚走）。
 * 页面已经滚到底时点按钮，浏览器会把 `scrollTop` 归零，于是「从底部往上跳」被测成
 * 「从顶部往下跳」、scroll-spy 测到的当前项也退回第一项（实测：滚到底后 label
 * 已是「更多数据」，一点按钮就变回「我的持仓」）。
 * 真实点击的可达性由「目录开合」与「点击目录项滚动」两条用例用 `.click()` 单独覆盖。
 */
async function goTo(page: Page, label: string, real = false) {
  await openMenu(page, real);
  const item = page.locator(".toc-menu__item", { hasText: label }).first();
  if (real) await item.click();
  else await item.dispatchEvent("click");
  await expect(page.locator(".toc-menu__panel")).toHaveCount(0);
}

/** 目标区块顶边相对定位线的残差（px）；负数 = 落点偏上（被容器顶沿裁掉） */
async function lineResidual(page: Page, id: string) {
  return page.evaluate(anchorId => {
    const el = document.getElementById(anchorId);
    if (!el) return Number.NaN;
    const wrap = document.querySelector<HTMLElement>(
      ".app-main .el-scrollbar__wrap"
    );
    const line = (wrap ? wrap.getBoundingClientRect().top : 0) + 8;
    return el.getBoundingClientRect().top - line;
  }, id);
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
  // #2958：此前这里只写 8 个字段，而 FundProfileResult 有 21 个——本文件 12 个用例
  // 全部跑在「字段缺失 ⇒ 降级为 —」的防御态上，看到的页面和用户看到的不是同一个。
  // 完整桩收口在 e2e/fixtures/productDetail.ts，「缺字段」语义只由 #2191 那条显式构造。
  await page.route("**/api/products/fund-profile/**", route =>
    route.fulfill({
      status: 200,
      json: { data: fundProfileFixture(), message: "ok" }
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
    // 不再有断点两级：页头下拉在任何宽度都是同一个形态（见 §响应式用例）
    await page.setViewportSize({ width: 1100, height: 900 });
  });

  test("基金页：目录只列真实渲染的区块（无死链）", async ({ page }) => {
    await page.goto(`/#/fund/${SYMBOL}`);
    // 等持仓明细到位（异步取数后才出现的锚点）
    await expect(page.locator(".holding-section")).toBeVisible({
      timeout: 60_000
    });

    const labels = await navLabels(page);
    expect(labels).toEqual([
      "我的持仓",
      "走势",
      "交易记录",
      "基金资料",
      "业绩与风险",
      // 高级洞察 Pro 紧跟业绩与风险（高价值模块不沉底；详情页区块顺序的投影）
      "高级洞察 Pro",
      "行业与持仓",
      // 相似基金（#2480）/ 投资风格（#2478）：两区块合入 dev 时漏更新本断言，
      // 因 E2E 不进 per-PR 门禁（#1568）而一直没转红——本 PR 连过期项一并修正
      "相似基金",
      "投资风格",
      "关联标的",
      "更多数据"
    ]);

    // 每个条目都必须有对应锚点——死链是这条不变式的反面
    // （items 由 DOM 扫描生成，数量必然相等；静态清单回归会让它不相等）。
    // 条目数取浮层里读到的列表长度：`navLabels` 读完就 Esc 收起，DOM 里已没有 item。
    const anchors = await page.evaluate(
      () =>
        document.querySelectorAll('.product-detail__main [id^="nav-"]').length
    );
    expect(labels.length).toBe(anchors);
  });

  test("目录开合：aria 状态、当前项 aria-current、Esc 回焦、点外部关闭", async ({
    page
  }) => {
    // 浮层的可访问性只能在真浏览器里验：焦点回还、aria-current 的取值、
    // 点击面板外部（页面别处）是否收敛，都是 DOM 行为而非纯样式。
    await page.goto(`/#/fund/${SYMBOL}`);
    await expect(page.locator(".toc-menu__btn")).toBeVisible({
      timeout: 60_000
    });

    const btn = page.locator(".toc-menu__btn");
    await expect(btn).toHaveAttribute("aria-haspopup", "true");
    await expect(btn).toHaveAttribute("aria-expanded", "false");
    // 未展开时按钮已显示当前所在区块（不需要展开才知道自己在哪）
    await expect(activeLabel(page)).toHaveText("我的持仓");

    await btn.click();
    await expect(btn).toHaveAttribute("aria-expanded", "true");
    // 当前项用 aria-current="location"（读屏读到「当前所在位置」，不是「选中」）
    await expect(
      page.locator('.toc-menu__item[aria-current="location"]')
    ).toHaveText("我的持仓");
    await expect(
      page.locator(".toc-menu__item", { hasText: "我的持仓" })
    ).toHaveClass(/is-active/);

    // Esc 关闭并把焦点还给触发按钮（否则焦点落到 body，键盘用户丢失位置）
    await page.keyboard.press("Escape");
    await expect(page.locator(".toc-menu__panel")).toHaveCount(0);
    await expect(btn).toBeFocused();

    // 点面板外部关闭
    await btn.click();
    await expect(page.locator(".toc-menu__panel")).toBeVisible();
    await page.locator(".page-header__title").click();
    await expect(page.locator(".toc-menu__panel")).toHaveCount(0);
  });

  test("高级洞察 Pro 占位：区块渲染 + 徽标来自状态位（#2272）", async ({
    page
  }) => {
    // #2272（#994 Phase 1 接口骨架 + 付费墙壳）。钉三件事：
    // ① 区块真的渲染了——#2029 同款静默消失防线：detail.vue 的 import 被删时
    //    Vue 只发 warning，父级透传的 id 静默丢弃，页面无可见报错；
    // ② 徽标（Phase N 建设中）来自后端状态位而非前端硬编码（不编造"已上线"）；
    // ③ 目录收录该区块（与锚点同在，无死链）。
    // 注：付费墙遮罩的 e2e 断言已随 #994 Phase 2 移除——playwright.config 显式
    // VITE_PRO_PAYWALL_ENABLED=false（CI 无 .env.local），遮罩是纯 CSS 视觉件。
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
            // 未开通态（#2523 两态拆分）：介绍卡只有未开通家庭看得到。
            paywall_required: true,
            modules: {
              performance: { available: false, phase: 2 },
              risk: { available: false, phase: 2 },
              // ⚠️ 本用例测的就是「未上线 ⇒ 徽标渲染 Phase N 建设中」这条占位路径，
              // 故四个模块**全部** false——不要跟着后端状态位去同步成 true，
              // 那会把本用例的唯一测试意图（徽标来自 status.phase）抹掉。
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

    // 目录收录该区块（与锚点同在，无死链）
    expect(await navLabels(page)).toContain("高级洞察 Pro");
    expect(pageErrors).toEqual([]);
  });

  test("无持仓：交易记录不渲染、不进目录、不发请求", async ({ page }) => {
    // #2104 行为修正：交易流水是用户自己的账本数据，与「我的持仓」同条件——
    // 仅当前持有时渲染。未持有用户不该看到一张「暂无交易记录」空卡，
    // 也不该为它打一次无用请求，目录更不该多一项死重量。
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
    await expect(page.locator(".toc-menu__btn")).toBeVisible({
      timeout: 60_000
    });

    const labels = await navLabels(page);
    expect(labels).not.toContain("交易记录");
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

    // compact 列集（顺序即契约）：无产品列/手续费/操作列；
    // 详情页另经 #extra-columns 注入重放两列（当时成本/收益贡献，#2171 P2）
    await expect(table.locator(".el-table__header th")).toHaveText([
      "交易日期",
      "类型",
      "价格",
      "数量",
      "金额",
      "账户",
      "当时成本",
      "收益贡献"
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

  test("基金资料：完整响应下经理/费率/晨星真渲染（#2958）", async ({
    page
  }) => {
    // #2958：本文件 12 个用例此前共用一份只有 8 个字段的 fund-profile 桩，基金资料
    // 区块全程是「—」——经理、费率、晨星三条渲染分支在 e2e 里从未见过真实数据。
    const pageErrors: string[] = [];
    page.on("pageerror", e => pageErrors.push(e.message));

    await page.goto(`/#/fund/${SYMBOL}`);
    const fund = page.locator("#nav-fund");
    await expect(fund).toBeVisible({ timeout: 60_000 });

    // 先证明桩接上了：区块渲染出真实内容，而非「暂无可展示」空态（取数失败时
    // 下面所有 toContainText 都会假绿）
    await expect(fund.locator(".fund-section__nav")).toBeVisible();

    const cell = (label: string) =>
      fund.locator(".facts-grid__cell", { hasText: label });

    // 基金经理：姓名真渲染，代表作徽标只挂在 is_classic 那一只上
    await expect(cell("基金经理")).toContainText("测试经理");
    await expect(cell("基金经理")).toContainText("协同经理");
    await expect(cell("基金经理").locator(".fund-section__badge")).toHaveCount(
      1
    );

    // 与经理无关的字段一并证明「整份响应到了」：规模 / 成立日期 / 业绩基准
    await expect(cell("规模")).toContainText("12.34 亿元");
    await expect(cell("成立日期")).toContainText("2022-03-15");
    await expect(fund).toContainText("中证北证50");

    // 晨星（#1440）：口径在纯函数里有单测，但「组件有没有把算好的值渲染进 DOM」
    // 这一环在 e2e 里此前是零覆盖
    await expect(cell("晨星评级")).toContainText("4 星（3年期）");
    await expect(cell("晨星评级")).toContainText("较上期 升1星");

    // 费率：申购取最低档（含条件与「分档递减」标记），赎回取首档惩罚档
    await expect(cell("申购费率")).toContainText("1.20%");
    await expect(cell("申购费率")).toContainText("100 万以下");
    await expect(cell("赎回费率")).toContainText("1.50%");
    await expect(cell("赎回费率")).toContainText("不足 7 天");

    expect(pageErrors).toEqual([]);
  });

  test("基金经理字段缺失：降级为「—」，不抛错不消失（#2191）", async ({
    page
  }) => {
    // 本用例是 e2e 中**唯一**允许 fund-profile 缺字段的地方（#2958）：其余用例一律
    // 走 fundProfileFixture() 的完整 21 字段。缺字段语义只在这里显式构造，否则
    // 「降级路径真的生效」与「基线本来就没这个字段、一路陪跑」在 DOM 上不可分辨。
    //
    // #2191：模板曾裸取 profile.managers.length，缺该字段时渲染抛 TypeError。Vue 把
    // 渲染错误吞进子组件（父级透传的 #nav-fund 锚点可能还在），整块基金资料渲染成
    // 空、页面无可见报错——本用例钉两条：
    // ① 基金经理行降级为「—」；② 加载全程零 pageerror。
    const pageErrors: string[] = [];
    page.on("pageerror", e => pageErrors.push(e.message));

    // 后注册的 route 优先：覆盖 beforeEach 里的完整桩，只摘掉 managers 一个键
    await page.route("**/api/products/fund-profile/**", route =>
      route.fulfill({
        status: 200,
        json: {
          data: withoutFields(fundProfileFixture(), ["managers"]),
          message: "ok"
        }
      })
    );

    await page.goto(`/#/fund/${SYMBOL}`);
    await expect(page.locator(".toc-menu__btn")).toBeVisible({
      timeout: 60_000
    });

    // 先证明桩接上了、且缺的**只是 managers**：与它无关的字段必须照常有值。
    const fund = page.locator("#nav-fund");
    await expect(fund).toBeVisible();
    await expect(fund.locator(".fund-section__nav")).toBeVisible();
    await expect(
      fund.locator(".facts-grid__cell", { hasText: "基金公司" })
    ).toContainText("永赢基金管理有限公司");
    await expect(
      fund.locator(".facts-grid__cell", { hasText: "规模" })
    ).toContainText("12.34 亿元");

    // 缺失的那一格降级为「—」（`ProductFundSection.vue` 的 `v-else {{ DASH }}`）
    await expect(
      fund.locator(".facts-grid__cell", { hasText: "基金经理" })
    ).toContainText("—");

    expect(pageErrors).toEqual([]);
  });

  test("点击目录项滚动到目标区块且当前项随动", async ({ page }) => {
    await page.goto(`/#/fund/${SYMBOL}`);
    await expect(page.locator(".toc-menu__btn")).toBeVisible({
      timeout: 60_000
    });
    await expect(activeLabel(page)).toHaveText("我的持仓");

    await goTo(page, "业绩与风险", true);
    // 平滑滚动结束后残差必须落在定位线上（±8px）。这里不做固定 sleep——
    // 平滑滚动时长随距离变，用 waitForFunction 等收敛。
    await page.waitForFunction(
      () => {
        const el = document.getElementById("nav-performance");
        if (!el) return false;
        const wrap = document.querySelector<HTMLElement>(
          ".app-main .el-scrollbar__wrap"
        );
        const line = (wrap ? wrap.getBoundingClientRect().top : 0) + 8;
        return Math.abs(el.getBoundingClientRect().top - line) < 8;
      },
      null,
      { timeout: 10_000 }
    );
    await expect(activeLabel(page)).toHaveText("业绩与风险");
  });

  test("scroll-spy：滚动时当前项跟随当前区块", async ({ page }) => {
    await page.goto(`/#/fund/${SYMBOL}`);
    await expect(page.locator(".holding-section")).toBeVisible({
      timeout: 60_000
    });
    await expect(activeLabel(page)).toHaveText("我的持仓");
    // 条目在**滚动之前**读：滚到底后再开浮层，浮层在页头里、点它会把页面滚回顶部
    const labels = await navLabels(page);

    // 滚到「业绩与风险」：它的顶边刚到定位线下方 → 当前项必须是它
    await scrollSectionUnderLine(page, "nav-performance");
    await expect(activeLabel(page)).toHaveText("业绩与风险", {
      timeout: 5_000
    });

    // 滚到最底部：当前项必须是最后一项。最后一项下方没有更多内容把它推过
    // 定位线（maxScroll 截断，实测差 400-600px），按「越过线」判据它永远
    // 选不上——触底时用户看的就是最后一项（主流目录同款行为）。
    await scrollBy(page, 999_999);
    await expect(activeLabel(page)).toHaveText(labels[labels.length - 1]);
  });

  test("逐项点击：停稳后当前项必须是点击项（正序 + 逆序）", async ({
    page
  }) => {
    // 不变式：点任意目录项，滚动停稳后当前项必须落在点击项上。
    // 老实现有两个缺陷都会让它红：
    // 1. 定位线零容差 + 落点正好压在线上 → ±0.5px 亚像素抖动让高亮退回
    //    前一项（实测约一半概率中招，用户看到「概率性跳对」）；
    // 2. 触底时 maxScroll 截断 → 点最后一项，高亮永远停在倒数第二项。
    await page.goto(`/#/fund/${SYMBOL}`);
    await expect(page.locator(".holding-section")).toBeVisible({
      timeout: 60_000
    });
    const labels = await navLabels(page);
    expect(labels.length).toBeGreaterThan(2);

    // 正序：从顶部出发逐项往下点（下行跳转 + 触底截断）
    for (const label of labels) {
      await scrollBy(page, 0);
      await goTo(page, label);
      await waitScrollSettle(page);
      await expect(activeLabel(page)).toHaveText(label);
    }
    // 逆序：从底部出发逐项往上点（上行跳转；首项回顶部后应落在第一项）
    for (const label of [...labels].reverse()) {
      await scrollBy(page, 999_999);
      await goTo(page, label);
      await waitScrollSettle(page);
      await expect(activeLabel(page)).toHaveText(label);
    }
  });

  test("数据在飞时点击：走势卡长高后落点不漂移", async ({ page }) => {
    // 老缺陷（过期目标）：点击时走势卡还是「正在读取…」的矮态，数据到位后
    // 长成 300px 图表，下方区块整体下移——原生 scrollTo({behavior:'smooth'})
    // 的终点只算一次，按旧布局算的目标整体失效，实测过冲 800+px。
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
    await expect(page.locator(".toc-menu__btn")).toBeVisible({
      timeout: 60_000
    });
    // 走势卡还在加载态（矮）——此刻它下方的区块都还没被推下去
    await expect(page.locator(".trend-section__hint")).toBeVisible();

    // 点走势卡下方的区块：按旧布局算的目标在数据到位后必然过期
    await goTo(page, "基金资料", true);

    // 数据到位：卡片长高（v-chart 300px），布局突变发生
    await expect(page.locator(".trend-section__chart")).toBeVisible({
      timeout: 15_000
    });
    // echarts autoresize 落定后再测（布局稳定后的残差才是跳转质量）
    await page.waitForTimeout(400);
    await waitScrollSettle(page);

    expect(Math.abs(await lineResidual(page, "nav-fund"))).toBeLessThan(8);
    await expect(activeLabel(page)).toHaveText("基金资料");
  });

  test("触底：点最后一项，当前项与滚动都到位（maxScroll 截断兜底）", async ({
    page
  }) => {
    // 老缺陷：最后一项下方没有内容把它推过定位线（maxScroll 截断，实测差
    // 400-600px），按「越过线」判据它永远选不上——点最后一项滚到底，
    // 高亮却停在倒数第二项。不变式：「送到定位线」或「触底」二选一，
    // 两者都不满足才是漂移（e2e mock 数据下页面够高时能送到线）。
    await page.goto(`/#/fund/${SYMBOL}`);
    await expect(page.locator(".holding-section")).toBeVisible({
      timeout: 60_000
    });
    const labels = await navLabels(page);
    const lastLabel = labels[labels.length - 1];

    await goTo(page, lastLabel);
    await waitScrollSettle(page);

    await expect(activeLabel(page)).toHaveText(lastLabel);
    const state = await page.evaluate(() => {
      const wrap = document.querySelector<HTMLElement>(
        ".app-main .el-scrollbar__wrap"
      );
      // 与 usePageNav.scan 同源：容器内真实渲染的 nav-* 锚点，
      // 最后一项 = DOM 序最后一个
      const main = document.querySelector<HTMLElement>(".product-detail__main");
      const list = main?.querySelectorAll<HTMLElement>('[id^="nav-"]');
      const lastEl = list && list.length > 0 ? list[list.length - 1] : null;
      if (!wrap || !lastEl) return { atLine: false, atBottom: false };
      const line = wrap.getBoundingClientRect().top + 8;
      return {
        atLine: Math.abs(lastEl.getBoundingClientRect().top - line) < 8,
        atBottom: wrap.scrollTop >= wrap.scrollHeight - wrap.clientHeight - 1
      };
    });
    expect(state.atLine || state.atBottom).toBe(true);
  });

  test("响应式：页头下拉在各宽度都可用，条目一致且不撑破视口", async ({
    page
  }) => {
    // 旧形态是「<xl 胶囊 / xl+ rail」两级互斥。收到页头后**不再有断点分支**：
    // 三种宽度下都是同一个按钮。要钉的是两件事——条目集合与宽度无关（状态同源，
    // 只是投影不变），以及绝对定位浮层不产生横向溢出（窄屏最容易踩）。
    await page.goto(`/#/fund/${SYMBOL}`);
    await expect(page.locator(".holding-section")).toBeVisible({
      timeout: 60_000
    });

    const baseline = await navLabels(page);
    await expect(page.locator(".toc-menu__btn")).toBeVisible();

    for (const width of [1400, 768, 390]) {
      await page.setViewportSize({ width, height: 900 });
      await expect(page.locator(".toc-menu__btn")).toBeVisible();
      await openMenu(page);
      const labels = await page
        .locator(".toc-menu__item")
        .evaluateAll(els => els.map(el => el.textContent?.trim() ?? ""));
      expect(labels).toEqual(baseline);
      // 浮层是 absolute + right:0 —— 宽度固定 240px，窄屏下若定位错了会顶破视口
      const overflow = await page.evaluate(() => {
        const doc = document.documentElement;
        return doc.scrollWidth - doc.clientWidth;
      });
      expect(overflow, `${width}px 视口出现横向溢出`).toBe(0);
      await page.keyboard.press("Escape");
    }
  });

  test("经理页：不渲染的区块不进目录（无死链）", async ({ page }) => {
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

    // 走势（无序列）/ 交易记录（不可交易）/ 基金三张卡（非基金品类）都不该出现
    expect(await navLabels(page)).toEqual(["基金经理", "关联标的"]);
    expect(attrWarnings).toHaveLength(0);
  });
});
