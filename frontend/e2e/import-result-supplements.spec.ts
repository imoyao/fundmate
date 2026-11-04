import { expect, test, type Page } from "@playwright/test";
import { injectSupabaseSession } from "./support/session";

/**
 * 导入结果页「补充信息卡片」回归网（#980 批 B3 拆分 `ResultStep.vue` 后补的接线判据）。
 *
 * ResultStep 439 → 286：五张补充卡片整体搬进 `ResultSupplements.vue`，显隐规则
 * 收口到 `importResultModel.ts` 的 `buildResultView` / `shouldShowSupplements`。
 * 纯函数有单测（`importResultModel.spec.ts`，17 例），这里钉的是**拆分最容易断的接线**：
 *
 *   ① 父级 `hasSupplements` 总控 → 子组件 `v-if`：断掉的表现是「该出现的卡片不出现」，
 *      或更糟——「没有任何补充信息时，被渲染成一个只有 top 边框的空块」。
 *      后者是本次把「判空」从模板搬进纯函数时最典型的回退，而且**不报错**。
 *   ② props 逐字段连线：漏传一个计数，对应的那张卡就静默消失（模板 v-if 直接为假）。
 *   ③ 「无新增数据」分支仍保留独立的错误汇总块（它不走 ResultSupplements）。
 *
 * 打桩策略：真实走「选账户 → 上传 → 解析 → 确认导入」，只把 `/api/importers/parse/`
 * 与 `/api/importers/confirm/` 换成固定回执，让五张卡各自的计数可控。
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

/** 2 条完整 + 1 条疑似重复：确认后默认导入 2 条 */
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
  }
];

interface CommitPayload {
  imported: number;
  skipped: number;
  orphan_count: number;
  errors: Array<{ symbol: string; name: string; error: string }>;
  cash_transfers_created: number;
  kept_duplicates: number;
  kept_duplicates_blocked: number;
}

function commit(over: Partial<CommitPayload> = {}): CommitPayload {
  return {
    imported: 2,
    skipped: 1,
    orphan_count: 0,
    errors: [],
    cash_transfers_created: 0,
    kept_duplicates: 0,
    kept_duplicates_blocked: 0,
    ...over
  };
}

async function openResult(page: Page, payload: CommitPayload) {
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
          data: PARSE_ROWS,
          total: PARSE_ROWS.length,
          error_count: 0,
          duplicate_count: 1,
          cash_transfer_count: 0,
          message: "ok",
          error_code: 0
        }
      })
  );
  await page.route(
    url => url.pathname.includes("/api/importers/confirm"),
    route =>
      route.fulfill({
        json: { data: payload, message: "ok", error_code: 0 }
      })
  );

  await page.goto("/#/inventory/investment/import");

  // dev 模式会渲染右下角的「调试快进（DEV）」面板，它压在预览页的
  // 「确认导入」按钮上并拦截指针事件（Playwright 报 subtree intercepts
  // pointer events）。生产构建没有这块，测试里直接隐掉，避免用
  // `click({ force: true })` 绕过真实可点性检查。
  await page.addStyleTag({
    content: ".dev-jump-panel { display: none !important; }"
  });

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

  // 步骤3：预览 → 确认导入 → 步骤4 结果
  await expect(page.locator(".step3-container")).toBeVisible({
    timeout: 30_000
  });
  await page.locator(".import-btn").click();
  await expect(page.locator(".import-result")).toBeVisible({ timeout: 30_000 });
}

test.describe("导入结果页补充信息卡片（#980 批 B3 拆分后的接线判据）", () => {
  test.setTimeout(180_000);

  test.beforeEach(async ({ context, baseURL }) => {
    await injectSupabaseSession(context, baseURL!);
  });

  test("五张补充卡按回执计数各自出现（props 逐字段连线不断）", async ({
    page
  }) => {
    await openResult(
      page,
      commit({
        orphan_count: 1,
        errors: [
          { symbol: "000002", name: "万科A", error: "交易日期无法解析" }
        ],
        cash_transfers_created: 1,
        kept_duplicates: 1,
        kept_duplicates_blocked: 1
      })
    );

    // 主结果区仍是成功态
    await expect(page.locator(".result-title")).toHaveText("导入完成");

    const supplements = page.locator(".result-supplements");
    await expect(supplements).toBeVisible();

    // ① 银证转账（cashTransfersCreated）② 勾选保留（kept + keptBlocked）
    // ③ 孤儿交易（orphanCount）④ 导入错误汇总（hasImportErrors）⑤ 价格提示
    await expect(supplements).toContainText("银证转账已同步");
    await expect(supplements).toContainText("重复行已按勾选保留");
    await expect(supplements).toContainText("部分交易数据不完整");
    await expect(supplements).toContainText("持仓市价已自动更新");
    // #2723：错误汇总从 el-alert 换成 SoftBanner，标题改由消费方显式渲染
    // （.import-error-summary__title），锚点随之更换
    await expect(
      supplements.locator(".import-error-summary__title")
    ).toContainText("导入过程中部分记录因以下原因被跳过");

    // 计数落到文案里：漏传 prop 会先在这里露馅
    await expect(supplements).toContainText("已为 1 笔转账生成现金侧记录");
    await expect(supplements).toContainText(
      "1 笔疑似重复交易已按你的勾选保留入库"
    );
    await expect(supplements).toContainText("1 笔此前已保留过");
    await expect(supplements).toContainText("1 笔交易因缺少对应持仓记录");

    // 卡片数量：转账 / 保留 / 孤儿 / 价格提示 各一 + 错误汇总
    await expect(supplements.locator(".supplement-card")).toHaveCount(4);
  });

  test("回执全零时整块不渲染（父级 hasSupplements 总控，不出空边框块）", async ({
    page
  }) => {
    // 真正的全零态：0 入库（否则 showPriceUpdateTip 自带 imported>0 的前置条件会
    // 让价格提示卡成立，那是正确行为，不是空块）、0 孤儿、0 错误、0 转账 /
    // 保留 / 拦截。此时 hasSupplements 必须为假——五张卡一张都不许渲染出容器。
    await openResult(page, commit({ imported: 0, skipped: 1 }));

    await expect(page.locator(".result-title")).toHaveText("导入完成");
    // 关键回退点：若判空从父级挪进子组件并写错，这里会出现一个只有 border-top 的空块
    await expect(page.locator(".result-supplements")).toHaveCount(0);
    await expect(page.locator(".supplement-card")).toHaveCount(0);
    await expect(page.locator(".import-error-summary")).toHaveCount(0);
  });

  test("无新增数据分支：独立的错误汇总块仍在（不走 ResultSupplements）", async ({
    page
  }) => {
    await openResult(
      page,
      commit({
        imported: 0,
        skipped: 3,
        orphan_count: 0,
        errors: [
          { symbol: "000002", name: "万科A", error: "交易日期无法解析" },
          { symbol: "000003", name: "国农科技", error: "代码未匹配" }
        ]
      })
    );

    // 走的是「处理完成」分支（nothingImported：imported=0 且 orphan=0 且有错误）
    await expect(page.locator(".result-title")).toHaveText("处理完成");
    await expect(page.locator(".result-caption").first()).toContainText(
      "本次无新增交易，共跳过 3 条记录"
    );

    // 该分支的汇总块是 ResultStep 自己的 .result-supplements + title="跳过原因"
    const supplements = page.locator(".result-supplements");
    await expect(supplements).toHaveCount(1);
    await expect(
      supplements.locator(".import-error-summary__title")
    ).toHaveText("跳过原因");
    // 五张补充卡一张都不该出现
    await expect(supplements.locator(".supplement-card")).toHaveCount(0);
  });
});
