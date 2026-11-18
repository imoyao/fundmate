import { expect, test, type Page, type Route } from "@playwright/test";

import { injectSupabaseSession } from "./support/session";

/**
 * 域 F「数据缺失」532 条 blocked 流水的补全 / 删除写路径回归网（#2866 后续）。
 *
 * #2926 的设计边界是「系统不猜归属」，所以那批数据当时只能看、不能动。本组用例
 * 钉的是新增的两条**显式、可撤销**写路径：补全标的代码 / 交易日期、以及带二次
 * 确认与完整行快照的显式删除。
 *
 * 三条刻意的判据，都是本仓踩过的坑：
 *  ① **桩路径逐字带 /api**：Vite 只代理 /api，漏前缀会拿到 SPA index.html
 *     （HTTP 200），前端把 HTML 当数据 → 整页空态且**不报错**（#2866 实测）。
 *  ② **不只数按钮 / 锚点**：Vue 对子组件渲染错误会冻结末次成功渲染，无白屏、
 *     无 pageerror、只有 warn。所以既监听 pageerror + [Vue warn]，又断言内容
 *     （预览数字、日志编号、请求体），避免「恒真」的空断言。
 *  ③ **反向对照**：fixable 组不该出现补全 / 删除；空列表不该出现任何入口。
 *     只写正向用例时，把按钮改成「恒渲染」也能全绿。
 *
 * 注册顺序 = 匹配优先级（**后注册先匹配**）：兜底最宽、最先注册；六个新端点
 * 最具体、最后注册。域 F 列表桩用 pathname 精确相等，否则会吃掉所有子路径。
 */

type Call = { method: string; path: string; search: string; body: unknown };

const GROUP_BLOCKED = {
  key: "pid-77",
  ledger_id: 1,
  symbol: "",
  txn_count: 2,
  dangling_position_ids: [77],
  net_units: 3,
  live_position: null,
  candidates: [],
  batch_id: 9,
  batch_label: "2026-09 导入",
  flags: ["缺标的代码"],
  fixable: false,
  block_reason: "缺标的代码，且对应持仓记录已删除；可补全信息或删除这些交易。",
  transactions: [
    {
      id: 9001,
      txn_type: "buy",
      trade_date: null,
      confirm_date: null,
      symbol: "",
      quantity: 2,
      amount: 340,
      position_id: 77
    },
    {
      id: 9002,
      txn_type: "sell",
      trade_date: null,
      confirm_date: null,
      symbol: "",
      quantity: 1,
      amount: 170,
      position_id: 77
    }
  ]
};

const GROUP_FIXABLE = {
  ...GROUP_BLOCKED,
  key: "pid-78",
  symbol: "600519",
  fixable: true,
  block_reason: null,
  live_position: {
    id: 31,
    symbol: "600519",
    quantity: 10,
    ownership_status: "在持"
  }
};

function listOf(groups: (typeof GROUP_BLOCKED)[]) {
  return {
    total: groups.reduce((n, g) => n + g.txn_count, 0),
    group_count: groups.length,
    batch_count: groups.length ? 1 : 0,
    null_symbol: groups.length ? 2 : 0,
    null_trade_date: groups.length ? 2 : 0,
    fixable_count: groups.filter(g => g.fixable).length ? 2 : 0,
    groups,
    batches: groups.length
      ? [
          {
            id: 9,
            label: "2026-09 导入",
            txn_count: 2,
            ledger_ids: [1],
            symbol_count: 1
          }
        ]
      : []
  };
}

/**
 * ⚠️ 后端 trade_date 返回 iso 串（带 T00:00:00），与前端 YYYY-MM-DD 输入不同。
 * 弹窗必须把「请求时的输入」回填进预览对象，guard 的 fieldSignature 才不会
 * 把格式差误判成「输入已变化」。桩故意保留这个差异，删掉回填逻辑本用例即红。
 */
const ENRICH_PREVIEW = {
  txn_count: 2,
  fill_symbol_count: 2,
  fill_date_count: 0,
  unchanged_count: 0,
  symbol: "600519",
  trade_date: "2026-10-20T00:00:00",
  candidate_positions: [
    {
      id: 31,
      symbol: "600519",
      ledger_id: 1,
      quantity: 10,
      ownership_status: "在持"
    }
  ],
  changes: [
    {
      id: 9001,
      symbol_before: "",
      symbol_after: "600519",
      trade_date_before: null,
      trade_date_after: null,
      asset_type: "stock"
    },
    {
      id: 9002,
      symbol_before: "",
      symbol_after: "600519",
      trade_date_before: null,
      trade_date_after: null,
      asset_type: "stock"
    }
  ],
  warnings: ["补全后仍需人工确认能否挂回现存持仓"]
};

const DELETE_PREVIEW = {
  txn_count: 2,
  transactions: [
    {
      id: 9001,
      txn_type: "buy",
      trade_date: null,
      symbol: "",
      quantity: 2,
      amount: 340,
      position_id: 77,
      realized_pnl: 0,
      is_income: false
    },
    {
      id: 9002,
      txn_type: "sell",
      trade_date: null,
      symbol: "",
      quantity: 1,
      amount: 170,
      position_id: 77,
      realized_pnl: 0,
      is_income: false
    }
  ],
  snapshot_columns: 28,
  total_amount: 510,
  warnings: [
    "删除会影响已实现盈亏与收益统计",
    "现存持仓份额不会改变",
    "删除前会保存每一行的完整快照到审计日志，可凭日志编号撤销"
  ]
};

const ORPHAN_EMPTY = {
  total: 0,
  fixable_count: 0,
  blocked_count: 0,
  batch_count: 0,
  groups: [],
  batches: []
};

const LIST_PATH = "/api/reconciliation/dangling-refs/";

async function mockApis(
  page: Page,
  opts: { groups?: (typeof GROUP_BLOCKED)[] } = {}
): Promise<Call[]> {
  const calls: Call[] = [];
  const list = listOf(opts.groups ?? [GROUP_BLOCKED]);

  /** 记账：所有桩（含最具体的桩）的第一句，漏了就会「明明发了请求却没记录」。 */
  function record(route: Route) {
    const url = new URL(route.request().url());
    let body: unknown = null;
    try {
      body = route.request().postDataJSON();
    } catch {
      body = route.request().postData();
    }
    calls.push({
      method: route.request().method(),
      path: url.pathname,
      search: url.search,
      body
    });
  }
  const reply = (route: Route, data: unknown) => {
    record(route);
    return route.fulfill({ json: { data, message: "ok" } });
  };

  // 兜底：最宽，最先注册（后注册的具体桩会覆盖它）
  await page.route(
    url => url.pathname.startsWith("/api/"),
    route => reply(route, [])
  );

  // 其它域全部给空，保证页面首屏五个加载器都收口、不把 HTML 当数据
  await page.route(
    url => url.pathname.startsWith("/api/reconciliation/discrepancies"),
    route => reply(route, [])
  );
  await page.route(
    url => url.pathname.startsWith("/api/reconciliation/dividend-tax"),
    route => reply(route, [])
  );
  await page.route(
    url => url.pathname.startsWith("/api/e-account/reconciliation"),
    route =>
      reply(route, {
        data_date: "2026-10-20",
        items: [],
        summary: {
          pending_count: 0,
          attributed_count: 0,
          ignored_count: 0,
          verified_count: 0
        }
      })
  );
  // 宽桩先注册，具体的 /ignored/ 后注册（后注册先匹配）。写反会让
  // ignoredItems 拿到 {groups, ignored_count} 而不是数组，触发 prop 类型 warn。
  await page.route(
    url => url.pathname.startsWith("/api/reconciliation/ghost-duplicates"),
    route => reply(route, { groups: [], ignored_count: 0 })
  );
  await page.route(
    url =>
      url.pathname.startsWith("/api/reconciliation/ghost-duplicates/ignored"),
    route => reply(route, [])
  );
  await page.route(
    url => url.pathname === "/api/reconciliation/orphan-ledger/",
    route => reply(route, ORPHAN_EMPTY)
  );

  // 域 F 列表：pathname 必须精确相等，否则会吃掉下面六个子端点
  await page.route(
    url => url.pathname === LIST_PATH,
    route => reply(route, list)
  );

  // 六个新端点：最具体，最后注册 → 最先匹配
  await page.route(
    url => url.pathname === `${LIST_PATH}enrich-preview/`,
    route => reply(route, ENRICH_PREVIEW)
  );
  await page.route(
    url => url.pathname === `${LIST_PATH}enrich/`,
    route =>
      reply(route, {
        log_id: 881,
        updated: 2,
        skipped: 0,
        symbol: "600519",
        trade_date: null
      })
  );
  await page.route(
    url => url.pathname === `${LIST_PATH}enrich-undo/`,
    route => reply(route, { restored: 2, skipped: 0, log_id: 881 })
  );
  await page.route(
    url => url.pathname === `${LIST_PATH}delete-preview/`,
    route => reply(route, DELETE_PREVIEW)
  );
  await page.route(
    url => url.pathname === `${LIST_PATH}delete/`,
    route =>
      reply(route, {
        log_id: 882,
        deleted: 2,
        total_amount: 510,
        confirm_phrase: "删除"
      })
  );
  await page.route(
    url => url.pathname === `${LIST_PATH}delete-undo/`,
    route => reply(route, { restored: 2, skipped: 0, log_id: 882 })
  );

  return calls;
}

/** Vue 渲染错误不会白屏、也不会 pageerror，只剩 warn；两类都收进来。 */
function attachRenderProbes(page: Page): string[] {
  const problems: string[] = [];
  page.on("pageerror", err => problems.push(`pageerror: ${err.message}`));
  page.on("console", msg => {
    const text = msg.text();
    // vite-plugin-vue-inspector 给每个多根组件注入 data-insp-path，dev 环境全站
    // 都有这条 warn，与业务组件无关；只滤掉这一类，其余 warn 全部保留。
    // prop 类型不符这类真错误仍会被探针抓住（本组初跑即靠它抓到桩顺序写反）。
    if (
      msg.type() === "warning" &&
      text.includes("[Vue warn]") &&
      !text.includes("data-insp-path")
    ) {
      problems.push(text);
    }
  });
  return problems;
}

async function openDomainF(page: Page) {
  // 新 IA 不再有 7 个域 tab：站外入口与测试都用 `?domain=F` 直达「修正数据」任务，
  // 页面自动展开该来源的处理区。域只作寻址，不作导航维度。
  await page.goto("/#/investment/reconcile-workbench?domain=F", {
    waitUntil: "commit"
  });
  await expect(page.locator(".workbench-head__title")).toBeVisible({
    timeout: 150_000
  });
  await expect(page.locator(".df-summary")).toBeVisible();
  // 先等首屏取数收口，再做「不存在」类断言，避免 toHaveCount(0) 抢跑假绿
  await expect(page.locator(".df-state")).toHaveCount(0);
}

function dialog(page: Page) {
  return page.locator(".el-dialog:visible");
}

function callOf(calls: Call[], path: string): Call {
  return calls.filter(c => c.path === path).at(-1)!;
}

test.describe("域 F 数据缺失：补全信息 / 显式删除（#2866 后续）", () => {
  test.setTimeout(240_000);

  let problems: string[] = [];

  test.beforeEach(async ({ context, baseURL, page }) => {
    await injectSupabaseSession(context, baseURL!);
    problems = attachRenderProbes(page);
  });

  test("blocked 分组暴露两枚可用入口，并说清差什么（不是灰按钮）", async ({
    page
  }) => {
    await mockApis(page);
    await openDomainF(page);

    const card = page.locator(".df-groups .df-group");
    await expect(card).toHaveCount(1);
    // 内容断言：分组、原因、明细都要真渲染出来，不只是「按钮存在」
    await expect(card.locator(".df-group__block")).toContainText(
      "对应持仓记录已删除"
    );
    await expect(card.locator(".df-group__meta")).toContainText(
      "对应持仓记录已删除"
    );
    const enrich = card.getByRole("button", { name: "补全信息" });
    const remove = card.getByRole("button", { name: "删除" });
    await expect(enrich).toBeEnabled();
    await expect(remove).toBeEnabled();
    await expect(card.getByRole("button", { name: "去处理" })).toHaveCount(0);
    expect(problems).toEqual([]);
  });

  test("补全：填字段 → 看影响 → 勾选 → 写入 → 凭日志编号撤销，并刷新列表", async ({
    page
  }) => {
    const calls = await mockApis(page);
    await openDomainF(page);
    await page
      .locator(".df-groups .df-group")
      .getByRole("button", { name: "补全信息" })
      .click();

    const dlg = dialog(page);
    await expect(dlg.locator(".el-dialog__title")).toContainText("补全信息");
    const submit = dlg.getByRole("button", { name: "确认补全" });
    await expect(submit).toBeDisabled();
    await expect(dlg.locator(".dr-block")).toContainText(
      "请至少填写标的代码或交易日期"
    );

    const symbolInput = dlg.locator('input[placeholder="例如 600519"]');
    await symbolInput.fill("600519");
    await expect(submit).toBeDisabled();
    await expect(dlg.locator(".dr-block")).toContainText("请先查看影响");

    await dlg.getByRole("button", { name: "查看影响" }).click();
    await expect(dlg.locator(".dr-panel .dr-stats")).toContainText("涉及 2 条");
    await expect(dlg.locator(".dr-panel")).toContainText("600519");

    const preview = callOf(calls, `${LIST_PATH}enrich-preview/`);
    expect(preview.method).toBe("GET");
    expect(new URLSearchParams(preview.search).get("transaction_ids")).toBe(
      "9001,9002"
    );
    expect(new URLSearchParams(preview.search).get("symbol")).toBe("600519");

    await expect(submit).toBeDisabled();
    await expect(dlg.locator(".dr-block")).toContainText("请先勾选二次确认");
    await dlg.locator(".dr-confirm").click();
    await expect(submit).toBeEnabled();

    const listBefore = calls.filter(c => c.path === LIST_PATH).length;
    await submit.click();
    await expect(dlg.locator(".dr-done")).toContainText("已补全信息");
    await expect(dlg.locator(".dr-done")).toContainText("日志编号 #881");
    await expect(dlg.locator(".dr-done")).toContainText(
      "可凭日志编号撤销本次处理"
    );

    const write = callOf(calls, `${LIST_PATH}enrich/`);
    expect(write.method).toBe("POST");
    expect(write.body).toEqual({
      transaction_ids: [9001, 9002],
      symbol: "600519",
      confirm: true
    });
    // @refresh="loadDanglingRefs"：写完必须重拉列表，否则页面还停在旧数字
    await expect
      .poll(() => calls.filter(c => c.path === LIST_PATH).length, {
        timeout: 15_000
      })
      .toBeGreaterThan(listBefore);

    await dlg.getByRole("button", { name: "撤销本次处理" }).click();
    await expect(dlg.locator(".dr-done__undone")).toHaveText("本次处理已撤销");
    const undo = callOf(calls, `${LIST_PATH}enrich-undo/`);
    expect(undo.method).toBe("POST");
    expect(undo.body).toEqual({ log_id: 881 });
    expect(problems).toEqual([]);
  });

  test("预览后改输入：旧预览作废，提交闸门重新关上", async ({ page }) => {
    await mockApis(page);
    await openDomainF(page);
    await page
      .locator(".df-groups .df-group")
      .getByRole("button", { name: "补全信息" })
      .click();

    const dlg = dialog(page);
    const submit = dlg.getByRole("button", { name: "确认补全" });
    const symbolInput = dlg.locator('input[placeholder="例如 600519"]');
    await symbolInput.fill("600519");
    await dlg.getByRole("button", { name: "查看影响" }).click();
    await expect(dlg.locator(".dr-panel .dr-stats")).toBeVisible();
    await dlg.locator(".dr-confirm").click();
    await expect(submit).toBeEnabled();

    // 输入一变，watch 清空预览与勾选；guard 的签名比对是第二层保险
    await symbolInput.fill("000001");
    await expect(submit).toBeDisabled();
    await expect(dlg.locator(".dr-panel")).toHaveCount(0);
    await expect(dlg.locator(".dr-block")).toContainText("请先查看影响");
    await expect(dlg.locator(".dr-confirm")).not.toHaveClass(/is-checked/);
    expect(problems).toEqual([]);
  });

  test("删除：自动预览 → 硬确认词 → 写入 → 撤销，请求体带 confirm_phrase", async ({
    page
  }) => {
    const calls = await mockApis(page);
    await openDomainF(page);
    await page
      .locator(".df-groups .df-group")
      .getByRole("button", { name: "删除" })
      .click();

    const dlg = dialog(page);
    await expect(dlg.locator(".el-dialog__title")).toContainText("删除交易");
    await expect(dlg.locator(".dr-static-warn")).toContainText(
      "会影响已实现盈亏与收益统计"
    );

    // 打开即自动取预览（不是等着用户点「查看影响」）
    await expect(dlg.locator(".dr-panel .dr-stats")).toContainText(
      "将删除 2 条 · 金额合计 510 元 · 完整快照 28 列"
    );
    const preview = callOf(calls, `${LIST_PATH}delete-preview/`);
    expect(preview.method).toBe("GET");
    expect(new URLSearchParams(preview.search).get("transaction_ids")).toBe(
      "9001,9002"
    );

    const submit = dlg.getByRole("button", { name: "确认删除" });
    await expect(submit).toBeDisabled();
    await expect(dlg.locator(".dr-block")).toContainText(
      "请输入「删除」二字确认"
    );

    const phrase = dlg.locator('input[placeholder="请输入「删除」二字确认"]');
    await phrase.fill("删");
    await expect(submit).toBeDisabled();
    await phrase.fill("删除");
    await expect(submit).toBeEnabled();

    const listBefore = calls.filter(c => c.path === LIST_PATH).length;
    await submit.click();
    await expect(dlg.locator(".dr-done")).toContainText("已删除");
    await expect(dlg.locator(".dr-done")).toContainText("日志编号 #882");

    const write = callOf(calls, `${LIST_PATH}delete/`);
    expect(write.method).toBe("POST");
    expect(write.body).toEqual({
      transaction_ids: [9001, 9002],
      confirm: true,
      confirm_phrase: "删除"
    });
    await expect
      .poll(() => calls.filter(c => c.path === LIST_PATH).length, {
        timeout: 15_000
      })
      .toBeGreaterThan(listBefore);

    await dlg.getByRole("button", { name: "撤销本次处理" }).click();
    await expect(dlg.locator(".dr-done__undone")).toHaveText("本次处理已撤销");
    expect(callOf(calls, `${LIST_PATH}delete-undo/`).body).toEqual({
      log_id: 882
    });
    expect(problems).toEqual([]);
  });

  test("反向对照：可补关联的组只给「去处理」，不给补全 / 删除", async ({
    page
  }) => {
    await mockApis(page, { groups: [GROUP_FIXABLE] });
    await openDomainF(page);

    const card = page.locator(".df-groups .df-group");
    await expect(card).toHaveCount(1);
    await expect(card.getByRole("button", { name: "去处理" })).toBeEnabled();
    // 先断言组已渲染，再做 count(0)，避免抢在取数完成前假绿
    await expect(card.getByRole("button", { name: "补全信息" })).toHaveCount(0);
    await expect(card.getByRole("button", { name: "删除" })).toHaveCount(0);
    expect(problems).toEqual([]);
  });

  test("反向对照：空列表时不出现任何写入口", async ({ page }) => {
    await mockApis(page, { groups: [] });
    await openDomainF(page);
    // 页面上其它域与通知抽屉也用 el-empty，直接 .el-empty 会 strict mode 冲突
    await expect(page.locator(".domain-f-body .el-empty")).toContainText(
      "暂无数据缺失"
    );
    await expect(page.getByRole("button", { name: "补全信息" })).toHaveCount(0);
    await expect(page.getByRole("button", { name: "确认删除" })).toHaveCount(0);
    expect(problems).toEqual([]);
  });
});
