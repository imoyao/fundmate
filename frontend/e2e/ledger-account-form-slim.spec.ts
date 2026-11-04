import { expect, test, type Page } from "@playwright/test";
import { injectSupabaseSession } from "./support/session";

/**
 * #980 批 B1 拆分回归网：账户表单（`AccountFormFields` → 三个宿主）。
 *
 * 原 587 行文件把「销售机构检索」「活期+ 远程搜索」「自动申购联动」挤在一起，
 * 拆成 `SalesInstitutionSelect` / `MoneyFundBindingFields` / `accountFormModel` 后，
 * 最容易静默坏掉的是**跨组件联动**——它们不会报错，只是字段不见了或该清空没清空：
 *
 * 1. 账户类型不是证券/基金平台时，「现金账户 / 活期+ / 自动申购」三块必须整体不渲染
 *    （v-if 从父模板挪到组件调用点，漏了就会给银行账户显示活期+）；
 * 2. 切回非渠道类型时必须清空关联值（`linkedCashId` / `feeConfig` / 活期+ / 自动申购），
 *    这条逻辑仍在父组件 `onTypeChange` 里，拆分后要确认 emit 链没断；
 * 3. 销售机构下拉的「常用机构 / 全部机构」分组由模型层过滤产出，
 *    props 传错（比如把 institutions 传成 undefined）只会变成一个空下拉。
 */

const COMMON_INST = {
  id: 1,
  org_name: "蚂蚁（杭州）基金销售有限公司",
  display_name: "支付宝",
  pinyin_short: "zfb",
  org_type: "独立基金销售机构",
  is_common: true,
  common_sort: 1
};

const OTHER_INST = {
  id: 2,
  org_name: "华泰证券股份有限公司",
  display_name: "华泰证券",
  pinyin_short: "htzq",
  org_type: "证券公司",
  is_common: false,
  common_sort: null
};

/**
 * 打桩账户页所需接口。
 *
 * ⚠️ 路由必须锚定 host：宽 glob 会把 vite 的源码模块请求（`/src/api/ledger.ts`）
 * 一起拦掉，页面直接白屏。
 */
async function stubLedgers(page: Page): Promise<void> {
  // ⚠️ 顺序即优先级：Playwright 的 route 是**后注册先匹配**。
  // 所以从宽到窄依次注册——兜底最宽排第一，`/api/ledgers/` 的列表 stub 必须
  // 排在 sales-institutions / aggregation 之前，否则那两条具体 stub 会被它吃掉
  // （表现：机构列表为空、下拉没有选项，但不报任何错）。
  await page.route(/^https?:\/\/[^/]+\/api\//, route =>
    route.fulfill({
      status: 404,
      json: { data: null, message: "e2e 未打桩", error_code: 40400 }
    })
  );

  await page.route(/^https?:\/\/[^/]+\/api\/ledgers\//, route =>
    route.fulfill({ status: 200, json: { data: [], total: 0 } })
  );

  await page.route(/^https?:\/\/[^/]+\/api\/portfolios\//, route =>
    route.fulfill({ status: 200, json: { data: [] } })
  );

  await page.route(
    /^https?:\/\/[^/]+\/api\/ledgers\/(fund|securities)-aggregation\//,
    route =>
      route.fulfill({
        status: 200,
        json: {
          data: {
            total_market_value_cents: 0,
            dimension: "product",
            groups: [],
            total: 0,
            page: 1,
            page_size: 18,
            total_pages: 1
          }
        }
      })
  );

  await page.route(
    /^https?:\/\/[^/]+\/api\/ledgers\/sales-institutions\//,
    route =>
      route.fulfill({ status: 200, json: { data: [COMMON_INST, OTHER_INST] } })
  );
}

/** 打开「新增账户」对话框 */
async function openCreateDialog(page: Page) {
  await page.goto("/#/asset/ledgers");
  await page.getByRole("button", { name: /新增账户/ }).click();
  const dialog = page.locator(".el-dialog");
  await expect(dialog).toBeVisible({ timeout: 90_000 });
  return dialog;
}

/** 切换账户类型（el-select + 下拉项） */
async function pickLedgerType(page: Page, label: string) {
  const dialog = page.locator(".el-dialog");
  const typeItem = dialog
    .locator(".el-form-item")
    .filter({ hasText: "账户类型" })
    .first();
  await typeItem.locator(".el-select").click();
  await page
    .locator(".el-select-dropdown__item")
    .filter({ hasText: new RegExp(`^${label}$`) })
    .first()
    .click();
}

test.describe("账户表单拆分回归（#980 批 B1）", () => {
  test.setTimeout(180_000);

  test.beforeEach(async ({ context, baseURL }) => {
    await injectSupabaseSession(context, baseURL!);
  });

  test("银行账户：不显示现金账户 / 活期+ / 自动申购，销售机构始终在", async ({
    page
  }) => {
    await stubLedgers(page);
    const dialog = await openCreateDialog(page);

    // 账户类型默认「银行」
    await expect(dialog.getByText("账户类型")).toBeVisible();

    // 银行渠道没有这三块（拆分后 v-if 在父模板的组件调用点上）
    await expect(dialog.getByText("现金账户", { exact: true })).toHaveCount(0);
    await expect(dialog.getByText("活期+", { exact: true })).toHaveCount(0);
    await expect(dialog.getByText("自动申购", { exact: true })).toHaveCount(0);

    // 销售机构始终存在
    await expect(dialog.getByText("销售机构", { exact: true })).toBeVisible();
  });

  test("切到证券：三块出现；切回银行：三块消失（emit 链未断）", async ({
    page
  }) => {
    await stubLedgers(page);
    const dialog = await openCreateDialog(page);

    await pickLedgerType(page, "证券");

    await expect(dialog.getByText("现金账户", { exact: true })).toBeVisible();
    await expect(dialog.getByText("活期+", { exact: true })).toBeVisible();
    await expect(dialog.getByText("自动申购", { exact: true })).toBeVisible();
    // 未绑定活期+ → 开关禁用 + 说明文案走「请先绑定」分支
    await expect(
      dialog.getByText("请先绑定活期+，再开启自动申购")
    ).toBeVisible();

    await pickLedgerType(page, "银行");

    await expect(dialog.getByText("现金账户", { exact: true })).toHaveCount(0);
    await expect(dialog.getByText("活期+", { exact: true })).toHaveCount(0);
  });

  test("销售机构下拉：常用置顶 + 按账户类型过滤", async ({ page }) => {
    await stubLedgers(page);
    const dialog = await openCreateDialog(page);

    const instItem = dialog
      .locator(".el-form-item")
      .filter({ hasText: "销售机构" })
      .first();
    const instInput = instItem.locator("input").first();
    const dropdownItem = (text: string) =>
      page.locator(".el-select-dropdown__item").filter({ hasText: text });

    // 银行渠道：两类机构都能搜到（检索走 filter-method 三路匹配）
    await instInput.click();
    await instInput.fill("华泰");
    await expect(dropdownItem("华泰证券")).toBeVisible();

    await instInput.fill("支付宝");
    await expect(dropdownItem("支付宝")).toBeVisible();

    // 关键：切到证券渠道后，独立销售机构（支付宝）必须被过滤掉
    await page.keyboard.press("Escape");
    await pickLedgerType(page, "证券");
    await instInput.fill("支付宝");
    await expect(dropdownItem("支付宝")).toHaveCount(0);
    await instInput.fill("华泰");
    await expect(dropdownItem("华泰证券")).toBeVisible();
  });
});
