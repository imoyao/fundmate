import { expect, test, type Page } from "@playwright/test";
import { injectSupabaseSession } from "./support/session";

/**
 * 预览页两处「透明底主色按钮」与转账行批量入口（#2838）。
 *
 * 为什么需要真 DOM：`theme.scss` 里 `.el-button.el-button--primary` 把
 * `--el-button-text-color` 设成白色，与 Element Plus 的 `.el-button--primary.is-link`
 * 同权重且后加载 —— 结果所有 `link type="primary"` 按钮都是**白字透明底**，
 * 在页面上等于隐身（「补全」「恢复」「全部勾选」全中）。颜色算错的按钮不会被
 * 任何存在性断言发现，所以这里直接钉 computed color。
 */

const SEC_LEDGER = {
  id: 1,
  name: "华泰证券",
  ledger_type: "stock",
  default_allocation: "longterm",
  linked_cash_ledger_id: 2
};
const CASH_LEDGER = { id: 2, name: "招行储蓄卡", ledger_type: "bank" };

const baseRow = {
  display_type: "股票",
  op_type: "buy",
  op_type_label: "买入",
  fee: 0,
  trade_date: "2026-06-02",
  account_name: "",
  ledger_id: SEC_LEDGER.id,
  contract_id: "",
  is_cash_transfer: false,
  error: null as string | null,
  is_duplicate: false,
  allocation: null,
  link_group_id: null,
  link_warning: "",
  consumed_by: "",
  trade_amount: 0,
  net_amount: 0,
  notes: "",
  source: "e2e",
  is_calculated: false
};

const ROWS = [
  {
    ...baseRow,
    symbol: "563530",
    name: "卫星E",
    type: "etf",
    display_type: "ETF",
    quantity: 1000,
    price: 1.3,
    amount: 1300,
    notes: "证券买入"
  },
  {
    ...baseRow,
    symbol: "600036",
    name: "招商银行",
    type: "stock",
    quantity: null,
    price: null,
    amount: 6600,
    notes: "证券买入"
  },
  {
    ...baseRow,
    symbol: "113649",
    name: "丰山转债",
    type: "bond",
    display_type: "可转债",
    op_type: "dividend_cash",
    op_type_label: "现金分红",
    quantity: 90,
    price: 1,
    amount: 90,
    notes: "债券兑息",
    trade_date: "2026-06-05"
  },
  {
    // #2840：利息归本 = 投资收益，asset_type 是 cash 但没有标的、券商原文也不给代码。
    // 它不该被当成银证转账，更不该因为「没代码」就勾不上。
    ...baseRow,
    symbol: "",
    name: "利息归本",
    type: "cash",
    display_type: "现金",
    op_type: "dividend_cash",
    op_type_label: "现金分红",
    quantity: 0,
    price: 0,
    amount: 0.9,
    is_cash_transfer: false,
    notes: "利息归本",
    trade_date: "2026-06-02"
  },
  {
    ...baseRow,
    symbol: "__CASH__",
    name: "银行转证券",
    type: "cash",
    display_type: "现金",
    op_type: "deposit",
    op_type_label: "存入",
    quantity: 0,
    price: 0,
    amount: 8420.5,
    is_cash_transfer: true,
    trade_date: "2026-06-03"
  },
  {
    ...baseRow,
    symbol: "__CASH__",
    name: "OTC现金宝交",
    type: "cash",
    display_type: "现金",
    op_type: "withdraw",
    op_type_label: "取出",
    quantity: 0,
    price: 0,
    amount: 6501.2,
    is_cash_transfer: true,
    trade_date: "2026-06-04"
  },
  {
    // #2836：金额比「数量×单价」多 470 元，远超该行手续费 5.81——原先这行会拿到
    // 一枚绿色「正常」（StatusCell 缺分支），而概览条把它算进「需要修正」。
    ...baseRow,
    symbol: "002311",
    name: "海大集团",
    type: "stock",
    quantity: 200,
    price: 47.97,
    amount: 10064,
    fee: 5.81,
    notes: "证券买入",
    trade_date: "2026-06-06"
  }
];

async function mockApis(page: Page) {
  await page.route(
    url => /\/api\/ledgers\/?$/.test(url.pathname),
    route =>
      route.fulfill({
        json: { data: [SEC_LEDGER, CASH_LEDGER], message: "ok", error_code: 0 }
      })
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
          data: ROWS,
          total: ROWS.length,
          error_count: 0,
          duplicate_count: 0,
          cash_transfer_count: 2,
          message: "ok",
          error_code: 0
        }
      })
  );
}

/** 只走到上传步骤（不传文件）：用于断言首屏那些「说明型」构件 */
async function openUploadStep(page: Page) {
  await mockApis(page);
  await page.goto("/#/inventory/investment/import");
  await page.locator(".account-select").click();
  await page
    .locator(".el-select-dropdown:visible .el-select-dropdown__item", {
      hasText: SEC_LEDGER.name
    })
    .first()
    .click();
  await expect(page.locator(".upload-guide")).toBeVisible({ timeout: 30_000 });
}

async function openPreview(page: Page) {
  await mockApis(page);

  await page.goto("/#/inventory/investment/import");
  await page.locator(".account-select").click();
  await page
    .locator(".el-select-dropdown:visible .el-select-dropdown__item", {
      hasText: SEC_LEDGER.name
    })
    .first()
    .click();
  await page.locator(".golden-upload input[type=file]").setInputFiles({
    name: "ths.csv",
    mimeType: "text/csv",
    buffer: Buffer.from("x")
  });
  await expect(page.locator(".step3-container")).toBeVisible({
    timeout: 30_000
  });
}

/** 白字在浅底上肉眼不可见；只断言「不是白色」即可覆盖这个失效模式 */
async function colorOf(locator: ReturnType<Page["locator"]>) {
  return locator.evaluate(el => getComputedStyle(el).color as string);
}

test.describe("预览页按钮可见性与转账行批量勾选（#2838）", () => {
  test.setTimeout(180_000);

  test.beforeEach(async ({ context, baseURL }) => {
    await injectSupabaseSession(context, baseURL!);
  });

  test("步骤条：当前步高亮、已完成打勾，且不再有填充色横条", async ({
    page
  }) => {
    await openPreview(page);

    const steps = page.locator(".import-steps .step");
    await expect(steps).toHaveCount(4);
    await expect(steps.nth(0)).toHaveClass(/is-done/);
    await expect(steps.nth(1)).toHaveClass(/is-done/);
    await expect(steps.nth(2)).toHaveClass(/is-current/);
    await expect(steps.nth(2)).toContainText("预览与修正");
    await expect(steps.nth(3)).toHaveClass(/is-todo/);

    // 旧版 el-steps 的 simple 横条：有背景色、有左右 8% 内边距，像贴在页头下的膏药
    const bg = await page
      .locator(".import-steps")
      .evaluate(el => getComputedStyle(el).backgroundColor);
    expect(bg).toBe("rgba(0, 0, 0, 0)");
  });

  test("「全部勾选」可见且能用：两条转账行一次勾上，再点一次清掉", async ({
    page
  }) => {
    await openPreview(page);

    const btn = page.locator(".ov-note-action");
    await expect(btn).toBeVisible();
    await expect(btn).toHaveText("全部勾选");
    // 守 theme.scss：透明底主色按钮若拿到白字，这个按钮在页面上等于不存在
    expect(await colorOf(btn)).not.toBe("rgb(255, 255, 255)");

    const transferChecks = page
      .locator(".table-wrapper .el-table__row:visible")
      .filter({ hasText: "__CASH__" })
      .locator("input[type=checkbox]");

    await btn.click();
    await expect(btn).toHaveText("全部取消");
    await expect(page.locator(".summary-primary")).toContainText("已选择");
    for (const box of await transferChecks.all()) {
      await expect(box).toBeChecked();
    }

    await btn.click();
    await expect(btn).toHaveText("全部勾选");
    for (const box of await transferChecks.all()) {
      await expect(box).not.toBeChecked();
    }
  });

  test("操作列「补全」不是白字：缺数量/价格的行要能看见这个入口", async ({
    page
  }) => {
    await openPreview(page);

    const row = page
      .locator(".table-wrapper .el-table__row:visible")
      .filter({ hasText: "招商银行" });
    const fill = row.getByRole("button", { name: "补全" });
    await expect(fill).toHaveCount(1);
    expect(await colorOf(fill)).not.toBe("rgb(255, 255, 255)");
  });

  test("产品列不再重复操作列：证券买入不显示，债券兑息要显示", async ({
    page
  }) => {
    await openPreview(page);

    const table = page.locator(".table-wrapper");
    await expect(table).toContainText("债券兑息");

    // 「证券买入」与操作列的「买入」是同义重复，只按原文判据隐藏；这里直接数出现次数
    const dup = await table.evaluate(
      el => (el.textContent || "").split("证券买入").length - 1
    );
    expect(dup).toBe(0);
  });

  /**
   * #2836：金额对不上的行曾被标成绿色「正常」。
   *
   * 这条的判据不能只看「有没有「金额不符」这几个字」——那只能证明标签存在，
   * 证明不了**原来那枚「正常」不再出现**。所以两件事都断言：该行拿到「金额不符」，
   * 且它不再是「正常」。
   */
  test("金额对不上的行标「金额不符」，不再冒充「正常」", async ({ page }) => {
    await openPreview(page);

    const row = page
      .locator(".table-wrapper .el-table__row:visible")
      .filter({ hasText: "海大集团" });

    await expect(row.locator(".el-tag", { hasText: "金额不符" })).toHaveCount(
      1
    );
    await expect(row.locator(".el-tag", { hasText: "正常" })).toHaveCount(0);
  });

  test("「全部数据 / 只看问题」是两个真靶区，不是一个开关的两端", async ({
    page
  }) => {
    await openPreview(page);

    const tabs = page.locator(".table-controls [role=tab]");
    await expect(tabs).toHaveCount(2);
    await expect(tabs.nth(0)).toHaveText(/全部数据/);
    await expect(tabs.nth(1)).toHaveText(/只看问题/);

    // 点左端文字必须生效（el-switch 时代点文字没反应，这是本条的核心）
    await tabs.nth(1).click();
    await expect(tabs.nth(1)).toHaveClass(/is-active/);
    await expect(tabs.nth(0)).not.toHaveClass(/is-active/);

    await tabs.nth(0).click();
    await expect(tabs.nth(0)).toHaveClass(/is-active/);
  });

  /**
   * #2836：备注曾被挤在「代码行」，`# 113649` 吃掉约 66px，真实备注一律截成
   * 「债券兑息兑…」。挪到名称行后要能完整显示——判据用 scrollWidth vs clientWidth，
   * 因为省略号是 CSS 画的，`toHaveText` 读到的仍是全文，看不出被截。
   */
  test("产品列备注完整显示（不再截成「债券兑息兑…」）", async ({ page }) => {
    await openPreview(page);

    const note = page
      .locator(".table-wrapper .el-table__row:visible")
      .filter({ hasText: "丰山转债" })
      .locator(".product-notes");

    await expect(note).toHaveText("债券兑息");
    const overflow = await note.evaluate(el => el.scrollWidth - el.clientWidth);
    expect(overflow).toBeLessThanOrEqual(1);

    // 备注必须与名称同行（第二行留给代码 + 类型标签）
    const inNameRow = await note.evaluate(
      el => el.parentElement?.classList.contains("product-name-row") ?? false
    );
    expect(inNameRow).toBe(true);
  });

  /**
   * #2836：格式说明卡从「右侧 340px 窄栏」改为「上传区下方通栏横排」。
   *
   * 判据用 computed `grid-template-columns` 的段数：它直接反映渲染出来的栏数，
   * 而「卡片在哪一栏」这种布局意图靠 DOM 顺序是看不出来的。1440 视口下要求 ≥3 栏
   * （窄栏时代恒为 1）。
   */
  test("上传步骤的格式说明卡是横排多栏，不再挤在右侧窄栏", async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await openUploadStep(page);

    const cols = await page
      .locator(".format-guide-list")
      .evaluate(el => getComputedStyle(el).gridTemplateColumns);
    expect(cols.split(" ").length).toBeGreaterThanOrEqual(3);

    // 通栏：卡片左边缘应与上传区左边缘对齐（不再是右侧 320px 那一条）
    const guideBox = await page.locator(".format-guide").boundingBox();
    const uploadBox = await page.locator(".golden-upload").boundingBox();
    expect(guideBox!.width).toBeGreaterThan(700);
    expect(Math.abs(guideBox!.x - uploadBox!.x)).toBeLessThanOrEqual(2);
  });

  /**
   * #2836：操作类型列 104px 时，「债转股 · 可转债」被截成「可转」——资产类型直接丢失。
   * 判据仍是 scrollWidth vs clientWidth：省略号不看这两个值量不出来。
   *
   * 用 `expect.poll`：el-table 在数据填入后会有一轮列宽重算，紧跟 openPreview 取一次
   * 几何会撞上中间态（单独跑绿、整套跑红就是这么来的）。
   */
  test("操作类型列的「可转债」标签不被截断", async ({ page }) => {
    // 列宽预算（1060px）是按「1200 视口不横滚」定的，这里必须在基准视口量——
    // 默认 1024 下 11 列会被整体压缩到 minWidth 以下，量到的是压缩态，不是设计态。
    await page.setViewportSize({ width: 1440, height: 900 });
    await openPreview(page);

    const cell = page
      .locator(".table-wrapper .el-table__row:visible")
      .filter({ hasText: "丰山转债" })
      .locator(".op-type-cell");

    await expect(cell.locator(".el-tag")).toHaveText("可转债");
    await expect
      .poll(() => cell.evaluate(el => el.scrollWidth - el.clientWidth), {
        timeout: 10_000
      })
      .toBeLessThanOrEqual(1);
  });

  /**
   * #2840：利息归本（现金利息）曾同时踩两个坑——
   * ① 被 `asset_type == 'cash'` 判成银证转账 ⇒ 要求先关联现金账户、计入「含 N 条银证转账」；
   * ② 又因为没代码被判「代码未匹配」⇒ 勾不上，也不进任何计数，只剩一个标签干挂着。
   */
  test("现金利息行可以勾选，且不再挂「代码未匹配」", async ({ page }) => {
    await openPreview(page);

    const row = page
      .locator(".table-wrapper .el-table__row:visible")
      .filter({ hasText: "利息归本" });

    await expect(row.locator(".el-tag", { hasText: "代码未匹配" })).toHaveCount(
      0
    );
    await expect(row.locator("input[type=checkbox]")).toBeChecked();
  });

  /**
   * #2840：底栏三个数字曾来自三个分母（已选 169 / 另有 169 / 按钮 169+40），
   * 用户没法核对「银证转账到底算不算在内」。
   *
   * 判据不放宽成「文案里有没有这几个字」——那证明不了分母一致。这里把数字解析出来
   * 相加，必须等于概览条上的「全部」。
   */
  test("底栏计数可互算：已选 + 未勾选 == 全部", async ({ page }) => {
    await openPreview(page);

    const summary = page.locator(".summary-primary");
    await expect(summary).toContainText("已选择");

    const flat = (await summary.innerText()).replace(/\s/g, "");
    const selected = Number(flat.match(/已选择(\d+)条/)?.[1]);
    const unselected = Number(flat.match(/另有(\d+)条未勾选/)?.[1] ?? 0);

    const allText = await page.locator(".ov-all").innerText();
    const all = Number(allText.replace(/\s/g, "").match(/(\d+)/)?.[1]);

    expect(selected).toBeGreaterThan(0);
    expect(selected + unselected).toBe(all);
  });

  /**
   * #2840：转账行默认不勾，所以「含 N 条银证转账」不该凭空空降；
   * 勾上之后它必须出现，且条数与勾上的转账行一致——这正是用户看不清的那件事。
   */
  test("「含 N 条银证转账」只在勾了转账时出现", async ({ page }) => {
    await openPreview(page);

    const summary = page.locator(".summary-primary");
    await expect(summary).not.toContainText("银证转账");

    await page.locator(".ov-note-action").click();

    const flat = (await summary.innerText()).replace(/\s/g, "");
    const n = Number(flat.match(/含(\d+)条银证转账/)?.[1]);
    expect(n).toBe(2);
  });

  /**
   * #2840：中间那个按钮执行的是「把勾选重置成正常行」，不是第二种导入。
   * 原文案「跳过这 N 条，导入 M 条」把两个不同分母的数字并列，还隐瞒了
   * 「会把已勾的转账一起清掉」这个副作用。
   *
   * 它只在「当前勾选 ≠ 正常行」时才有意义（勾了转账、或手动取消了几行）；
   * 初始状态（已选 == 正常行）下出现只会让人以为还有第二种导入。
   */
  test("重置勾选的按钮只说「正常行」，且只在勾选偏离正常行时出现", async ({
    page
  }) => {
    await openPreview(page);

    const bar = page.locator(".fixed-action-bar");
    const reset = bar.getByRole("button", { name: /只导入正常行/ });

    // 初始：默认勾选的就是可自动导入的行，没有「重置」可言
    await expect(reset).toHaveCount(0);

    // 勾上转账后，勾选偏离了正常行，重置入口才该出现
    await page.locator(".ov-note-action").click();
    await expect(reset).toHaveCount(1);
    await expect(reset).toContainText(/只导入正常行（\d+ 条）/);

    // 旧文案里的「跳过这 N 条，导入 M 条」两个分母并存，已删掉
    await expect(bar).not.toContainText("跳过这");
  });
});
