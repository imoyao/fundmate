import { expect, test, type Page } from "@playwright/test";

import { injectSupabaseSession } from "./support/session";

/**
 * 录入通用资产页回归网（#980 拆分 `AssetEntry.vue` 后补的接线判据）。
 *
 * 666 行的页面拆成 `assetEntry/`（表单 / 大类联动 / 建账弹窗 + 纯函数层）。
 * 纯函数已有单测（`assetEntryModel.spec.ts`），这里钉的是**拆组件最容易断的接线**：
 *
 * 1. **大类 → 子类联动**：三个下拉现在住在 `AssetCategoryFields` 里，靠两个
 *    `v-model:*` 回到表单。断一环的表现是「切了大类，子类选择器不出现 / 不清空」
 *    ——不报错，但会把投资细分写到固定资产上；
 * 2. **URL 初值落位**：`?category=fixed&type=house` 由页面解析后作为 `initial`
 *    递给表单。此前 `?type=` 被静默丢弃（#1798），房产在详情页无法与其他固定资产区分；
 * 3. **建账弹窗 → 表单回填**：弹窗是页面的兄弟节点，建完要走 `created` →
 *    `pickedLedger` → 表单 watch 这一段。断一环的表现是「提示创建成功，
 *    所属账户却没选上」。
 *
 * 断言只落在「选完能看到什么、请求里发了什么」，不测样式值。
 */

const LEDGERS = [
  { id: 1, name: "招商银行", ledger_type: "bank", currency: "CNY" },
  { id: 2, name: "华泰证券", ledger_type: "securities", currency: "CNY" }
];

/** 建账返回体：id 必须非 0，否则「所属账户」回填会落空 */
const CREATED_LEDGER = {
  id: 99,
  name: "天天基金",
  ledger_type: "fund",
  currency: "CNY"
};

type Call = { method: string; path: string; body: Record<string, unknown> };

/** 只打桩 /api/：vite 源码模块请求不能碰，否则整页白屏 */
async function mockApis(page: Page): Promise<Call[]> {
  const calls: Call[] = [];
  let created = false;
  await page.route(/^https?:\/\/[^/]+\/api\//, async route => {
    const url = new URL(route.request().url());
    const method = route.request().method();

    if (url.pathname.startsWith("/api/assets")) {
      if (method === "POST") {
        calls.push({
          method,
          path: url.pathname,
          body: (route.request().postDataJSON() ?? {}) as Record<
            string,
            unknown
          >
        });
        return route.fulfill({ json: { data: { id: 1 }, message: "" } });
      }
      return route.fulfill({ json: { data: [], message: "" } });
    }
    if (url.pathname.startsWith("/api/ledgers")) {
      if (method === "POST") {
        calls.push({
          method,
          path: url.pathname,
          body: (route.request().postDataJSON() ?? {}) as Record<
            string,
            unknown
          >
        });
        created = true;
        return route.fulfill({ json: { data: CREATED_LEDGER, message: "" } });
      }
      // 建账成功后页面会重新拉列表，这份要带上新建的账户
      return route.fulfill({
        json: {
          data: created ? [...LEDGERS, CREATED_LEDGER] : LEDGERS,
          message: ""
        }
      });
    }
    if (url.pathname.startsWith("/api/ledgers/sales-institutions")) {
      return route.fulfill({ json: { data: [], message: "" } });
    }
    return route.fulfill({ json: { data: [], message: "" } });
  });
  return calls;
}

async function openAssetEntry(page: Page, query = "") {
  await page.goto(`/#/asset/asset-entry${query}`, { waitUntil: "commit" });
  await expect(page.locator(".entry-card")).toBeVisible({ timeout: 150_000 });
}

/** 按表单项标签定位（「资产大类」与「资产子类」标签相近，必须精确匹配） */
function formItem(page: Page, label: string) {
  return page
    .locator(".el-form-item")
    .filter({
      has: page.locator(".el-form-item__label", {
        hasText: new RegExp(`^${label}$`)
      })
    })
    .first();
}

/** 填完必填项并提交，等成功提示 */
async function submitWith(page: Page, name: string, amount: string) {
  await formItem(page, "资产名称").locator("input").fill(name);
  await formItem(page, "金额").locator("input").fill(amount);
  await pickOption(page, "所属账户", "招商银行");
  await page.getByRole("button", { name: "确认录入" }).click();
  await expect(page.getByText("已录入资产")).toBeVisible({ timeout: 30_000 });
}

/** 取最近一次创建资产的请求体 */
function assetCalls(calls: Call[]) {
  return calls.filter(
    c => c.path.startsWith("/api/assets") && c.method === "POST"
  );
}

async function pickOption(page: Page, rootLabel: string, optionText: string) {
  const select = formItem(page, rootLabel).locator(".el-select").first();
  await select.click();
  await page
    .locator(".el-select-dropdown__item:visible")
    .filter({ hasText: optionText })
    .first()
    .click();
}

test.describe("录入通用资产页（#980 拆分后的接线判据）", () => {
  test.beforeEach(async ({ context, baseURL }) => {
    await injectSupabaseSession(context, baseURL!);
  });

  test("大类 → 子类联动：切到固定资产出「资产子类」，切回投资理财出「投资类型」，且旧细分被清掉", async ({
    page
  }) => {
    test.setTimeout(240_000);
    const calls = await mockApis(page);
    await openAssetEntry(page);

    // 默认 cash：两个子类选择器都不该出现
    await expect(formItem(page, "资产子类")).toHaveCount(0);
    await expect(formItem(page, "投资类型")).toHaveCount(0);

    // 固定资产 → 资产子类（house/car/gold）
    await pickOption(page, "资产大类", "固定资产");
    await expect(formItem(page, "资产子类")).toBeVisible();
    await expect(formItem(page, "投资类型")).toHaveCount(0);
    await pickOption(page, "资产子类", "房产");

    // 切到投资理财：子类选择器换一个
    await pickOption(page, "资产大类", "投资理财");
    await expect(formItem(page, "投资类型")).toBeVisible();
    await expect(formItem(page, "资产子类")).toHaveCount(0);

    // 判据：切大类必须清掉不适用的细分，否则 house 会被写到投资理财上。
    // 用提交载荷钉，不靠下拉的显示文本（placeholder 里也含「房产」，读文本会误判）。
    await submitWith(page, "某银行理财", "10000");
    const payload = assetCalls(calls).at(-1)?.body;
    expect(payload).toMatchObject({ major_category: "investment" });
    expect(payload).not.toHaveProperty("minor_category");
  });

  test("URL 初值：?category=fixed&type=house 落到大类与子类（#1798）", async ({
    page
  }) => {
    test.setTimeout(240_000);
    const calls = await mockApis(page);
    await openAssetEntry(page, "?category=fixed&type=house");

    // 大类与子类选择器都要在位（此前 ?type= 被静默丢弃，房产在详情页无法区分）
    await expect(formItem(page, "资产大类")).toContainText("固定资产");
    await expect(formItem(page, "资产子类")).toBeVisible();

    // 用提交载荷钉「子类真的落库了」——下拉的 placeholder 里也含「房产」，
    // 只读显示文本会把「没选中」误判成「选中了」。
    await submitWith(page, "阳光花园", "1200000");
    expect(assetCalls(calls).at(-1)?.body).toMatchObject({
      major_category: "fixed",
      minor_category: "house"
    });
  });

  test("非法 ?type= 一律忽略，不写进 minor_category", async ({ page }) => {
    test.setTimeout(240_000);
    const calls = await mockApis(page);
    await openAssetEntry(page, "?category=fixed&type=__evil__");
    await expect(formItem(page, "资产大类")).toContainText("固定资产");

    await submitWith(page, "某固定资产", "5000");
    const payload = assetCalls(calls).at(-1)?.body;
    expect(payload).toMatchObject({ major_category: "fixed" });
    expect(payload).not.toHaveProperty("minor_category");
  });

  test("提交：以 ledger_id 为准，成功后表单重置", async ({ page }) => {
    test.setTimeout(240_000);
    const calls = await mockApis(page);
    await openAssetEntry(page);

    await formItem(page, "资产名称").locator("input").fill("阳光花园房产");
    await pickOption(page, "资产大类", "固定资产");
    await pickOption(page, "资产子类", "房产");
    await formItem(page, "金额").locator("input").fill("1200000");
    await pickOption(page, "所属账户", "招商银行");

    await page.getByRole("button", { name: "确认录入" }).click();

    // 判据：payload 以 ledger_id 为准，且带上固定资产子类
    await expect(page.getByText("已录入资产")).toBeVisible({ timeout: 30_000 });
    const assetCall = calls.find(c => c.path.startsWith("/api/assets"));
    expect(assetCall, "未发出创建资产请求").toBeTruthy();
    expect(assetCall!.body).toMatchObject({
      name: "阳光花园房产",
      major_category: "fixed",
      minor_category: "house",
      ledger_id: 1
    });

    // 成功后重置：大类回到 cash（子类选择器随之消失）
    await expect(formItem(page, "资产大类")).toContainText("流动资金");
    await expect(formItem(page, "资产子类")).toHaveCount(0);
    await expect(formItem(page, "资产名称").locator("input")).toHaveValue("");
  });

  test("新增账户弹窗：建完回填到「所属账户」", async ({ page }) => {
    test.setTimeout(240_000);
    const calls = await mockApis(page);
    await openAssetEntry(page);

    await page.getByRole("button", { name: "新增账户" }).click();
    const dialog = page.locator(".el-dialog:visible");
    await expect(dialog).toBeVisible({ timeout: 30_000 });

    await dialog.getByPlaceholder("如：招商银行、华泰证券").fill("天天基金");
    await dialog.locator(".el-select").first().click();
    await page
      .locator(".el-select-dropdown__item:visible")
      .filter({ hasText: "基金" })
      .first()
      .click();
    await dialog.getByRole("button", { name: "确认创建" }).click();

    // 判据 3：弹窗关闭 + 账户列表已刷新 + 表单的「所属账户」被回填
    await expect(page.locator(".el-dialog:visible")).toBeHidden({
      timeout: 30_000
    });
    await expect(formItem(page, "所属账户")).toContainText("天天基金", {
      timeout: 30_000
    });

    // 判据 3（续）：建账下发的是 channel_category 而不是 ledger_type（#1101）
    const ledgerCall = calls.find(
      c => c.method === "POST" && c.path.startsWith("/api/ledgers")
    );
    expect(ledgerCall, "未发出建账请求").toBeTruthy();
    expect(ledgerCall!.body).toMatchObject({ name: "天天基金" });
    expect(ledgerCall!.body).toHaveProperty("channel_category");
    expect(ledgerCall!.body).not.toHaveProperty("ledger_type");
  });
});
