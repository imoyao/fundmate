import { expect, test } from "@playwright/test";

import { injectSupabaseSession } from "./support/session";

/**
 * #1694 回归网：E账户导入草稿层接线（A 方案）。
 *
 * 修复前（#1239 接线缺失）本用例必红：
 * - `persistDraft` 无调用点 → 解析成功后不落草稿 → 刷新后 Banner 永不出现；
 * - 即便恢复，`restoreDraft` 落 currentStep=1 而 `result` 不随草稿保存 →
 *   模板 `v-if="currentStep===0"` / `v-else-if="result"` 两支都不成立 → 内容区空白。
 *
 * 覆盖验收：解析成功后草稿真实落盘（persistDraft 有调用点）；刷新出现恢复 Banner；
 * 恢复后内容区渲染预览表格（不空白、落步骤 0）；丢弃后 Banner 不再出现。
 *
 * 打桩：POST /api/importers/holdings/parse/ 按后端真实信封返回行数据（docs/dev/frontend-e2e.md §7）。
 */

const PARSE_STUB = {
  data: [
    {
      symbol: "110011",
      name: "易方达中小盘",
      quantity: 4526.51,
      price: 1.1024,
      snapshot_date: "2026-09-25",
      error: ""
    }
  ],
  total: 1,
  error_count: 0
};

/** 上传输入框在 el-upload 内（EaccountUploadCard），解析成功后卡片折叠即消失 */
const FILE_INPUT = ".eaccount-upload input[type='file']";
/** 解析完成状态条（fileName + 计数 + 重新上传） */
const DONE_BAR = ".parse-done-bar";
/** 预览表格卡片（EaccountParsePreview 根节点） */
const PREVIEW_CARD = ".preview-card";
/** 恢复 Banner（EaccountDraftBanner 根节点） */
const BANNER = ".draft-banner";

/** 走一遍「上传 CSV → 解析成功」，回到解析完成状态 */
async function uploadAndParse(page: import("@playwright/test").Page) {
  await page.setInputFiles(FILE_INPUT, {
    name: "eaccount-holdings.csv",
    mimeType: "text/csv",
    buffer: Buffer.from("code,name,quantity\n110011,易方达中小盘,4526.51\n")
  });
  await expect(page.locator(DONE_BAR)).toBeVisible();
  await expect(page.locator(PREVIEW_CARD)).toBeVisible();
}

test.describe("E账户导入草稿层（#1694：persistDraft 接线 + 恢复落步骤 0 预览）", () => {
  test("解析成功落草稿，刷新后 Banner 恢复出预览表格且不空白", async ({
    context,
    page,
    baseURL
  }) => {
    await injectSupabaseSession(context, baseURL!);

    await page.route("**/api/importers/holdings/parse/", route =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(PARSE_STUB)
      })
    );

    await page.goto("/#/investment/eaccount-import");
    await uploadAndParse(page);

    // 刷新：persistDraft 必须已落盘（修复前无调用点 → Banner 永不出现，此断言即红）
    await page.reload();
    const banner = page.locator(BANNER);
    await expect(banner).toBeVisible();
    await expect(banner).toContainText("发现未完成的 E账户导入草稿（1 条持仓）");

    // 恢复：内容区必须渲染预览表格（修复前落步骤 1 且无 result → 整段内容空白）
    await banner.getByRole("button", { name: "恢复草稿" }).click();
    await expect(banner).toHaveCount(0);
    await expect(page.locator(PREVIEW_CARD)).toBeVisible();
    await expect(page.locator(DONE_BAR)).toBeVisible();
    // 落在步骤 0：第一步 head 为 process、第二步为 wait（状态 class 在 .el-step__head 上，修复前 active=1）
    await expect(
      page.locator(".import-steps .el-step__head").nth(0)
    ).toHaveClass(/is-process/);
    await expect(
      page.locator(".import-steps .el-step__head").nth(1)
    ).toHaveClass(/is-wait/);
    // 对账结果组件不得出现（恢复不产生 result；其根节点为 MetricGrid.result-grid）
    await expect(page.locator(".result-grid")).toHaveCount(0);
  });

  test("丢弃草稿后刷新 Banner 不再出现", async ({ context, page, baseURL }) => {
    await injectSupabaseSession(context, baseURL!);

    await page.route("**/api/importers/holdings/parse/", route =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(PARSE_STUB)
      })
    );

    await page.goto("/#/investment/eaccount-import");
    await uploadAndParse(page);
    await page.reload();

    const banner = page.locator(BANNER);
    await expect(banner).toBeVisible();
    await banner.getByRole("button", { name: "丢弃" }).click();
    await expect(banner).toHaveCount(0);

    // 丢弃是真删存储：再刷新也不复活
    await page.reload();
    await expect(page.locator(BANNER)).toHaveCount(0);
  });
});
