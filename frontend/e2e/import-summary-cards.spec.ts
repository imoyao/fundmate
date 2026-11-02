import { expect, test, type Page } from "@playwright/test";
import { injectSupabaseSession } from "./support/session";

/**
 * 导入预览「概览条」（原 #1791 三卡片，2026-11-02 改为一栏胶囊）。
 *
 * 覆盖验收：
 * - ① 三类胶囊条数 = 点该胶囊后表格行数 = 「全部」胶囊条数（三者互证）；
 * - ② 点胶囊筛表时概览条不消失（表格仍是唯一滚动容器）；
 * - ③ 疑似重复默认不计入导入集合，可手动勾选保留（沿 #1791 验收④）；
 * - ④ 点「需要修正」= 筛选 + 自动展开修正面板，且等式行写出细分构成。
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
    // 差额 100 远大于 fee 5：这是「真对不上」，不是被手续费解释。
    // （旧数据 amount 999 + fee 5 自 2026-11-02 费用容差上线后已属「可解释」，会归 complete，
    //  那样这条 fixture 就测不到 mismatch 分区了——e2e 只看夜间绿灯，最容易烂在这种地方。）
    amount: 900
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

type Category = "complete" | "duplicate" | "fix";

/** 类别胶囊：左侧复选框 + 右侧主体（筛表），两个独立靶区 */
function chip(page: Page, category: Category) {
  return page.locator(`.ov-chip[data-category="${category}"]`);
}

/** 点胶囊主体＝按该类筛表（复选框是「按类全选」，别混用） */
function chipButton(page: Page, category: Category) {
  return chip(page, category).locator(".ov-chip-btn");
}

/** 「全部」胶囊：清空筛选 */
function allChip(page: Page) {
  return page.locator('.ov-all[data-category="all"]');
}

/** 底部操作条的「已选择 N 条」——概览条不再重复显示已选数，只有这一处 */
function selectedLine(page: Page) {
  return page.locator(".action-summary .summary-primary");
}

test.describe("导入预览概览条（原 #1791 三卡片）", () => {
  test.setTimeout(180_000);

  test.beforeEach(async ({ context, baseURL }) => {
    await injectSupabaseSession(context, baseURL!);
  });

  test("胶囊条数 = 筛后表格行数 = 全部条数（三者互证），等式行写出细分构成", async ({
    page
  }) => {
    const pageErrors: string[] = [];
    page.on("pageerror", e => pageErrors.push(e.message));

    await openPreview(page);

    // ── 概览条：全部 6 + 三类 2 / 1 / 3 ──
    await expect(allChip(page)).toContainText(String(TOTAL));
    const chips = page.locator(".ov-chip");
    await expect(chips).toHaveCount(3);
    await expect(chip(page, "complete").locator(".ov-count")).toHaveText("2");
    await expect(chip(page, "duplicate").locator(".ov-count")).toHaveText("1");
    await expect(chip(page, "fix").locator(".ov-count")).toHaveText("3");

    // 等式行：不需要用户自己把 1+1+1 加一遍
    const breakdown = page.locator(".ov-breakdown");
    await expect(breakdown).toContainText("需要修正 3 条 =");
    await expect(breakdown).toContainText("解析错误 1");
    await expect(breakdown).toContainText("代码未匹配 1");
    await expect(breakdown).toContainText("差额超出手续费 1");

    // 底部「已选择」：selectAllValid 排除重复/错误/待补全，选中 4 行
    await expect(selectedLine(page)).toContainText("已选择 4 条");

    // ── 未筛选：完整表格 6 行，「全部」胶囊为选中态 ──
    await expect(page.locator(".table-wrapper .el-table__row")).toHaveCount(
      TOTAL
    );
    await expect(allChip(page)).toHaveClass(/is-active/);

    // ── 点「可直接导入」→ 表格 2 行，与胶囊条数一致；概览条常驻 ──
    await chipButton(page, "complete").click();
    await expect(page.locator(".table-wrapper .el-table__row")).toHaveCount(2);
    await expect(page.locator(".step3-right")).toContainText("共 2 条");
    await expect(chip(page, "complete")).toHaveClass(/is-active/);
    await expect(page.locator(".summary-panel")).toBeVisible();

    // 再点一次同一胶囊 → 收起筛选，回到 6 行
    await chipButton(page, "complete").click();
    await expect(page.locator(".table-wrapper .el-table__row")).toHaveCount(
      TOTAL
    );
    await expect(chip(page, "complete")).not.toHaveClass(/is-active/);

    // ── 点「需要修正」→ 表格 3 行 + 修正面板自动展开（点它的人下一步就是修它）──
    await chipButton(page, "fix").click();
    await expect(page.locator(".table-wrapper .el-table__row")).toHaveCount(3);
    const fixPanel = page.locator("[data-fix-panel]");
    await expect(fixPanel).toBeVisible();
    await expect(page.locator(".summary-panel")).toBeVisible();

    // 【收起批量修正】已移到顶行右侧，仍在面板内
    await fixPanel.getByRole("button", { name: "收起批量修正" }).click();
    await expect(fixPanel).toBeHidden();
    // 收起面板不清筛选：表格仍是那 3 行
    await expect(page.locator(".table-wrapper .el-table__row")).toHaveCount(3);

    // ── 点「全部」→ 清空筛选回完整表格 ──
    await allChip(page).click();
    await expect(page.locator(".table-wrapper .el-table__row")).toHaveCount(
      TOTAL
    );
    await expect(page.locator(".step3-right")).toContainText(`共 ${TOTAL} 条`);

    // ── 验收③：滚动表格区后概览条仍常驻（表格是唯一滚动容器） ──
    await page.locator(".step3-right").evaluate(el => {
      el.scrollTop = el.scrollHeight;
    });
    await expect(page.locator(".summary-panel")).toBeVisible();

    expect(pageErrors).toEqual([]);
  });

  test("疑似重复默认不勾选、可手动勾选保留（沿 #1791 验收④）", async ({
    page
  }) => {
    await openPreview(page);

    // 默认：重复行未被勾选（selectAllValid 排除 is_duplicate）
    await expect(selectedLine(page)).toContainText("已选择 4 条");

    // 按「疑似重复」筛表 → 表格 1 行
    await chipButton(page, "duplicate").click();
    const row = page.locator(".table-wrapper .el-table__row");
    await expect(row).toHaveCount(1);

    // 行复选框可用（#1791 放开 dup 的 disabled），且默认未选中
    const rowInput = row.locator("input[type=checkbox]");
    await expect(rowInput).toBeEnabled();
    await expect(rowInput).not.toBeChecked();

    // 手动勾选 → 计入已选择
    await row.locator("label.el-checkbox").click();
    await expect(rowInput).toBeChecked();
    await expect(selectedLine(page)).toContainText("已选择 5 条");

    // 胶囊左侧复选框同步为全选态（勾选与筛选是两个靶区，互不触发）
    await expect(
      chip(page, "duplicate").locator("input[type=checkbox]")
    ).toBeChecked();
  });
});
