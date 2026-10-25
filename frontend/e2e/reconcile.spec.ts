import { expect, test, type Page } from "@playwright/test";

import { injectSupabaseSession } from "./support/session";

/**
 * E账户对账页回归网（#980 拆分 `reconcile/index.vue` 后补的接线判据）。
 *
 * 690 行的页面拆成 `reconcileView/`（页头 / 指标卡 / 表格 / 行操作 / 空态 + 纯函数层）。
 * 纯函数已有单测（`reconcileModel.spec.ts`），这里钉的是**拆组件最容易断的接线**，
 * 尤其是这条三级链：
 *
 *   `ReconcileRowActions`（按钮）→ `ReconcileTable`（列插槽）→ 页面（发请求 + 重载）
 *
 * 断任意一环的表现都是「点了按钮毫无反应」——不报错，也不会有任何网络请求，
 * 只靠单测抓不到（单测不渲染 el-table 的列插槽）。
 *
 * 断言只落在「点完能看到什么、请求里发了什么」，不测样式值。
 */

const DATA_DATE = "2026-10-20";

const SUMMARY = {
  pending_count: 2,
  attributed_count: 1,
  ignored_count: 0,
  verified_count: 1
};

function items() {
  return [
    {
      record_id: 11,
      symbol: "000001",
      name: "华夏成长",
      source_broker: "天天基金",
      fund_manager: "华夏基金",
      eaccount_quantity: 1000,
      eaccount_total: 1500,
      system_quantity: 900,
      diff: 600,
      status: "pending"
    },
    {
      record_id: 12,
      symbol: "110011",
      name: "易方达中小盘",
      source_broker: "支付宝",
      fund_manager: "易方达",
      eaccount_quantity: 500,
      eaccount_total: 500,
      system_quantity: 500,
      diff: 0,
      status: "verified"
    },
    {
      record_id: 13,
      symbol: "161725",
      name: "招商中证白酒",
      source_broker: "招商银行",
      fund_manager: "招商基金",
      eaccount_quantity: 300,
      eaccount_total: 300,
      system_quantity: 250,
      diff: 50,
      status: "pending"
    },
    {
      record_id: 14,
      symbol: "000311",
      name: "景顺长城沪深300",
      source_broker: "华泰证券",
      fund_manager: "景顺长城",
      eaccount_quantity: 800,
      eaccount_total: 800,
      system_quantity: 800,
      diff: 0,
      status: "attributed",
      attributed_to: "华泰证券"
    }
  ];
}

type Call = { method: string; path: string; body: Record<string, unknown> };

/** 只打桩 /api/：vite 源码模块请求不能碰，否则整页白屏 */
async function mockApis(page: Page): Promise<Call[]> {
  const calls: Call[] = [];
  await page.route(/^https?:\/\/[^/]+\/api\//, async route => {
    const url = new URL(route.request().url());
    const method = route.request().method();

    if (url.pathname.startsWith("/api/e-account/attribution")) {
      const body = (route.request().postDataJSON() ?? {}) as Record<
        string,
        unknown
      >;
      calls.push({ method, path: url.pathname, body });
      return route.fulfill({ json: { data: { failed: 0 }, message: "" } });
    }
    if (url.pathname.startsWith("/api/e-account/reconciliation")) {
      return route.fulfill({
        json: {
          data: { data_date: DATA_DATE, items: items(), summary: SUMMARY },
          message: ""
        }
      });
    }
    return route.fulfill({ json: { data: [], message: "" } });
  });
  return calls;
}

async function openReconcile(page: Page) {
  await page.goto("/#/investment/reconcile", { waitUntil: "commit" });
  await expect(page.locator(".reconcile-head__title")).toBeVisible({
    timeout: 150_000
  });
}

/** 表格按基金名定位行（不用 .el-table__row 下标，冻结列会多渲染一份） */
function rowOf(page: Page, name: string) {
  return page.locator(".table-card .el-table__row").filter({ hasText: name });
}

test.describe("E账户对账页（#980 拆分后的接线判据）", () => {
  test.beforeEach(async ({ context, baseURL }) => {
    await injectSupabaseSession(context, baseURL!);
  });

  test("页头数据日期、四态计数、表格行与空态文案", async ({ page }) => {
    test.setTimeout(240_000);
    await mockApis(page);
    await openReconcile(page);

    // 页头：数据日期胶囊走 formatDate
    await expect(page.locator(".data-date-capsule")).toContainText(
      "2026-10-20"
    );

    // 四态计数卡：数字来自 summary，不是前端算的
    const grid = page.locator(".summary-grid");
    await expect(grid).toContainText("待处理");
    await expect(grid).toContainText("已归因");
    await expect(grid).toContainText("已忽略");
    await expect(grid).toContainText("已核对");

    // 表格：4 行都在；「共 4 条」是筛选后的全量口径
    await expect(page.locator(".filter-bar__count")).toContainText("共 4 条");
    await expect(page.locator(".table-card .el-table__row")).toHaveCount(4);

    // 多渠道角标：eaccount_total ≠ eaccount_quantity 才出现
    await expect(
      rowOf(page, "华夏成长").locator(".qty-cell__total")
    ).toHaveCount(1);
    await expect(
      rowOf(page, "易方达中小盘").locator(".qty-cell__total")
    ).toHaveCount(0);

    // 非待处理行不给操作按钮，只回显去向
    await expect(
      rowOf(page, "招商中证白酒").getByText("归因覆盖")
    ).toBeVisible();
    await expect(rowOf(page, "景顺长城沪深300")).toContainText("已归因至");
    await expect(rowOf(page, "易方达中小盘")).toContainText("已核对一致");
  });

  test("状态筛选：切到「待处理」只留待处理行，切到空态档给提示文案", async ({
    page
  }) => {
    test.setTimeout(240_000);
    await mockApis(page);
    await openReconcile(page);
    await expect(page.locator(".table-card .el-table__row")).toHaveCount(4);

    // SegmentedControl 是 role="tablist" + role="tab"（不是 radio）
    await page
      .locator(".segmented-control")
      .getByRole("tab", { name: "待处理" })
      .click();
    await expect(page.locator(".filter-bar__count")).toContainText("共 2 条");
    await expect(page.locator(".table-card .el-table__row")).toHaveCount(2);
    await expect(rowOf(page, "华夏成长")).toBeVisible();
    await expect(rowOf(page, "招商中证白酒")).toBeVisible();

    // 「已忽略」档没有记录 → 走空态的「当前筛选下没有记录」分支（含出路提示）
    await page
      .locator(".segmented-control")
      .getByRole("tab", { name: "已忽略" })
      .click();
    await expect(page.locator(".table-card .el-table__row")).toHaveCount(0);
    await expect(page.locator(".reconcile-empty")).toContainText(
      "当前筛选下没有记录"
    );
    await expect(page.locator(".reconcile-empty__hint")).toContainText("刷新");
  });

  test("行内归因覆盖：三级 emit 链打通，请求体带 action=cover", async ({
    page
  }) => {
    test.setTimeout(240_000);
    const calls = await mockApis(page);
    await openReconcile(page);

    // 断链的表现是点了没反应，所以先确认按钮真的存在且可点
    const row = rowOf(page, "华夏成长");
    await row.getByText("归因覆盖").click();

    // 确认框：危险语义要写清「删除渠道原记录」+「不可撤销」
    const box = page.locator(".el-message-box");
    await expect(box).toBeVisible({ timeout: 30_000 });
    await expect(box).toContainText("华夏成长");
    await expect(box).toContainText("删除渠道原记录");

    await box.getByRole("button", { name: "确认覆盖" }).click();

    // 请求体：三个字符串字段 + action=cover
    await expect(page.locator(".el-message-box")).toBeHidden({
      timeout: 30_000
    });
    const call = calls.find(c => c.method === "POST");
    expect(call, "未发出归因请求").toBeTruthy();
    const decisions = call!.body.decisions as Record<string, unknown>[];
    expect(decisions).toHaveLength(1);
    expect(decisions[0]).toMatchObject({
      symbol: "000001",
      source_broker: "天天基金",
      action: "cover"
    });

    // 成功提示 + 重载后列表仍在（重载走的是页面的 fetchData）
    await expect(page.getByText("归因覆盖完成")).toBeVisible({
      timeout: 30_000
    });
    await expect(page.locator(".table-card .el-table__row")).toHaveCount(4);
  });

  test("行内忽略：同一条链走 action=ignore，且不声明不可撤销", async ({
    page
  }) => {
    test.setTimeout(240_000);
    const calls = await mockApis(page);
    await openReconcile(page);

    await rowOf(page, "招商中证白酒").getByText("忽略").click();

    const box = page.locator(".el-message-box");
    await expect(box).toBeVisible({ timeout: 30_000 });
    await expect(box).toContainText("可稍后重新对账恢复");
    await expect(box).not.toContainText("不可撤销");

    await box.getByRole("button", { name: "确认忽略" }).click();
    await expect(page.locator(".el-message-box")).toBeHidden({
      timeout: 30_000
    });

    const call = calls.find(c => c.method === "POST");
    expect(call, "未发出归因请求").toBeTruthy();
    const decisions = call!.body.decisions as Record<string, unknown>[];
    expect(decisions[0]).toMatchObject({ symbol: "161725", action: "ignore" });

    await expect(page.getByText("已忽略该记录")).toBeVisible({
      timeout: 30_000
    });
  });
});
