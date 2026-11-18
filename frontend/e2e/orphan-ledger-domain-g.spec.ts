import { expect, test, type Page, type Route } from "@playwright/test";

import { injectSupabaseSession } from "./support/session";

/**
 * 域 G「缺账本孤儿流水」（#2875）回归网：暴露 → 逐条核对 → 回填 → 撤销。
 *
 * ⚠️ 为什么必须单独建桩：既有 `reconcile-workbench-head.spec.ts` 的兜底桩把
 * `/reconciliation/` 全部返回 `data: []`，域 G 取数落到兜底后 `total` 恒为 0，
 * 页面全程跑**降级空态**。那 8 个用例全绿只能证明「没把既有页弄坏」，
 * 证明不了域 G 真的接上了。这里每个用例都断言桩里的特有内容（账本名、
 * 流水 id、逐条归属），桩一旦没命中就必红。
 *
 * ⚠️ Vue 对子组件 render 抛错是「包容」的：DOM 冻结在末次成功渲染，无白屏、
 * 无 pageerror，只有一条 `[Vue warn]`。所以不能只数锚点或断言组件存在——
 * 必须断言**渲染出来的内容**，同时监听 pageerror 与含组件名的 Vue warn。
 *
 * ⚠️ 后端接口统一走 `/api/` 前缀（vite 只代理 `/api`）。域 G 初版沿用
 * `api/reconciliation.ts` 漏写前缀的旧路径，真页面会拿到 SPA 回退的 HTML（#2866）。
 * 注册顺序 = 后注册先匹配：兜底最宽、最先注册；三个 orphan 端点精确匹配、最后注册。
 */

type Call = { method: string; path: string; body: unknown };

const LIST_PATH = "/api/reconciliation/orphan-ledger/";
const BACKFILL_PATH = "/api/reconciliation/orphan-ledger/backfill/";
const UNDO_PATH = "/api/reconciliation/orphan-ledger/undo/";

const BATCH_LABEL = "2026-10-28 16:59";
const LEDGER_NAME = "同花顺（银河证券）";
const BLOCK_REASON = "账户名为空，无法按同名唯一匹配账本";

function txn(
  id: number,
  amount: number,
  accountName: string | null,
  ledgerId: number | null,
  reason: string | null
): Record<string, unknown> {
  return {
    id,
    txn_type: "buy",
    trade_date: null,
    confirm_date: null,
    symbol: null,
    asset_type: null,
    account_name: accountName,
    amount,
    created_at: "2026-10-28T16:59:00",
    resolved_ledger_id: ledgerId,
    block_reason: reason
  };
}

/** 3 条孤儿流水：2 条可唯一归属账本 #12，1 条账户名为空必须 blocked */
const ORPHAN_LIST = {
  total: 3,
  fixable_count: 2,
  blocked_count: 1,
  batch_count: 1,
  batches: [{ id: 1, label: BATCH_LABEL, txn_count: 3 }],
  groups: [
    {
      key: "ledger:12",
      resolved_ledger: { id: 12, name: LEDGER_NAME },
      txn_count: 2,
      block_reason: null,
      batch_id: 1,
      batch_label: BATCH_LABEL,
      transactions: [
        txn(9001, 1200.5, LEDGER_NAME, 12, null),
        txn(9002, 800.25, LEDGER_NAME, 12, null)
      ]
    },
    {
      key: "blocked",
      resolved_ledger: null,
      txn_count: 1,
      block_reason: BLOCK_REASON,
      batch_id: 1,
      batch_label: BATCH_LABEL,
      transactions: [txn(9003, 30, null, null, BLOCK_REASON)]
    }
  ]
};

const EMPTY_LIST = {
  total: 0,
  fixable_count: 0,
  blocked_count: 0,
  batch_count: 0,
  groups: [],
  batches: []
};

const BACKFILL_RESULT = {
  log_id: 77,
  updated: 2,
  ledgers: [{ id: 12, name: LEDGER_NAME, count: 2 }]
};

type MockOpts = { empty?: boolean };

async function mockApis(page: Page, opts: MockOpts = {}): Promise<Call[]> {
  const calls: Call[] = [];

  function record(route: Route): void {
    const url = new URL(route.request().url());
    let body: unknown = null;
    try {
      body = route.request().postDataJSON();
    } catch {
      body = route.request().postData();
    }
    calls.push({ method: route.request().method(), path: url.pathname, body });
  }

  // 兜底最宽、最先注册（后注册的具体桩会覆盖它）
  await page.route(
    url => url.pathname.startsWith("/api/"),
    route => {
      record(route);
      return route.fulfill({ json: { data: [], message: "" } });
    }
  );

  // E账户对账取数读 data.summary，兜底的 [] 会让它解构失败
  await page.route(
    url => url.pathname.startsWith("/api/e-account/reconciliation"),
    route => {
      record(route);
      return route.fulfill({
        json: {
          data: {
            data_date: "2026-10-28",
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

  // 三个 orphan 端点：精确等值，避免 list 桩把 backfill/undo 吃掉
  await page.route(
    url => url.pathname === LIST_PATH,
    route => {
      record(route);
      return route.fulfill({
        json: { data: opts.empty ? EMPTY_LIST : ORPHAN_LIST, message: "ok" }
      });
    }
  );
  await page.route(
    url => url.pathname === BACKFILL_PATH,
    route => {
      record(route);
      return route.fulfill({ json: { data: BACKFILL_RESULT, message: "ok" } });
    }
  );
  await page.route(
    url => url.pathname === UNDO_PATH,
    route => {
      record(route);
      return route.fulfill({
        json: { data: { restored: 2, log_id: 77 }, message: "ok" }
      });
    }
  );

  return calls;
}

/** 收集会让「看起来渲染了」变成假绿的运行时信号 */
function watchRuntimeErrors(page: Page): {
  pageErrors: string[];
  vueWarnings: string[];
} {
  const pageErrors: string[] = [];
  const vueWarnings: string[] = [];
  page.on("pageerror", err => pageErrors.push(err.message));
  page.on("console", msg => {
    const text = msg.text();
    if (
      msg.type() === "warning" &&
      text.includes("[Vue warn]") &&
      /OrphanLedger|DomainGOrphanLedger/.test(text)
    ) {
      vueWarnings.push(text);
    }
  });
  return { pageErrors, vueWarnings };
}

function expectNoRuntimeErrors(signal: {
  pageErrors: string[];
  vueWarnings: string[];
}): void {
  expect(signal.pageErrors).toEqual([]);
  expect(signal.vueWarnings).toEqual([]);
}

async function openDomainG(page: Page): Promise<void> {
  await page.goto("/#/investment/reconcile-workbench?domain=G", {
    waitUntil: "commit"
  });
  await expect(page.locator(".domain-g-body")).toBeVisible({
    timeout: 150_000
  });
  // 新 IA：域 G 归入「修正数据」任务卡，来源名只作队列卡上的小标签
  await expect(
    page.locator(".workbench-tabs .recon-task-card.is-active")
  ).toContainText("修正数据");
}

test.describe("域 G 缺账本孤儿流水（#2875：暴露 + 回填 + 撤销）", () => {
  test.setTimeout(240_000);

  test.beforeEach(async ({ context, baseURL }) => {
    await injectSupabaseSession(context, baseURL!);
  });

  test("真桩生效：汇总数、分组归属、blocked 阻断都按后端结果渲染", async ({
    page
  }) => {
    const signal = watchRuntimeErrors(page);
    const calls = await mockApis(page);
    await openDomainG(page);

    // 「桩真的命中了」的硬判据：GET 被记账，且桩里的特有文本落到 DOM
    await expect
      .poll(() => calls.filter(c => c.path === LIST_PATH).length, {
        timeout: 15_000
      })
      .toBeGreaterThan(0);
    await expect(page.locator(".domain-g-body")).toContainText(LEDGER_NAME);

    const nums = page.locator(".olg-summary__num");
    await expect(nums.nth(0)).toHaveText("3");
    await expect(nums.nth(1)).toHaveText("2");
    await expect(nums.nth(2)).toHaveText("1");
    await expect(nums.nth(3)).toHaveText("1");

    await expect(page.locator(".olg-group")).toHaveCount(2);
    const fixable = page.locator(".olg-group").nth(0);
    await expect(fixable.locator(".olg-group__key")).toHaveText(LEDGER_NAME);
    await expect(fixable.locator(".olg-group__sub")).toContainText("2 条流水");
    // 用户语言：用账本名，不再把 `#12` 和「按账户名精确同名唯一判定」印在页面上
    await expect(fixable.locator(".olg-group__meta")).toContainText(
      `拟归入：${LEDGER_NAME}`
    );
    await expect(
      fixable.getByRole("button", { name: /核对.*归入账本/ })
    ).toBeEnabled();

    // blocked 组必须说清原因，且按钮禁用（后端不猜归属，前端也不能放行）
    const blocked = page.locator(".olg-group").nth(1);
    await expect(blocked.locator(".olg-group__key")).toHaveText("无法归属");
    await expect(blocked.locator(".olg-group__block")).toContainText(
      "账户名为空"
    );
    await expect(
      blocked.getByRole("button", { name: /核对.*归入账本/ })
    ).toBeDisabled();
    await expect(page.locator(".olg-hint")).toContainText("系统不会猜测归属");

    // 展开组卡的逐条明细：交易类型 / 金额 / 归属都必须是人话；
    // 内部编号收进「记录编号」技术详情，不再当主视觉标识（#9001 / → #12 已下线）。
    await fixable.getByRole("button", { name: "查看 2 条流水明细" }).click();
    await expect(fixable.locator(".olg-txn")).toHaveCount(2);
    await expect(fixable.locator(".olg-txns")).toContainText("买入");
    await expect(fixable.locator(".olg-txns")).toContainText(
      `可归入 ${LEDGER_NAME}`
    );
    await expect(fixable.locator(".olg-tech")).toContainText("记录编号 9001");
    await expect(fixable.locator(".olg-tech")).toContainText("记录编号 9002");

    expectNoRuntimeErrors(signal);
  });

  test("完整写路径：预览准入 → 回填 → 结果 log_id → 撤销 → 列表重拉", async ({
    page
  }) => {
    const signal = watchRuntimeErrors(page);
    const calls = await mockApis(page);
    await openDomainG(page);
    await expect(page.locator(".domain-g-body")).toContainText(LEDGER_NAME);

    await page
      .locator(".olg-group")
      .nth(0)
      .getByRole("button", { name: /核对.*归入账本/ })
      .click();
    const dialog = page.locator(".el-dialog");
    await expect(dialog.locator(".el-dialog__title")).toContainText(
      `回填账本 · ${LEDGER_NAME}`
    );
    await expect(dialog.locator(".olf-target")).toContainText("目标账本：#12");

    const submit = dialog.getByRole("button", { name: "确认回填" });
    // 没展开逐条明细 → 不许提交（准入守卫）
    await expect(submit).toBeDisabled();
    await expect(dialog.locator(".olf-preview__empty")).toContainText(
      "尚未展开"
    );

    await dialog.getByRole("button", { name: "展开逐条明细" }).click();
    await expect(dialog.locator(".olf-rows .olf-row")).toHaveCount(2);
    await expect(dialog.locator(".olf-rows")).toContainText("#9001");
    await expect(dialog.locator(".olf-rows")).toContainText("→ 账本 #12");
    // 展开了但没二次确认 → 仍不许提交
    await expect(submit).toBeDisabled();

    await dialog.locator(".olf-confirm").click();
    await expect(submit).toBeEnabled();
    await dialog.locator(".olf-reason input").fill("按交割单核对账户名后回填");
    const listCallsBefore = calls.filter(c => c.path === LIST_PATH).length;
    await submit.click();

    // 请求体：显式给出用户选中的流水 id，不带任何「自动重挂/重算」参数
    await expect
      .poll(() => calls.filter(c => c.path === BACKFILL_PATH).length, {
        timeout: 15_000
      })
      .toBe(1);
    const backfill = calls.find(c => c.path === BACKFILL_PATH)!;
    expect(backfill.method).toBe("POST");
    expect(backfill.body).toEqual({
      transaction_ids: [9001, 9002],
      reason: "按交割单核对账户名后回填"
    });

    const done = dialog.locator(".olf-done");
    await expect(done).toContainText("已补全");
    await expect(done).toContainText("#77");
    await expect(done).toContainText("份额与金额未改动");

    await done.getByRole("button", { name: "撤销本次回填" }).click();
    await expect
      .poll(() => calls.filter(c => c.path === UNDO_PATH).length, {
        timeout: 15_000
      })
      .toBe(1);
    const undo = calls.find(c => c.path === UNDO_PATH)!;
    expect(undo.method).toBe("POST");
    expect(undo.body).toEqual({ log_id: 77 });
    await expect(done.locator(".olf-done__undone")).toHaveText(
      "本次回填已撤销"
    );

    // 两次 submitted 都应触发列表重拉；否则撤销完界面还留着旧数据
    await expect
      .poll(() => calls.filter(c => c.path === LIST_PATH).length, {
        timeout: 15_000
      })
      .toBeGreaterThan(listCallsBefore);

    expectNoRuntimeErrors(signal);
  });

  test("站外横幅按 total 报数，点击直达 ?domain=G", async ({ page }) => {
    await mockApis(page);
    await page.goto("/#/panorama", { waitUntil: "commit" });

    // #2866 改版：三类问题合并成一条全局紧凑提醒，这里只有域 G 有数据
    const notice = page.locator(".recon-banner");
    await expect(notice).toBeVisible({ timeout: 150_000 });
    await expect(notice.locator(".recon-notice__num")).toHaveText("3");
    await expect(notice.locator(".recon-notice__meta")).toContainText(
      "缺账本流水"
    );

    await notice.getByRole("button", { name: /去查看/ }).click();
    await expect(page).toHaveURL(/reconcile-workbench/);
    await expect(page).toHaveURL(/domain=G/);
    // 先证明工作台真渲染了，否则「横幅消失」可能只是白屏假绿
    await expect(page.locator(".workbench-head__title")).toHaveText(
      "对账中心",
      {
        timeout: 150_000
      }
    );
    await expect(
      page.locator(".workbench-tabs .recon-task-card.is-active")
    ).toContainText("修正数据");
    await expect(page.locator(".domain-g-body")).toContainText(LEDGER_NAME);
    await expect(page.locator(".recon-banner")).toHaveCount(0);
  });

  test("反向对照：桩返回 0 条时域 G 必须空态，桩特有文本一个都不出现", async ({
    page
  }) => {
    await mockApis(page, { empty: true });
    await openDomainG(page);

    const nums = page.locator(".olg-summary__num");
    await expect(nums.nth(0)).toHaveText("0");
    await expect(nums.nth(1)).toHaveText("0");
    await expect(page.locator(".olg-group")).toHaveCount(0);
    await expect(page.locator(".olg-hint")).toContainText("当前没有缺账本流水");
    // 若上一个用例的具体文本断言是恒真，这里就会撞出来
    await expect(page.locator(".domain-g-body")).not.toContainText(LEDGER_NAME);
    await expect(page.locator(".domain-g-body")).not.toContainText("#9001");
  });
});
