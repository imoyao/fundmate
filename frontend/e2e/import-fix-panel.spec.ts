import { expect, test, type Page } from "@playwright/test";
import { injectSupabaseSession } from "./support/session";

/**
 * #1792 批量修正面板（抽屉改内联 + 四分区能力 + 撤销栈 + 阈值形态切换）。
 *
 * 覆盖验收：
 * - ① 摘要面板与修正面板同屏可见（内联展开，非覆盖式抽屉）；
 * - ② 四分区逐项可点 + 【撤销】回滚生效（amount / fill / repo 三类作用域各验一次）；
 * - ③ 阈值形态的端到端侧写：≤10 混合 → 逐条卡片；≤10/>10 边界本身由
 *   vitest 单测覆盖（composables/__tests__/batchFixLogic.spec.ts）；
 * - ④ 逆回购行可识别标记，可查看转换结果（识别依据 + 配置目标）。
 *
 * 打桩策略同 #1791：真实走「选账户 → 上传 → 解析」链路，
 * 仅把 /api/importers/parse/ 换成固定数据集。
 */

const LEDGER = {
  id: 1,
  name: "E2E 演示账户",
  ledger_type: "stock",
  default_allocation: "longterm"
};

const baseRow = {
  display_type: "股票",
  op_type: "buy",
  op_type_label: "买入",
  fee: 5,
  trade_date: "2026-09-01",
  account_name: "",
  ledger_id: LEDGER.id,
  contract_id: "",
  is_cash_transfer: false,
  error: null as string | null,
  is_duplicate: false,
  allocation: null,
  link_group_id: null,
  trade_amount: 0,
  net_amount: 0,
  notes: "",
  source: "e2e",
  is_calculated: false
};

/** 完整行（stock） */
const completeRow = (symbol: string, name: string) => ({
  ...baseRow,
  symbol,
  name,
  type: "stock",
  quantity: 100,
  price: 1700,
  amount: 170000
});

/** 代码未匹配行（symbol=UNKNOWN，数量价格齐全 → 只属于 missingCode 分区） */
const missingCodeRow = (name: string) => ({
  ...baseRow,
  symbol: "UNKNOWN",
  name,
  type: "stock",
  quantity: 100,
  price: 10,
  amount: 1000
});

/** 金额不一致行（100×10=1000 ≠ 999） */
const mismatchRow = (name: string) => ({
  ...baseRow,
  symbol: "600000",
  name,
  type: "stock",
  quantity: 100,
  price: 10,
  amount: 999
});

/** 可自动推算的缺失行（缺数量、有单价与金额 → 数量 = 金额 ÷ 单价） */
const derivableRow = (name: string) => ({
  ...baseRow,
  symbol: "600519",
  name,
  type: "stock",
  quantity: 0,
  price: 10,
  amount: 100
});

/** 不可推算的缺失行（数量与价格同时缺失） */
const blockedRow = (name: string) => ({
  ...baseRow,
  symbol: "600519",
  name,
  type: "stock",
  quantity: 0,
  price: 0,
  amount: 100
});

/** 逆回购行（解析期按代码模式识别，配置目标自动置「活钱」） */
const repoRow = (symbol: string, name: string) => ({
  ...baseRow,
  symbol,
  name,
  type: "reverse_repo",
  quantity: 1,
  price: 100,
  amount: 100,
  allocation: "liquid"
});

/**
 * A 组：分类批量修正数据集——问题行 14（未匹配 4 + 不一致 4 + 缺失 5 + 错误 1），
 * >10 且含可批量分区 → batch 形态；另有完整 1 + 逆回购 2 = 总 17 行。
 */
const BATCH_ROWS = [
  completeRow("600519", "贵州茅台"),
  missingCodeRow("未匹配个股A"),
  missingCodeRow("未匹配个股B"),
  missingCodeRow("未匹配个股C"),
  missingCodeRow("未匹配个股D"),
  mismatchRow("金额不一致A"),
  mismatchRow("金额不一致B"),
  mismatchRow("金额不一致C"),
  mismatchRow("金额不一致D"),
  derivableRow("可推算甲"),
  derivableRow("可推算乙"),
  derivableRow("可推算丙"),
  blockedRow("双缺失A"),
  blockedRow("双缺失B"),
  {
    ...baseRow,
    symbol: "000002",
    name: "万科A",
    type: "stock",
    quantity: 500,
    price: 8,
    amount: 4000,
    error: "交易日期无法解析"
  },
  repoRow("204001", "GC001"),
  repoRow("131810", "R-001")
];

/**
 * B 组：逐条修正数据集——问题行 4（未匹配 + 不一致 + 缺失 + 错误），
 * ≤10 且混合 → single 形态（卡片式单条表单）。
 */
const SINGLE_ROWS = [
  completeRow("600519", "贵州茅台"),
  missingCodeRow("未匹配个股X"),
  mismatchRow("金额不一致X"),
  derivableRow("可推算丁"),
  {
    ...baseRow,
    symbol: "000002",
    name: "万科A",
    type: "stock",
    quantity: 500,
    price: 8,
    amount: 4000,
    error: "交易日期无法解析"
  }
];

async function openPreview(page: Page, rows: typeof BATCH_ROWS) {
  await page.route(
    url => /\/api\/ledgers\/?$/.test(url.pathname),
    route =>
      route.fulfill({ json: { data: [LEDGER], message: "ok", error_code: 0 } })
  );
  await page.route(
    url => url.pathname.includes("/api/ledgers/sales-institutions"),
    route => route.fulfill({ json: { data: [], message: "ok", error_code: 0 } })
  );
  await page.route(
    url => url.pathname.includes("/api/importers/parse"),
    route =>
      route.fulfill({
        json: {
          data: rows,
          total: rows.length,
          error_count: rows.filter(r => r.error).length,
          duplicate_count: 0,
          cash_transfer_count: 0,
          message: "ok",
          error_code: 0
        }
      })
  );

  await page.goto("/#/inventory/investment/import");

  await page.locator(".account-select").click();
  await page
    .locator(".el-select-dropdown:visible .el-select-dropdown__item", {
      hasText: LEDGER.name
    })
    .first()
    .click();

  await page.locator(".golden-upload input[type=file]").setInputFiles({
    name: "trades.csv",
    mimeType: "text/csv",
    buffer: Buffer.from("交易日期,证券代码,数量\n2026-09-01,600519,100\n")
  });

  await expect(page.locator(".step3-container")).toBeVisible({
    timeout: 30_000
  });
}

function fixCard(page: Page) {
  return page.locator('.summary-card[data-category="fix"]');
}

function section(page: Page, key: string) {
  return page.locator(`.bf-section[data-section="${key}"]`);
}

test.describe("批量修正内联面板（#1792）", () => {
  test.setTimeout(180_000);

  test.beforeEach(async ({ context, baseURL }) => {
    await injectSupabaseSession(context, baseURL!);
  });

  test("批量模式：四分区同屏可点、三类作用域撤销回滚、逆回购识别与转换结果", async ({
    page
  }) => {
    const pageErrors: string[] = [];
    page.on("pageerror", e => pageErrors.push(e.message));

    await openPreview(page, BATCH_ROWS);

    // ── 验收①：内联展开——摘要、修正面板、表格三方同屏 ──
    await fixCard(page).getByRole("button", { name: "批量修正" }).click();
    const panel = page.locator("[data-fix-panel]");
    await expect(panel).toBeVisible();
    await expect(page.locator(".summary-panel")).toBeVisible();
    await expect(page.locator(".step3-right")).toBeVisible();

    // 形态：>10 混合（含错误）→ 分类批量修正模式
    await expect(panel.locator('[data-fix-mode="batch"]')).toContainText(
      "分类批量修正模式"
    );

    // ── 验收②：四分区齐备（代码未匹配 / 单价数量缺失 / 数据不一致 / 逆回购识别）──
    await expect(section(page, "missingCode")).toBeVisible();
    await expect(section(page, "missingQtyPrice")).toBeVisible();
    await expect(section(page, "mismatch")).toBeVisible();
    await expect(section(page, "reverse_repo")).toBeVisible();
    // §4 第 4 条：错误行不可批量 → 提示条 + 跳过引导
    await expect(panel).toContainText("另有 1 条解析错误不支持批量修正");
    await expect(
      panel.getByRole("button", { name: "跳过这 1 条" })
    ).toBeVisible();

    // ── 验收④：逆回购识别标记 + 查看转换结果（识别依据、配置目标） ──
    const repoSection = section(page, "reverse_repo");
    await expect(repoSection).toContainText("2 条");
    await repoSection.getByRole("button", { name: "查看转换结果" }).click();
    const repoDialog = page.getByRole("dialog", { name: "逆回购转换结果" });
    await expect(repoDialog).toBeVisible();
    await expect(repoDialog).toContainText("204001");
    await expect(repoDialog).toContainText("沪市 204 模式");
    await expect(repoDialog).toContainText("活钱");
    await page.keyboard.press("Escape");
    await expect(repoDialog).toBeHidden();

    // 逆回购作用域撤销：分区【撤销】置活钱→长期增值（按钮随之禁用），
    // 顶部【撤销上一步】回滚（按钮恢复可用）
    const repoUndo = repoSection.getByRole("button", { name: "撤销" });
    await expect(repoUndo).toBeEnabled();
    await repoUndo.click();
    await expect(repoUndo).toBeDisabled();
    await panel.getByRole("button", { name: "撤销上一步" }).click();
    await expect(repoUndo).toBeEnabled();

    // ── amount 作用域：自动修正金额 → 分区消失；撤销上一步 → 分区回滚出现 ──
    await section(page, "mismatch")
      .getByRole("button", { name: "自动修正金额" })
      .click();
    await expect(section(page, "mismatch")).toHaveCount(0);
    await panel.getByRole("button", { name: "撤销上一步" }).click();
    await expect(section(page, "mismatch")).toBeVisible();
    await expect(section(page, "mismatch").locator(".el-tag")).toHaveText(
      "4 条"
    );

    // ── fill 作用域：自动填充 → 可查看已填充数据；分区【撤销】按作用域回滚 ──
    const qtySection = section(page, "missingQtyPrice");
    await expect(qtySection).toContainText("可自动填充 3 条");
    const fillUndo = qtySection.getByRole("button", { name: "撤销" });
    const filledBtn = qtySection.getByRole("button", {
      name: "查看已填充数据"
    });
    await expect(fillUndo).toBeDisabled(); // 栈空 → 作用域不匹配
    await expect(filledBtn).toBeDisabled();
    await qtySection.getByRole("button", { name: "自动填充" }).click();
    await expect(qtySection.locator(".el-tag")).toHaveText("2 条");
    await expect(filledBtn).toBeEnabled();
    await expect(fillUndo).toBeEnabled();
    await filledBtn.click();
    const filledDialog = page.getByRole("dialog", { name: "已填充数据" });
    await expect(filledDialog).toBeVisible();
    await expect(filledDialog).toContainText("可推算甲");
    await page.keyboard.press("Escape");
    await expect(filledDialog).toBeHidden();
    await fillUndo.click();
    await expect(qtySection.locator(".el-tag")).toHaveText("5 条");
    await expect(qtySection).toContainText("可自动填充 3 条");
    await expect(filledBtn).toBeDisabled();

    // ── missingCode 分区：输入代码 + 应用到全部 → 分区消失 ──
    const codeSection = section(page, "missingCode");
    await codeSection.locator(".bf-input input").fill("600000");
    await codeSection.getByRole("button", { name: "应用到全部" }).click();
    await expect(section(page, "missingCode")).toHaveCount(0);

    // ── 面板底部【收起批量修正】→ 面板收起，摘要仍在 ──
    await panel.getByRole("button", { name: "收起批量修正" }).click();
    await expect(panel).toHaveCount(0);
    await expect(page.locator(".summary-panel")).toBeVisible();

    expect(pageErrors).toEqual([]);
  });

  test("逐条模式（≤10 混合）：卡片式单条表单可应用、可跳过、同屏常驻", async ({
    page
  }) => {
    const pageErrors: string[] = [];
    page.on("pageerror", e => pageErrors.push(e.message));

    await openPreview(page, SINGLE_ROWS);

    await fixCard(page).getByRole("button", { name: "批量修正" }).click();
    const panel = page.locator("[data-fix-panel]");
    await expect(panel).toBeVisible();
    await expect(page.locator(".summary-panel")).toBeVisible();

    // 形态：≤10 混合 → 逐条修正（卡片式单条表单），4 张卡片对应 4 类问题行
    await expect(panel.locator('[data-fix-mode="single"]')).toContainText(
      "逐条修正模式"
    );
    const cards = panel.locator("[data-fix-card]");
    await expect(cards).toHaveCount(4);

    // 错误卡片展示解析错误信息
    await expect(
      panel.locator('[data-fix-card][data-section="error"]')
    ).toContainText("交易日期无法解析");

    // mismatch 卡片差额说明（100×10 − 999 = +1.00）
    await expect(
      panel.locator('[data-fix-card][data-section="mismatch"]')
    ).toContainText("差额 +1.00");

    // 代码未匹配卡片：输入代码 → 应用 → 行出问题集，卡片消失
    const codeCard = panel.locator(
      '[data-fix-card][data-section="missingCode"]'
    );
    await codeCard.locator(".bf-input input").fill("600000");
    await codeCard.getByRole("button", { name: "应用" }).click();
    await expect(cards).toHaveCount(3);

    // 跳过此条（mismatch 卡片）：行退出导入集合 → 底部已选择计数 -1
    // 默认已选 3 条（完整 1 + 未匹配 1 + 不一致 1；缺失/错误行默认不选）
    await expect(page.locator(".summary-foot .foot-selected")).toContainText(
      "已选择 3 条"
    );
    await panel
      .locator('[data-fix-card][data-section="mismatch"]')
      .getByRole("button", { name: "跳过此条" })
      .click();
    await expect(page.locator(".summary-foot .foot-selected")).toContainText(
      "已选择 2 条"
    );

    // 收起 → 面板关闭，摘要仍在
    await panel.getByRole("button", { name: "收起批量修正" }).click();
    await expect(panel).toHaveCount(0);
    await expect(page.locator(".summary-panel")).toBeVisible();

    expect(pageErrors).toEqual([]);
  });
});
