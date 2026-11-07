import { expect, test, type Page } from "@playwright/test";

import type { DiscrepancyItem } from "../src/api/reconciliation";
import { injectSupabaseSession } from "./support/session";

/**
 * 对账中心第二轮（用户视角细节）实机回归网。
 *
 * 钉的都是「读起来像不像给人用的」这类单测抓不到的事：
 *   ① 队列 12 条只渲染 10 条 + 分页器，翻页不重挂载、不写 URL；
 *   ② 点一条待办打开右侧抽屉，首屏能看见产品名 / 账本 / 差额 / 投资轨迹；
 *   ③ 差异表列名、口径说明、补录弹窗标题与上下文：不许再出现
 *      「理论 / 实际 / 类型 / 孤儿 / 就地补充 / 设定持仓 / 裸 cash」。
 *
 * ⚠️ 桩注册顺序 = 后注册先匹配（与 reconcile-workbench-head.spec.ts 同一条坑）：
 * 最宽的 `/api/` 兜底必须最先注册，具体接口随后逐个覆盖。
 */

const LEDGER_NAME = "主账本";

/**
 * 返回类型直接标成后端契约 `DiscrepancyItem`，不另写一份 interface——
 * 契约加必填字段时本文件不改就类型报错，桩不会悄悄落后于真实出参。
 */
/** 12 条 > 每页 10 条；第 1 条带产品名，第 3 条是 special symbol，第 4 条是 orphan */
const ROWS: DiscrepancyItem[] = Array.from({ length: 12 }, (_, i) => ({
  id: i + 1,
  domain: "B",
  ledger_id: 1,
  symbol: i === 2 ? "cash" : `60${String(i + 1).padStart(4, "0")}`,
  display_name: i === 0 ? "贵州茅台" : "",
  discrepancy_type: i === 3 ? "orphan" : "quantity",
  expected_value: 100,
  actual_value: 98,
  diff: -2,
  status: "pending",
  is_permanent: false,
  first_detected_at: "2026-11-01T08:00:00",
  updated_at: null
}));

const TXN_ROWS = [
  {
    id: 901,
    txn_type: "buy",
    trade_date: "2026-10-20",
    confirm_date: "2026-10-21",
    symbol: "600001",
    position_name: "贵州茅台",
    account_name: LEDGER_NAME,
    ledger_id: 1,
    position_id: 7,
    position_state: "held",
    quantity: 100,
    price: 170,
    amount: 17000,
    fee: 5
  },
  {
    id: 902,
    txn_type: "sell",
    trade_date: "2026-10-28",
    confirm_date: "2026-10-29",
    symbol: "600001",
    position_name: "贵州茅台",
    account_name: LEDGER_NAME,
    ledger_id: 1,
    position_id: 7,
    position_state: "held",
    quantity: 2,
    price: 175,
    amount: 350,
    fee: 1
  }
];

interface Call {
  method: string;
  path: string;
  body: unknown;
}

async function stubApis(page: Page): Promise<Call[]> {
  const calls: Call[] = [];
  page.on("pageerror", err => pageErrors.push(err.message));
  page.on("request", req => {
    const url = new URL(req.url());
    if (!url.pathname.startsWith("/api/")) return;
    let body: unknown = null;
    try {
      body = req.postDataJSON();
    } catch {
      body = req.postData();
    }
    calls.push({ method: req.method(), path: url.pathname, body });
  });

  // 兜底（最宽，最先注册）
  await page.route(
    url => url.pathname.startsWith("/api/"),
    route => route.fulfill({ json: { data: [], message: "" } })
  );

  await page.route(
    url => url.pathname.startsWith("/api/reconciliation/discrepancies"),
    route => route.fulfill({ json: { data: ROWS, message: "" } })
  );

  await page.route(
    url => url.pathname.startsWith("/api/e-account/reconciliation"),
    route =>
      route.fulfill({
        json: {
          data: {
            data_date: "2026-10-20",
            items: [],
            summary: {
              pending_count: 0,
              attributed_count: 0,
              ignored_count: 0,
              verified_count: 0
            }
          },
          message: ""
        }
      })
  );

  await page.route(
    url => url.pathname.startsWith("/api/reconciliation/ghost-duplicates"),
    route =>
      route.fulfill({
        json: { data: { groups: [], ignored_count: 0 }, message: "" }
      })
  );

  // 已忽略清单必须单独给数组：宽桩的 {groups:[], ignored_count:0} 被当成数组
  // 写进 ghostIgnored，会让 buildReconQueue 的 for...of 抛错、Vue 把 DOM 冻在加载态
  // （既不白屏也不报错，是最难查的一类假象）。窄桩后注册 ⇒ 优先级更高。
  await page.route(
    url =>
      url.pathname.startsWith("/api/reconciliation/ghost-duplicates/ignored"),
    route => route.fulfill({ json: { data: [], message: "" } })
  );

  await page.route(
    url => url.pathname.startsWith("/api/reconciliation/dividend-tax"),
    route => route.fulfill({ json: { data: [], message: "" } })
  );

  await page.route(
    url => url.pathname === "/api/ledgers/",
    route =>
      route.fulfill({
        json: { data: [{ id: 1, name: LEDGER_NAME }], message: "" }
      })
  );

  // 账本流水（比 /api/ledgers/ 更具体，后注册先匹配）
  await page.route(
    url => /\/api\/ledgers\/\d+\/transactions\/$/.test(url.pathname),
    route =>
      route.fulfill({
        json: {
          data: { items: TXN_ROWS, total: TXN_ROWS.length },
          message: ""
        }
      })
  );

  // 未按账本查时走的全局流水
  await page.route(
    url => url.pathname.startsWith("/api/transactions"),
    route =>
      route.fulfill({
        json: {
          data: TXN_ROWS,
          total: TXN_ROWS.length,
          page: 1,
          per_page: 50,
          message: ""
        }
      })
  );

  return calls;
}

async function openWorkbench(page: Page, query = ""): Promise<void> {
  await page.goto(`/#/investment/reconcile-workbench${query}`, {
    waitUntil: "commit"
  });
  await expect(page.locator(".workbench-head__title")).toBeVisible({
    timeout: 150_000
  });
  // 首屏七个 loader 全回来才渲染列表；冷启动（vite 现做依赖预构建）可能远慢于
  // 默认 15s，给足时间，别把「构建慢」误记成「页面没渲染」。
  await expect(page.locator(".recon-queue__item").first()).toBeVisible({
    timeout: 60_000
  });
}

let pageErrors: string[] = [];

test.describe("对账中心第二轮：抽屉 / 分页 / 用户语言", () => {
  test.setTimeout(240_000);

  test.beforeEach(async ({ context, baseURL }) => {
    await injectSupabaseSession(context, baseURL!);
    pageErrors = [];
  });

  // Vue 对渲染错误很「包容」：computed 抛错只留 warn，DOM 冻在末次成功渲染
  // （加载态），既没白屏也没崩。只断言「元素存在」会漏掉这类假象，故每条用例
  // 都额外钉一次「零未捕获异常」。
  test.afterEach(() => {
    expect(pageErrors).toEqual([]);
  });

  test("12 条待办只渲染 10 条，翻页不重挂载、不写 URL", async ({ page }) => {
    await stubApis(page);
    await openWorkbench(page);

    const items = page.locator(".recon-queue__item");
    await expect(items).toHaveCount(10);
    await expect(page.locator(".recon-pagination")).toBeVisible();
    // 12 条差异 + 1 条「导入交割单」入口动作 = 13 项（入口也算一件待办）
    await expect(page.locator(".recon-pagination")).toContainText("共 13 条");

    await page
      .locator(".workbench-head")
      .evaluate(el => el.setAttribute("data-mount-probe", "kept"));
    const firstTitle = await items
      .first()
      .locator(".recon-queue__title")
      .innerText();

    await page
      .locator(".recon-pagination .el-pager li", { hasText: "2" })
      .click();
    await expect(items).toHaveCount(3);
    const secondPageTitle = await items
      .first()
      .locator(".recon-queue__title")
      .innerText();
    expect(secondPageTitle).not.toBe(firstTitle);

    await expect(
      page.locator('.workbench-head[data-mount-probe="kept"]')
    ).toHaveCount(1);
    expect(new URL(page.url()).hash).not.toContain("domain=");
  });

  test("队列不露存储术语：产品名优先、cash 翻成现金、零「孤儿」", async ({
    page
  }) => {
    await stubApis(page);
    await openWorkbench(page);

    const queue = page.locator(".recon-queue");
    await expect(queue).toContainText("贵州茅台");
    await expect(queue).toContainText("现金");
    await expect(queue).toContainText("这不是一只产品");
    await expect(queue).not.toContainText("cash");
    await expect(queue).not.toContainText("孤儿");
    await expect(queue).toContainText("有持仓、缺流水");
  });

  test("点开待办：右侧抽屉给出产品、账本、差额与投资轨迹", async ({ page }) => {
    await stubApis(page);
    await openWorkbench(page);

    await expect(page.locator(".recon-detail-drawer")).toBeHidden();
    await page.locator(".recon-queue__title").first().click();

    const drawer = page.locator(".recon-detail-drawer");
    await expect(drawer).toBeVisible();
    await expect(drawer.locator(".recon-context__title")).toContainText(
      "贵州茅台"
    );
    await expect(drawer.locator(".recon-context")).toContainText(LEDGER_NAME);
    await expect(drawer.locator(".recon-context")).toContainText("按流水算");
    await expect(drawer.locator(".recon-context")).toContainText("差多少");

    const trail = drawer.locator(".recon-trail");
    await expect(trail).toContainText("这个产品的投资轨迹");
    await expect(trail.locator(".recon-trail__hint")).toContainText(
      LEDGER_NAME
    );
    await expect(trail.locator(".recon-trail__hint")).toContainText(
      "最近 2 笔交易"
    );
    await expect(trail.locator(".recon-trail__tip")).toContainText(
      "对照上面的买卖记录"
    );
  });

  test("差异表说人话，补录弹窗带上下文且不再叫「设定持仓」", async ({
    page
  }) => {
    await stubApis(page);
    await openWorkbench(page, "?domain=B");

    const drawer = page.locator(".recon-detail-drawer");
    await expect(drawer).toBeVisible();
    await expect(drawer.locator(".disc-caliber")).toContainText("按流水算");

    const header = drawer.locator(".disc-table .el-table__header");
    for (const label of ["产品", "问题", "按流水算", "账上记的", "差多少"]) {
      await expect(header).toContainText(label);
    }
    await expect(header).not.toContainText("理论");
    await expect(header).not.toContainText("类型");

    await drawer
      .locator(".disc-table tbody tr")
      .first()
      .getByRole("button", { name: "补录这笔" })
      .click();

    const dialog = page.locator(".el-dialog");
    await expect(dialog.locator(".el-dialog__title")).toContainText(
      "补录这笔 · 贵州茅台"
    );
    await expect(dialog.locator(".recon-supplement-context")).toContainText(
      LEDGER_NAME
    );
    await expect(dialog.locator(".recon-supplement-context")).toContainText(
      "按流水算"
    );
    await expect(dialog).toContainText("把持仓改成");
    await expect(dialog).not.toContainText("设定持仓");
    await expect(dialog).not.toContainText("就地补充");
    await expect(dialog).not.toContainText("请填写");
  });

  test("「把持仓改成」是覆盖式 SET：先二次确认，载荷不带 op_type", async ({
    page
  }) => {
    const calls = await stubApis(page);
    await openWorkbench(page, "?domain=B");

    const drawer = page.locator(".recon-detail-drawer");
    await expect(drawer).toBeVisible();
    await drawer
      .locator(".disc-table tbody tr")
      .first()
      .getByRole("button", { name: "补录这笔" })
      .click();

    const dialog = page.locator(".el-dialog.recon-supplement");
    await dialog.getByRole("tab", { name: "把持仓改成" }).click();
    await expect(dialog).toContainText("改完不会新增买卖记录");

    const numbers = dialog.locator(".el-input-number input");
    await numbers.nth(0).fill("120");
    await numbers.nth(0).press("Tab");
    await numbers.nth(1).fill("1.2345");
    await numbers.nth(1).press("Tab");

    const posted = () =>
      calls.filter(
        c =>
          c.method === "POST" &&
          c.path.startsWith("/api/reconciliation/adjustments")
      );

    await dialog.getByRole("button", { name: "改成这个持仓" }).click();
    const confirmBox = page.locator(".el-message-box");
    await expect(confirmBox).toContainText("确认改成这个持仓");
    await expect(confirmBox).toContainText("120 份");
    await confirmBox.getByRole("button", { name: "再看看" }).click();
    expect(posted()).toHaveLength(0);

    await dialog.getByRole("button", { name: "改成这个持仓" }).click();
    await page
      .locator(".el-message-box")
      .getByRole("button", { name: "确认修改" })
      .click();
    await expect.poll(() => posted().length).toBe(1);

    const payload = posted()[0].body as Record<string, unknown>;
    expect(payload).toMatchObject({
      kind: "set",
      symbol: "600001",
      name: "贵州茅台",
      ledger_id: 1,
      quantity: 120,
      avg_price: 1.2345
    });
    // set 走 upsert_from_holding（覆盖锚点），不是补一笔流水
    expect(payload).not.toHaveProperty("op_type");
    expect(payload).not.toHaveProperty("confirm_date");
    expect(payload).toHaveProperty("snapshot_date");
  });
});
