import { expect, test, type Page, type Route } from "@playwright/test";

import { injectSupabaseSession } from "./support/session";

/**
 * 对账工作台页头 / 首屏分段回归网（#980 批 B3 拆分 `reconcile-workbench/index.vue`；
 * 2026-11-19 UI/UX 深度重构后收紧）。
 *
 * 本轮删掉了旧页头的「AI 识别」按钮、横幅选域（WorkbenchBanner）与任务卡
 * （WorkbenchTaskCards）。这里钉的是重构后**最容易断的两条线**：
 *
 *   ① `WorkbenchHead` 只剩一个 `run` emit——断掉的表现是「点了重新检查持仓差异没反应」，
 *      没有请求也没有报错，单测（不渲染组件）抓不到。同时锁死「AI 识别」已移出页头，
 *      回归到「导入交割单」队列项的抽屉内（owner 拍板）。
 *   ② 首屏默认展示「能一键处理(ready)」，ready=0 时自动落到「要你判断(judge)」。
 *      这是 `useReconQueue` 的 watch 落档，断掉的表现是「首屏一片空 / 卡在 ready 空档」。
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
 * ⚠️ 桩路径必须与真实请求**逐字一致**，这是本页最容易打错桩的地方：
 * - 所有后端接口都走 `/api/` 前缀（vite 只代理 `/api`，见 vite.config.ts）；
 *   `api/reconciliation.ts` 曾漏写 `/api`，请求打到 vite 的 SPA 回退拿到 HTML
 *   （HTTP 200），前端把 HTML 当数据 → 整页显示 0 条且不报错（#2866 实测）。
 * - `api/eaccount.ts` 写死 `/api/e-account/reconciliation/`。
 *
 * ⚠️ 注册顺序 = 匹配优先级（**后注册先匹配**）：
 * 兜底最宽，必须最先注册；`ghost-duplicates/ignored/` 比 `ghost-duplicates/` 更具体，
 * 必须最后注册。
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
    url => url.pathname.startsWith("/api/"),
    route => {
      record(route);
      return route.fulfill({ json: { data: [], message: "" } });
    }
  );

  // 域 B / C 的差异（本组用例只要 0 条，确保「B 无待办」）
  await page.route(
    url => url.pathname.startsWith("/api/reconciliation/discrepancies"),
    route => {
      record(route);
      return route.fulfill({ json: { data: [], message: "" } });
    }
  );

  // 域 E 分红税
  await page.route(
    url => url.pathname.startsWith("/api/reconciliation/dividend-tax"),
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
    url => url.pathname.startsWith("/api/reconciliation/ghost-duplicates"),
    route => {
      record(route);
      return route.fulfill({
        json: { data: { groups, ignored_count: 0 }, message: "" }
      });
    }
  );

  // 已忽略清单（窄，最后注册 → 最先匹配）
  await page.route(
    url =>
      url.pathname.startsWith("/api/reconciliation/ghost-duplicates/ignored"),
    route => {
      record(route);
      return route.fulfill({ json: { data: [], message: "" } });
    }
  );

  // 运行对账
  await page.route(
    url => url.pathname.startsWith("/api/reconciliation/run"),
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

test.describe("对账工作台（页头主行动 + 首屏分段落档）", () => {
  test.setTimeout(240_000);

  test.beforeEach(async ({ context, baseURL }) => {
    await injectSupabaseSession(context, baseURL!);
  });

  test("页头只留「重新检查持仓差异」：发 POST domain=B 并刷新差异；AI 识别已移出页头", async ({
    page
  }) => {
    const calls = await mockApis(page);
    await openWorkbench(page);

    // 标题 / 副标题仍由统一页头承接
    await expect(page.locator(".workbench-head__title")).toHaveText("对账中心");
    await expect(page.locator(".workbench-head__subtitle")).toContainText(
      "统一处理 E账户对账"
    );

    const head = page.locator(".workbench-head");
    await expect(
      head.getByRole("button", { name: "重新检查持仓差异" })
    ).toBeVisible();
    // owner 拍板：AI 识别不再放页头，回归「导入交割单」抽屉内
    await expect(
      head.getByRole("button", { name: "AI 识别" })
    ).toHaveCount(0);

    const before = calls.filter(c =>
      c.path.startsWith("/api/reconciliation/discrepancies")
    ).length;

    await head.getByRole("button", { name: "重新检查持仓差异" }).click();

    // 请求体带 domain=B（域 B 是「算差异」的入口）
    await expect
      .poll(
        () =>
          calls.filter(c => c.path.startsWith("/api/reconciliation/run"))
            .length,
        { timeout: 15_000 }
      )
      .toBe(1);
    const run = calls.find(c => c.path.startsWith("/api/reconciliation/run"))!;
    expect(run.method).toBe("POST");
    expect(run.body).toEqual({ domain: "B" });

    // 成功提示 + 差异列表被重新拉取（handleRun 里 Promise.all 的一个分支）。
    await expect(
      page.locator(".el-message", { hasText: "对账完成" })
    ).toBeVisible();
    await expect
      .poll(
        () =>
          calls.filter(c =>
            c.path.startsWith("/api/reconciliation/discrepancies")
          ).length,
        { timeout: 15_000 }
      )
      .toBeGreaterThan(before);
  });

  test("首屏 ready=0 自动落到「要你判断」分段，主行动引导给出判断件数", async ({
    page
  }) => {
    // 只有域 D 有 1 组待判断，其余全空 → ready=0、judge=1，必须自动落 judge
    await mockApis(page, { ghostGroups: 1 });
    await openWorkbench(page);

    // 主行动引导：没有 ready，只有 judge
    await expect(page.locator(".recon-action-hero")).toContainText(
      "有 1 件需要你判断"
    );

    // 分段器已落到「要你判断」，而不是卡在默认的「能一键处理」空档
    await expect(page.locator(".segmented-control__item.is-active")).toContainText(
      "要你判断"
    );

    // 列表可见该条待判断项（域 D 的跨账本重复组）
    await expect(page.locator(".recon-queue__item").first()).toContainText(
      "600519"
    );
  });
});
