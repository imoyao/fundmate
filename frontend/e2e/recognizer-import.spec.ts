import { expect, test, type Locator, type Page } from "@playwright/test";

import { injectSupabaseSession } from "./support/session";

/**
 * AI 识别入库弹窗回归网（#980 拆分 `RecognizerImportModal.vue` 后补的接线判据）。
 *
 * 656 行的弹窗拆成 `recognizerImport/`（额度条 / 输入面板 / 预览表 + 纯函数层 + composable）。
 * 纯函数已有单测（`recognizerImportModel.spec.ts`），这里钉的是**拆组件最容易断的接线**：
 *
 *   `RecognizerInputPanel`（三个 defineModel）→ `useRecognizerImport`（状态与动作）
 *   → `RecognizerPreviewTable`（props）→ 底部「确认进草稿」→ 工作台候选面板
 *
 * model 断了的表现是「粘贴了文本但按钮一直灰着」，props 断了是「识别出结果但预览表空白」——
 * 两者都不报错，单测也抓不到（不渲染 el-dialog）。
 *
 * 另钉一条业务判据：草稿按「识别时的场景」路由（txn→域 C / holding→域 A）。
 * txn 候选缺 ledgerId 时 `saveRecognizerCandidates` 会直接抛错，
 * 所以「保存成功」本身就证明账户 id 一路带到了草稿里。
 *
 * 断言只落在「点完能看到什么」，不测样式值。
 */

type Call = {
  method: string;
  path: string;
  body: Record<string, unknown> | null;
};

function holdingRows() {
  return [
    {
      symbol: "110011",
      name: "易方达中小盘",
      type: "fund",
      quantity: 1000,
      price: 2.5,
      amount: 2500,
      snapshot_date: "2026-10-20",
      account_name: "支付宝",
      ledger_id: 1,
      source: "ocr",
      import_hash: "h1"
    },
    {
      symbol: "161725",
      name: "招商中证白酒",
      type: "fund",
      quantity: 500,
      price: 1.2,
      amount: 600,
      snapshot_date: "2026-10-20",
      account_name: "支付宝",
      ledger_id: 1,
      source: "ocr",
      import_hash: "h2"
    },
    {
      symbol: "000001",
      name: "华夏成长",
      type: "fund",
      quantity: 300,
      price: 3.1,
      amount: 930,
      snapshot_date: "2026-10-20",
      account_name: "支付宝",
      ledger_id: 1,
      source: "ocr",
      import_hash: "h3"
    }
  ];
}

function txnRows() {
  return [
    {
      symbol: "110011",
      name: "易方达中小盘",
      type: "fund",
      display_type: "基金",
      op_type: "buy",
      op_type_label: "买入",
      quantity: 100,
      price: 2.5,
      amount: 250,
      fee: 0,
      trade_date: "2026-10-20",
      import_hash: "t1",
      source: "ocr",
      is_duplicate: false,
      error: null,
      warnings: []
    },
    {
      symbol: "161725",
      name: "招商中证白酒",
      type: "fund",
      display_type: "基金",
      op_type: "sell",
      op_type_label: "卖出",
      quantity: 200,
      price: 1.2,
      amount: 240,
      fee: 1,
      trade_date: "2026-10-20",
      import_hash: "t2",
      source: "ocr",
      is_duplicate: true,
      error: null,
      warnings: []
    }
  ];
}

async function mockApis(
  page: Page,
  usage: { remaining: number; quota: number }
) {
  const calls: Call[] = [];
  await page.route(/^https?:\/\/[^/]+\/api\//, async route => {
    const url = new URL(route.request().url());
    const method = route.request().method();
    const body = (route.request().postDataJSON() ?? null) as Record<
      string,
      unknown
    > | null;
    calls.push({ method, path: url.pathname, body });

    if (url.pathname.startsWith("/api/usage/")) {
      return route.fulfill({ json: { data: usage, message: "" } });
    }
    if (url.pathname === "/api/ocr/parse/") {
      const scenario = (body?.scenario as string) ?? "holding_import";
      return route.fulfill({
        json: {
          data: {
            scenario,
            rows: scenario === "txn_import" ? txnRows() : holdingRows(),
            usage
          },
          message: ""
        }
      });
    }
    if (url.pathname === "/api/ocr/recognize/") {
      return route.fulfill({
        json: { data: { scenario: "txn_import", rows: [], usage }, message: "" }
      });
    }
    if (url.pathname === "/api/ledgers/") {
      return route.fulfill({
        json: {
          data: [
            { id: 11, name: "招商银行" },
            { id: 12, name: "支付宝-基金" }
          ],
          message: ""
        }
      });
    }
    if (url.pathname.startsWith("/api/e-account/reconciliation")) {
      return route.fulfill({
        json: {
          data: { data_date: "2026-10-20", items: [], summary: {} },
          message: ""
        }
      });
    }
    return route.fulfill({ json: { data: [], message: "" } });
  });
  return calls;
}

async function openWorkbench(page: Page) {
  await page.goto("/#/investment/reconcile-workbench", { waitUntil: "commit" });
  await expect(page.getByRole("button", { name: "AI 识别" })).toBeVisible({
    timeout: 150_000
  });
}

/** 打开识别弹窗（工作台页头的入口按钮） */
async function openDialog(page: Page) {
  await page.getByRole("button", { name: "AI 识别" }).click();
  const dialog = page.getByRole("dialog");
  await expect(dialog).toBeVisible();
  return dialog;
}

/** 切到文本通道并粘贴内容 */
async function pasteText(dialog: Locator) {
  await dialog.getByRole("tab", { name: "粘贴文本" }).click();
  const textarea = dialog.locator(".ocr-textarea textarea");
  await expect(textarea).toBeVisible();
  await textarea.fill(
    "110011 易方达中小盘 1000 2.5\n161725 招商中证白酒 500 1.2"
  );
  return textarea;
}

test.describe("AI 识别入库弹窗（#980 拆分后的接线判据）", () => {
  test.beforeEach(async ({ context, baseURL }) => {
    await injectSupabaseSession(context, baseURL!);
  });

  test("额度条：随场景换 feature 查询，紧张/用尽两态各有提示", async ({
    page
  }) => {
    test.setTimeout(240_000);
    const calls = await mockApis(page, { remaining: 1, quota: 5 });
    await openWorkbench(page);
    const dialog = await openDialog(page);

    // 默认交易场景 → 查 txn_import 配额
    await expect(dialog.locator(".usage-banner__count")).toContainText(
      "1 / 5 次"
    );
    await expect(dialog.locator(".usage-banner__hint")).toContainText(
      "额度紧张，谨慎使用"
    );
    expect(
      calls.filter(c => c.path.startsWith("/api/usage/")).map(c => c.path)
    ).toContain("/api/usage/txn_import/");

    // 切到持仓识别 → 换 feature 重新查（场景变了配额是两套）
    await dialog.getByRole("tab", { name: "持仓识别" }).click();
    await expect(dialog.locator(".usage-banner__count")).toBeVisible();
    expect(
      calls.filter(c => c.path.startsWith("/api/usage/")).map(c => c.path)
    ).toContain("/api/usage/holding_import/");
  });

  test("额度用尽：提示改为「已用尽」，且「开始识别」不可点", async ({
    page
  }) => {
    test.setTimeout(240_000);
    await mockApis(page, { remaining: 0, quota: 5 });
    await openWorkbench(page);
    const dialog = await openDialog(page);

    await expect(dialog.locator(".usage-banner__hint")).toContainText(
      "额度已用尽，请明日再试"
    );
    // 即使已经粘贴了文本也不能识别（额度门槛优先于输入检查）
    await dialog.getByRole("tab", { name: "粘贴文本" }).click();
    await dialog.locator(".ocr-textarea textarea").fill("110011 易方达 1000");
    await expect(
      dialog.getByRole("button", { name: "开始识别" })
    ).toBeDisabled();
  });

  test("文本通道：粘贴 → 识别 → 预览 → 确认进草稿，工作台出现持仓候选", async ({
    page
  }) => {
    test.setTimeout(240_000);
    const calls = await mockApis(page, { remaining: 3, quota: 5 });
    await openWorkbench(page);
    const dialog = await openDialog(page);

    // 持仓场景：不需要关联账户（后端自动归到 E账户）
    await dialog.getByRole("tab", { name: "持仓识别" }).click();
    await expect(dialog.locator(".ledger-select")).toHaveCount(0);

    await pasteText(dialog);
    await dialog.getByRole("button", { name: "开始识别" }).click();

    // 预览表：3 条，且是持仓列（份额/成本/快照日），不是交易列
    await expect(dialog.locator(".preview-table .el-table__row")).toHaveCount(
      3
    );
    await expect(dialog.locator(".result-head")).toContainText("识别到 3 条");
    await expect(dialog.locator(".preview-table")).toContainText("快照日");
    await expect(dialog.locator(".preview-table")).not.toContainText("操作");

    // 底部按钮换成「确认进草稿（3）」，原「开始识别」消失
    await expect(dialog.getByRole("button", { name: "开始识别" })).toHaveCount(
      0
    );
    await dialog.getByRole("button", { name: "确认进草稿（3）" }).click();

    await expect(page.getByText("已存入对账草稿")).toBeVisible({
      timeout: 30_000
    });
    await expect(dialog).toBeHidden();

    // 判据：识别请求带的是持仓场景
    const parse = calls.filter(c => c.path === "/api/ocr/parse/").at(-1);
    expect(parse?.body?.scenario).toBe("holding_import");

    // 工作台域 A（默认 tab）出现持仓候选面板
    await expect(
      page.locator(".recognizer-candidate-panel__title")
    ).toContainText("AI 识别候选（持仓）· 3 条");
  });

  test("交易场景：选账户 → 识别 → 进草稿落到域 C（候选为「交易」）", async ({
    page
  }) => {
    test.setTimeout(240_000);
    await mockApis(page, { remaining: 3, quota: 5 });
    await openWorkbench(page);
    const dialog = await openDialog(page);

    // 交易场景必须出现关联账户（域 C 对账按账本隔离）
    await expect(dialog.locator(".ledger-select")).toBeVisible();
    await dialog.locator(".ledger-select .el-select").click();
    await page
      .locator(".el-select-dropdown__item")
      .filter({ hasText: "招商银行" })
      .first()
      .click();

    await pasteText(dialog);
    await dialog.getByRole("button", { name: "开始识别" }).click();

    await expect(dialog.locator(".preview-table .el-table__row")).toHaveCount(
      2
    );
    // 交易列：操作 / 数量 / 金额 / 日期；重复行要打「重复」标
    await expect(dialog.locator(".preview-table")).toContainText("买入");
    await expect(dialog.locator(".preview-table")).toContainText("卖出");
    await expect(dialog.locator(".preview-table")).toContainText("重复");

    // 判据（真 bug 回归）：交易行带 warnings 数组，存进 IndexedDB 走结构化克隆；
    // 若候选行仍挂着 Vue 响应式代理，这里会抛 DataCloneError 且**不弹任何提示**，
    // 表现为「点了确认进草稿毫无反应」。持仓行没有嵌套字段，所以只有交易场景会发作。
    await dialog.getByRole("button", { name: "确认进草稿（2）" }).click();
    await expect(page.getByText("已存入对账草稿")).toBeVisible({
      timeout: 30_000
    });
    await expect(dialog).toBeHidden();

    // 域 C 才挂 txn 候选面板（默认停在域 A）
    await page.getByRole("tab", { name: "对账单导入" }).click();
    await expect(
      page.locator(".recognizer-candidate-panel__title")
    ).toContainText("AI 识别候选（交易）· 2 条");
  });
});
