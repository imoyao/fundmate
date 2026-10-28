import { expect, test, type Page, type Route } from "@playwright/test";

import { injectSupabaseSession } from "./support/session";

/**
 * 对账工作台页头 / Tab 角标 / 横幅选域回归网（#980 批 B3 拆分 `reconcile-workbench/index.vue`）。
 *
 * 405 → 337：页头搬进 `WorkbenchHead.vue`、Tab 角标搬进 `DomainTabLabel.vue`、
 * 横幅选域顺序收口到 `utils/domainFocus.ts`。纯函数有单测（`domainFocus.spec.ts`，6 例），
 * 这里钉的是**拆分最容易断的那几条线**：
 *
 *   ① `WorkbenchHead` 的两个 emit（`recognize` / `run`）——断掉的症状是「点了没反应」，
 *      没有请求也没有报错，单测（不渲染组件）抓不到。
 *   ② `DomainTabLabel` 走 `<template #label>` 插槽：漏了插槽绑定，角标就永远不出现；
 *      而 `count > 0` 才渲染的判据若被改成「恒渲染」，每个 tab 尾巴上会挂个 0。
 *   ③ 横幅点击选域：顺序取自 `pickFirstPendingDomain`，断掉的表现是「点了横幅，
 *      tab 不动」或「跳到 B 而不是真正有待办的 D」。
 */

type Call = { method: string; path: string; body: unknown };

const GHOST_GROUP = {
  fingerprint: "fp-1",
  symbol: "600519",
  symbol_identity: "600519",
  confirm_date: "2026-10-20",
  txn_type: "buy",
  amount_yuan: 17000,
  ledger_ids: [1, 2],
  ledger_names: ["主账本", "基金账本"],
  count: 2,
  transactions: [
    {
      id: 101,
      ledger_id: 1,
      ledger_name: "主账本",
      quantity: 100,
      price: 170,
      amount_yuan: 17000
    },
    {
      id: 102,
      ledger_id: 2,
      ledger_name: "基金账本",
      quantity: 100,
      price: 170,
      amount_yuan: 17000
    }
  ]
};

/**
 * 只打桩后端接口（vite 源码模块请求不能碰，否则整页白屏）。
 *
 * ⚠️ 前缀不是统一的 `/api/`，这是本页最容易打错桩的地方：
 * - `api/reconciliation.ts` 里的路径**不带** `/api` 前缀（`/reconciliation/run/` 等），
 *   靠 vite 代理转发；
 * - `api/eaccount.ts` 写死了 `/api/e-account/reconciliation/`。
 * 初版只 match `/api/`，结果「运行对账」的 POST 与幽灵重复列表全落到 vite 代理上
 * （一个请求都没被记录），页面侧表现为「点了没反应」「横幅不出现」——**不报错**。
 *
 * ⚠️ 注册顺序 = 匹配优先级（**后注册先匹配**）：
 * 兜底最宽，必须最先注册；`ghost-duplicates/ignored/` 比 `ghost-duplicates/` 更具体，
 * 必须最后注册。曾把兜底放最后，结果它吃掉了所有具体桩，页面静默变成全空。
 *
 * ⚠️ 具体桩会**抢走**兜底的记账：兜底里那句 `calls.push(...)` 对命中具体桩的请求
 * 不生效。所以每个具体桩都必须先 `record(route)` 再 fulfill——初版漏了这一步，
 * 「运行对账」明明发出去了，`calls` 里却一条没有（断言「没发请求」，实际是没记账）。
 */
async function mockApis(
  page: Page,
  opts: { ghostGroups?: number } = {}
): Promise<Call[]> {
  const calls: Call[] = [];
  const groups = (opts.ghostGroups ?? 2) > 0 ? [GHOST_GROUP] : [];

  /** 记账：所有桩（含具体桩）的第一句 */
  function record(route: Route) {
    const url = new URL(route.request().url());
    let body: unknown = null;
    try {
      body = route.request().postDataJSON();
    } catch {
      body = route.request().postData();
    }
    calls.push({ method: route.request().method(), path: url.pathname, body });
  }

  // 兜底：最宽，最先注册（后注册的具体桩会覆盖它）
  await page.route(
    url =>
      url.pathname.startsWith("/api/") ||
      url.pathname.startsWith("/reconciliation/"),
    route => {
      record(route);
      return route.fulfill({ json: { data: [], message: "" } });
    }
  );

  // 域 B / C 的差异（本组用例只要 0 条，确保「B 无待办」）
  await page.route(
    url => url.pathname.startsWith("/reconciliation/discrepancies"),
    route => {
      record(route);
      return route.fulfill({ json: { data: [], message: "" } });
    }
  );

  // 域 E 分红税
  await page.route(
    url => url.pathname.startsWith("/reconciliation/dividend-tax"),
    route => {
      record(route);
      return route.fulfill({ json: { data: [], message: "" } });
    }
  );

  // 域 A E账户对账：无待处理
  await page.route(
    url => url.pathname.startsWith("/api/e-account/reconciliation"),
    route => {
      record(route);
      return route.fulfill({
        json: {
          data: {
            data_date: "2026-10-20",
            items: [],
            summary: {
              pending_count: 0,
              attributed_count: 0,
              ignored_count: 0,
              verified_count: 0
            }
          },
          message: ""
        }
      });
    }
  );

  // 域 D 幽灵重复（宽）——必须早于下面的 /ignored/
  await page.route(
    url => url.pathname.startsWith("/reconciliation/ghost-duplicates"),
    route => {
      record(route);
      return route.fulfill({
        json: { data: { groups, ignored_count: 0 }, message: "" }
      });
    }
  );

  // 已忽略清单（窄，最后注册 → 最先匹配）
  await page.route(
    url => url.pathname.startsWith("/reconciliation/ghost-duplicates/ignored"),
    route => {
      record(route);
      return route.fulfill({ json: { data: [], message: "" } });
    }
  );

  // 运行对账
  await page.route(
    url => url.pathname.startsWith("/reconciliation/run"),
    route => {
      record(route);
      return route.fulfill({ json: { data: {}, message: "" } });
    }
  );

  return calls;
}

async function openWorkbench(page: Page) {
  await page.goto("/#/investment/reconcile-workbench", { waitUntil: "commit" });
  await expect(page.locator(".workbench-head__title")).toBeVisible({
    timeout: 150_000
  });
}

/**
 * 切域后等页面「该动的东西都动完」再断言。
 *
 * 为什么必须有这个等待：本页断言的是**不重挂载**（一个「没发生」的事实）。
 * 重挂载要经过 `router.replace` → 路由状态更新 → `transitionMain` 的 out-in
 * 离场动画（约 300–500ms）→ 新实例 mount。早于这个窗口断言，必然抢在
 * 重挂载之前通过——初版就是这么假绿的（用 `networkidle` 也不够，因为它
 * 只看网络、不看离场动画）。1000ms 已远大于该窗口。
 */
async function settleAfterSwitch(page: Page) {
  await page.waitForTimeout(1000);
}

/**
 * 重挂载探针：在页面组件内部的一枚元素上打标记。
 * 组件被销毁重建时该元素是新节点、不带标记——比"看起来没闪"更硬的判据。
 */
async function probeSurvivesRemount(page: Page) {
  await page
    .locator(".workbench-head")
    .evaluate(el => el.setAttribute("data-mount-probe", "kept"));
}

async function expectMountProbeKept(page: Page) {
  await expect(
    page.locator('.workbench-head[data-mount-probe="kept"]')
  ).toHaveCount(1);
}

test.describe("对账工作台（#980 批 B3 拆分后的接线判据）", () => {
  test.setTimeout(240_000);

  test.beforeEach(async ({ context, baseURL }) => {
    await injectSupabaseSession(context, baseURL!);
  });

  test("页头两枚按钮的 emit 都接通：运行对账发 POST domain=B 并刷新差异", async ({
    page
  }) => {
    const calls = await mockApis(page);
    await openWorkbench(page);

    // 标题 / 副标题随组件搬迁仍在页头
    await expect(page.locator(".workbench-head__title")).toHaveText(
      "对账工作台"
    );
    await expect(page.locator(".workbench-head__subtitle")).toContainText(
      "统一处理 E账户对账"
    );

    const head = page.locator(".workbench-head");
    await expect(head.getByRole("button", { name: "AI 识别" })).toBeVisible();
    await expect(head.getByRole("button", { name: "运行对账" })).toBeVisible();

    const before = calls.filter(c =>
      c.path.startsWith("/reconciliation/discrepancies")
    ).length;

    await head.getByRole("button", { name: "运行对账" }).click();

    // 请求体带 domain=B（域 B 是「算差异」的入口）
    await expect
      .poll(
        () =>
          calls.filter(c => c.path.startsWith("/reconciliation/run")).length,
        { timeout: 15_000 }
      )
      .toBe(1);
    const run = calls.find(c => c.path.startsWith("/reconciliation/run"))!;
    expect(run.method).toBe("POST");
    expect(run.body).toEqual({ domain: "B" });

    // 成功提示 + 差异列表被重新拉取（handleRun 里 Promise.all 的一个分支）。
    // ⚠️ 不能用裸 `.el-message` 断言：页面上同时还挂着别的提示（如会话相关的 info），
    // 多元素命中会触发 strict mode violation。按文案过滤成唯一一条。
    await expect(
      page.locator(".el-message", { hasText: "对账完成" })
    ).toBeVisible();
    await expect
      .poll(
        () =>
          calls.filter(c => c.path.startsWith("/reconciliation/discrepancies"))
            .length,
        { timeout: 15_000 }
      )
      .toBeGreaterThan(before);
  });

  test("AI 识别按钮打开识别弹窗（emit('recognize') 接线）", async ({
    page
  }) => {
    await mockApis(page);
    await openWorkbench(page);

    await page
      .locator(".workbench-head")
      .getByRole("button", { name: "AI 识别" })
      .click();
    await expect(page.locator(".el-dialog__title")).toContainText(
      "AI 识别入库"
    );
  });

  test("Tab 角标只在有待办时出现；点横幅按固定顺序跳到第一个有待办的域", async ({
    page
  }) => {
    // B / C / A / E 全空，只有 D 有 1 组 → pickFirstPendingDomain 必须越过 B 落到 D
    await mockApis(page, { ghostGroups: 1 });
    await openWorkbench(page);

    // 横幅：总数 = 域 D 的组数
    const banner = page.locator(".workbench-banner");
    await expect(banner).toContainText("有 1 项差异待处理");

    // 角标：只有「跨账本重复」这一页签挂角标，其余 tab 不许挂 0
    const badges = page.locator(".workbench-tabs .domain-tab-count");
    await expect(badges).toHaveCount(1);
    await expect(badges.first()).toHaveText("1");
    await expect(
      page.locator(".workbench-tabs .el-tabs__item", { hasText: "跨账本重复" })
    ).toContainText("1");

    // 点击横幅 → 切到域 D。这是**页内**切换，只该换下半屏内容，
    // 不得重挂载整个页面组件，更不得把域写进 URL（#2706）。
    await probeSurvivesRemount(page);
    await banner.click();
    await expect(
      page.locator(".workbench-tabs .el-tabs__item.is-active")
    ).toContainText("跨账本重复");
    // ⚠️ 必须先等过渡结束：Vue 的重渲染在 nextTick，out-in 离场动画还要再占几百毫秒，
    // 点击后立刻断言"标记还在"会抢在重挂载之前通过——那是竞态，不是判据（初版即栽在这里）。
    await settleAfterSwitch(page);
    await expectMountProbeKept(page);
    // 不写回 URL：布局层以 route.fullPath 作 router-view 的 key，
    // query 一动就整页重建（onMounted 五个加载器全跑 = 用户看到的「整页刷新」）。
    expect(new URL(page.url()).hash).not.toContain("domain=");
  });

  test("切 tab 不重挂载页面：URL 不变、首屏加载器不重跑（#2706）", async ({
    page
  }) => {
    const calls = await mockApis(page, { ghostGroups: 1 });
    await openWorkbench(page);
    // 等首屏请求收敛再取基线。不锁具体次数：布局层横幅与本页各拉一次差异，
    // 写死次数等于把"谁发的"冻结进断言，改动无关代码就会误报。
    await page.waitForLoadState("networkidle");
    await probeSurvivesRemount(page);
    const before = calls.length;

    // ⚠️ 必须点一个**非默认域**的 tab：默认落在域 B，点「持仓快照」等于原地不动，
    // `activeDomain` 不变化就不会触发下文的写回——用例会变成空转（初版即栽在这里）。
    await page
      .locator(".workbench-tabs .el-tabs__item", { hasText: "分红未扣税" })
      .click();

    await expect(
      page.locator(".workbench-tabs .el-tabs__item.is-active")
    ).toContainText("分红未扣税");
    // 等过渡结束再看：重挂载 ⇒ onMounted 跑五个加载器 ⇒ 请求数必然增长
    await settleAfterSwitch(page);
    // 组件实例没被销毁（重挂载会连 `.workbench-head` 一起重建，标记随之消失）
    await expectMountProbeKept(page);
    expect(calls.length).toBe(before);
    expect(new URL(page.url()).hash).not.toContain("domain=");
  });
});
