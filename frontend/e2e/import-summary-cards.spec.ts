import { expect, test, type Page } from "@playwright/test";
import { injectSupabaseSession } from "./support/session";

/**
 * #1791 导入问题摘要三卡片（问题摘要面板改三卡片形态）。
 *
 * 覆盖验收：
 * - ② 三卡片条数 = 展开后表格行数 = 底部「展开全部数据（总条数）」三者一致；
 * - ③ 展开任一类别过滤时摘要面板不消失（表格是唯一滚动容器）；
 * - ④ 疑似重复默认不计入导入集合（默认未勾选），可手动勾选保留。
 *
 * 打桩策略：真实走「选账户 → 上传文件 → 解析」链路，仅把 `/api/importers/parse/`
 * 换成返回 2 完整 + 1 疑似重复 + 3 需修正（解析错误 / 代码未匹配 / 金额不一致）的
 * 固定数据集，保证三类分布可断言（mock 数据集没有重复行，devJump 不可用于本组用例）。
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

/** 分类：complete ×2 / duplicate ×1 / fix ×3（error、missingCode、mismatch 各 1） */
const PARSE_ROWS = [
  {
    ...baseRow,
    symbol: "600519",
    name: "贵州茅台",
    type: "stock",
    quantity: 100,
    price: 1700,
    amount: 170000
  },
  {
    ...baseRow,
    symbol: "000001",
    name: "平安银行",
    type: "stock",
    quantity: 1000,
    price: 10,
    amount: 10000
  },
  {
    ...baseRow,
    symbol: "600519",
    name: "贵州茅台",
    type: "stock",
    quantity: 100,
    price: 1710,
    amount: 171000,
    is_duplicate: true
  },
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
  {
    ...baseRow,
    symbol: "UNKNOWN",
    name: "未匹配基金",
    type: "fund",
    quantity: 1000,
    price: 1,
    amount: 1000
  },
  {
    ...baseRow,
    symbol: "600000",
    name: "浦发银行",
    type: "stock",
    quantity: 100,
    price: 10,
    amount: 999 // 100×10=1000 ≠ 999 → 金额不一致
  }
];

const TOTAL = PARSE_ROWS.length; // 6

async function openPreview(page: Page) {
  // 账户名录（fetchLedgers 与销售机构名录并行请求，两者都要桩掉）
  await page.route(
    url => /\/api\/ledgers\/?$/.test(url.pathname),
    route =>
      route.fulfill({ json: { data: [LEDGER], message: "ok", error_code: 0 } })
  );
  await page.route(
    url => url.pathname.includes("/api/ledgers/sales-institutions"),
    route => route.fulfill({ json: { data: [], message: "ok", error_code: 0 } })
  );
  // 解析：三类混合行
  await page.route(
    url => url.pathname.includes("/api/importers/parse"),
    route =>
      route.fulfill({
        json: {
          data: PARSE_ROWS,
          total: TOTAL,
          error_count: 1,
          duplicate_count: 1,
          cash_transfer_count: 0,
          message: "ok",
          error_code: 0
        }
      })
  );

  await page.goto("/#/inventory/investment/import");

  // 步骤1：选账户（选中即自动进入步骤2）
  await page.locator(".account-select").click();
  await page
    .locator(".el-select-dropdown:visible .el-select-dropdown__item", {
      hasText: LEDGER.name
    })
    .first()
    .click();

  // 步骤2：上传（解析已打桩，真实走 handleUpload 链路）
  await page.locator(".golden-upload input[type=file]").setInputFiles({
    name: "trades.csv",
    mimeType: "text/csv",
    buffer: Buffer.from("交易日期,证券代码,数量\n2026-09-01,600519,100\n")
  });

  // 步骤3：预览
  await expect(page.locator(".step3-container")).toBeVisible({
    timeout: 30_000
  });
}

function card(page: Page, category: "complete" | "duplicate" | "fix") {
  return page.locator(`.summary-card[data-category="${category}"]`);
}

test.describe("导入问题摘要三卡片（#1791）", () => {
  test.setTimeout(180_000);

  test.beforeEach(async ({ context, baseURL }) => {
    await injectSupabaseSession(context, baseURL!);
  });

  test("三卡片条数与展开后表格、底部总条数三者一致（验收②），面板常驻（验收③）", async ({
    page
  }) => {
    const pageErrors: string[] = [];
    page.on("pageerror", e => pageErrors.push(e.message));

    await openPreview(page);

    // ── 标题与三卡片条数（2 / 1 / 3） ──
    await expect(page.locator(".summary-title")).toContainText(
      "系统已自动分析，发现以下问题"
    );
    const cards = page.locator(".summary-card");
    await expect(cards).toHaveCount(3);
    await expect(card(page, "complete").locator(".card-count")).toHaveText("2");
    await expect(card(page, "duplicate").locator(".card-count")).toHaveText(
      "1"
    );
    await expect(card(page, "fix").locator(".card-count")).toHaveText("3");

    // ── 底部统计：已选择（selectAllValid 排除 dup/error，选中 4 行）+ 总条数 ──
    await expect(page.locator(".summary-foot .foot-selected")).toContainText(
      "已选择 4 条"
    );
    const expandAll = page.getByRole("button", {
      name: `展开全部数据（${TOTAL}）`
    });
    await expandAll.isVisible().then(v => expect(v).toBe(true));

    // 三卡之和 = 底部总条数
    const sum = (
      await Promise.all(
        [0, 1, 2].map(i => cards.nth(i).locator(".card-count").textContent())
      )
    )
      .map(Number)
      .reduce((a, b) => a + b, 0);
    expect(sum).toBe(TOTAL);

    // 展开前：完整表格 6 行
    await expect(page.locator(".table-wrapper .el-table__row")).toHaveCount(
      TOTAL
    );

    // ── 展开「数据完整」→ 表格 2 行，与卡片条数一致；面板常驻 ──
    await card(page, "complete")
      .getByRole("button", { name: "展开查看" })
      .click();
    await expect(page.locator(".table-wrapper .el-table__row")).toHaveCount(2);
    await expect(page.locator(".step3-right")).toContainText("共 2 条");
    await expect(
      card(page, "complete").getByRole("button", { name: "收起" })
    ).toBeVisible();
    await expect(page.locator(".summary-panel")).toBeVisible();

    // 收起 → 回到 6 行
    await card(page, "complete").getByRole("button", { name: "收起" }).click();
    await expect(page.locator(".table-wrapper .el-table__row")).toHaveCount(
      TOTAL
    );

    // ── 展开「需要修正」→ 表格 3 行 + 细分错误统计与卡片计数同源 ──
    await card(page, "fix").getByRole("button", { name: "展开查看" }).click();
    await expect(page.locator(".table-wrapper .el-table__row")).toHaveCount(3);
    const chips = card(page, "fix").locator(".card-chips");
    await expect(chips).toContainText("解析错误 1");
    await expect(chips).toContainText("代码未匹配 1");
    await expect(chips).toContainText("数据不一致 1");
    await expect(page.locator(".summary-panel")).toBeVisible();

    // 【批量修正】入口打开抽屉（#1791 要做的事 3）。
    // 页面上有多个常驻 drawer（FundMatchDrawer / 导入抽屉等），按 aria-label 定位。
    const fixDrawer = page.getByRole("dialog", { name: "智能修正" });
    await card(page, "fix").getByRole("button", { name: "批量修正" }).click();
    await expect(fixDrawer).toBeVisible();
    await page.keyboard.press("Escape");
    await expect(fixDrawer).toBeHidden();

    // ── 【展开全部数据】清空过滤回完整表格，面板仍在 ──
    await expandAll.click();
    await expect(page.locator(".table-wrapper .el-table__row")).toHaveCount(
      TOTAL
    );
    await expect(page.locator(".step3-right")).toContainText(`共 ${TOTAL} 条`);

    // ── 验收③：滚动表格区后摘要面板仍常驻（表格是唯一滚动容器） ──
    await page.locator(".step3-right").evaluate(el => {
      el.scrollTop = el.scrollHeight;
    });
    await expect(page.locator(".summary-panel")).toBeVisible();

    expect(pageErrors).toEqual([]);
  });

  test("疑似重复默认不勾选、可手动勾选保留（验收④）", async ({ page }) => {
    await openPreview(page);

    // 默认：重复行未被勾选（selectAllValid 排除 is_duplicate）
    await expect(page.locator(".summary-foot .foot-selected")).toContainText(
      "已选择 4 条"
    );

    // 展开「疑似重复」→ 表格 1 行
    await card(page, "duplicate")
      .getByRole("button", { name: "展开查看" })
      .click();
    const row = page.locator(".table-wrapper .el-table__row");
    await expect(row).toHaveCount(1);

    // 行复选框可用（#1791 放开 dup 的 disabled），且默认未选中
    const rowInput = row.locator("input[type=checkbox]");
    await expect(rowInput).toBeEnabled();
    await expect(rowInput).not.toBeChecked();

    // 手动勾选 → 计入已选择
    await row.locator("label.el-checkbox").click();
    await expect(rowInput).toBeChecked();
    await expect(page.locator(".summary-foot .foot-selected")).toContainText(
      "已选择 5 条"
    );
    // 卡片复选框同步为全选态
    await expect(
      card(page, "duplicate").locator("input[type=checkbox]")
    ).toBeChecked();
  });
});
