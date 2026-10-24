import { expect, test, type Page } from "@playwright/test";
import { injectSupabaseSession } from "./support/session";

/**
 * 策略视图回归网（#980 拆分 views/asset/strategies/index.vue）。
 *
 * 这页此前没有任何 e2e，拆分把「分组 / 组内分页 / 标签增删」搬进了子组件与 composable。
 * 最容易静默坏掉的是三件事：
 *
 * 1. **一只持仓带多个标签会出现在多个组里**（多对多）。若哪个环节把它当互斥分区
 *    （比如按标签去重），用户会看到「明明有两个标签，却只在一个组里」。
 * 2. **组内页码是子组件本地状态**：同一个页面里多个分组各翻各的页，互不影响。
 * 3. **勾选标签是双向 diff**：勾上要绑定、取消要解绑；两个方向都不能被吞。
 */

const TAGS = [
  { id: 1, name: "价值" },
  { id: 2, name: "成长" }
];

const HOLDINGS = [
  {
    id: 101,
    symbol: "110011",
    name: "易方达中小盘混合",
    type: "fund",
    type_label: "混合型",
    quantity: 1000,
    current_price: 2,
    avg_price: 1,
    account_name: "支付宝-基金"
  },
  {
    id: 102,
    symbol: "510300",
    name: "沪深300ETF",
    type: "etf",
    type_label: "ETF",
    quantity: 500,
    current_price: 4,
    avg_price: 3,
    account_name: "华泰证券"
  },
  {
    id: 103,
    symbol: "000001",
    name: "华夏成长混合",
    type: "fund",
    type_label: "混合型",
    quantity: 200,
    current_price: 5,
    avg_price: 4,
    account_name: "支付宝-基金"
  }
];

/** 打桩策略概览 + 标签增删改，并记录调用 */
async function stubStrategy(
  page: Page,
  opts: {
    holdings?: unknown[];
    relations?: Record<string, string[]>;
  } = {}
): Promise<{ bindCalls: () => string[]; createBodies: () => unknown[] }> {
  const bindCalls: string[] = [];
  const createBodies: unknown[] = [];
  const holdings = opts.holdings ?? HOLDINGS;
  const relations = opts.relations ?? { 101: ["价值", "成长"], 102: ["价值"] };

  await page.route(/^https?:\/\/[^/]+\/api\//, route =>
    route.fulfill({
      status: 404,
      json: { data: null, message: "e2e 未打桩", error_code: 40400 }
    })
  );

  await page.route(/^https?:\/\/[^/]+\/api\/strategy\/overview\/$/, route =>
    route.fulfill({
      status: 200,
      json: {
        data: { holdings, tags: TAGS, relations },
        message: "ok"
      }
    })
  );

  // 新建标签（POST /api/strategy/）
  await page.route(/^https?:\/\/[^/]+\/api\/strategy\/$/, async route => {
    if (route.request().method() !== "POST") {
      return route.fulfill({ status: 200, json: { data: TAGS } });
    }
    const body = route.request().postDataJSON() as { name: string };
    createBodies.push(body);
    await route.fulfill({
      status: 200,
      json: { data: { id: 99, name: body.name }, message: "ok" }
    });
  });

  // 绑定 / 解绑：POST / DELETE /api/strategy/{tagId}/positions/{positionId}/
  await page.route(
    /^https?:\/\/[^/]+\/api\/strategy\/\d+\/positions\/\d+\/$/,
    async route => {
      const method = route.request().method();
      bindCalls.push(`${method} ${new URL(route.request().url()).pathname}`);
      await route.fulfill({ status: 200, json: { data: null, message: "ok" } });
    }
  );

  return { bindCalls: () => bindCalls, createBodies: () => createBodies };
}

/** 打开策略视图并等首屏 */
async function openPage(page: Page) {
  await page.goto("/#/asset/strategies");
  await expect(page.getByRole("heading", { name: "策略视图" })).toBeVisible({
    timeout: 90_000
  });
}

/** 按分组标题定位分组区块（页面里每个标签一个 el-table） */
function groupOf(page: Page, tag: string) {
  return page.locator(".mb-8").filter({
    has: page.getByRole("heading", { level: 3, name: new RegExp(`^${tag}`) })
  });
}

test.describe("策略视图（#980 拆分）", () => {
  // 冷启动时 vite 首次编译整套依赖可能超过默认 60s
  test.setTimeout(180_000);

  test.beforeEach(async ({ context, baseURL }) => {
    await injectSupabaseSession(context, baseURL!);
  });

  test("分组：多标签持仓出现在多个组里，「未分类」恒排最后，汇总取原始持仓", async ({
    page
  }) => {
    await stubStrategy(page);
    await openPage(page);

    // 汇总卡：3 只持仓 / 2 个标签
    const cards = page.locator(".summary-card");
    await expect(cards).toHaveCount(4);
    await expect(cards.nth(0)).toContainText("3 项");
    await expect(cards.nth(1)).toContainText("2 个");
    // 总市值 = 1000×2 + 500×4 + 200×5 = 5000
    await expect(cards.nth(2)).toContainText("5,000.00");

    // 三个分组：价值 + 成长 + 未分类，且「未分类」恒排最后。
    // 前两组之间的先后由 `localeCompare(zh-Hans)` 决定（成长 cheng < 价值 jia），
    // 那是 ICU 排序细节，不在本用例的断言范围里——只钉「未分类在最后」。
    const headings = page.getByRole("heading", { level: 3 });
    await expect(headings).toHaveCount(3);
    await expect(headings.nth(2)).toContainText("未分类");
    const firstTwo = await headings.allTextContents();
    expect(firstTwo.slice(0, 2).some(t => t.includes("价值"))).toBe(true);
    expect(firstTwo.slice(0, 2).some(t => t.includes("成长"))).toBe(true);

    // 多对多：101 带「价值 + 成长」，两个组里都要有它
    await expect(groupOf(page, "价值").locator(".el-table__row")).toHaveCount(
      2
    );
    await expect(groupOf(page, "成长").locator(".el-table__row")).toHaveCount(
      1
    );
    await expect(groupOf(page, "成长")).toContainText("易方达中小盘混合");
    await expect(groupOf(page, "未分类").locator(".el-table__row")).toHaveCount(
      1
    );
    await expect(groupOf(page, "未分类")).toContainText("华夏成长混合");
  });

  test("组内分页：21 只同标签 ⇒ 两页，翻页只影响本组", async ({ page }) => {
    const many = Array.from({ length: 21 }, (_, i) => ({
      ...HOLDINGS[0],
      id: 200 + i,
      symbol: `1000${i}`,
      name: `价值基金${i}`
    }));
    const relations: Record<string, string[]> = {};
    many.forEach(h => {
      relations[String(h.id)] = ["价值"];
    });
    // 另有一只属于「成长」，用来验证翻页不会串组
    relations["102"] = ["成长"];

    await stubStrategy(page, {
      holdings: [...many, HOLDINGS[1]],
      relations
    });
    await openPage(page);

    const valueGroup = groupOf(page, "价值");
    await expect(valueGroup.locator(".el-table__row")).toHaveCount(20);
    await expect(valueGroup.locator(".el-pagination")).toBeVisible();

    await valueGroup.locator(".el-pager li", { hasText: "2" }).click();
    await expect(valueGroup.locator(".el-table__row")).toHaveCount(1);

    // 另一个组只有 1 行、没有分页器（两组页码互不影响）
    const growthGroup = groupOf(page, "成长");
    await expect(growthGroup.locator(".el-table__row")).toHaveCount(1);
    await expect(growthGroup.locator(".el-pagination")).toHaveCount(0);
  });

  test("标签：勾选触发绑定、取消触发解绑，管理对话框可新建标签", async ({
    page
  }) => {
    const stub = await stubStrategy(page);
    await openPage(page);

    // 价值组第一行（101）已挂「价值 + 成长」，点触发器打开多选面板
    const valueGroup = groupOf(page, "价值");
    const firstRow = valueGroup.locator(".el-table__row").first();
    await firstRow.locator(".tag-trigger").click();

    // 每行都有一个 popover（teleported 到 body，未展开的 aria-hidden=true），
    // 所以必须按「当前可见」筛，否则撞 strict mode
    const popover = page
      .locator(".el-popover:visible")
      .filter({ hasText: "选择标签" });
    await expect(popover).toBeVisible();

    // 取消勾选「成长」⇒ DELETE /api/strategy/2/positions/101/
    // 点 label 而不是原生 input：Element Plus 的 input 是视觉隐藏的，
    // 直接点它 Playwright 会判为 not visible（点 label 才触发 change）
    const growthBox = popover
      .locator(".el-checkbox")
      .filter({ hasText: "成长" });
    await growthBox.click();
    await expect
      .poll(() => stub.bindCalls().length, { timeout: 15_000 })
      .toBe(1);
    expect(stub.bindCalls()[0]).toBe("DELETE /api/strategy/2/positions/101/");

    // 取消成功后，表格里的徽标与勾选框都要跟着变（标签投影回归网）
    await expect(
      firstRow.locator(".el-tag").filter({ hasText: "成长" })
    ).toHaveCount(0);

    // 再勾回来 ⇒ POST 同一个地址
    await growthBox.click();
    await expect
      .poll(() => stub.bindCalls().length, { timeout: 15_000 })
      .toBe(2);
    expect(stub.bindCalls()[1]).toBe("POST /api/strategy/2/positions/101/");

    // 管理标签：新建一个全局标签
    await page.getByRole("button", { name: "管理标签" }).click();
    const dialog = page
      .locator(".el-dialog")
      .filter({ hasText: "管理策略标签" });
    await expect(dialog).toBeVisible();
    await expect(dialog.locator(".el-table__row")).toHaveCount(2);

    await dialog
      .getByPlaceholder("输入新标签名（如：成长、价值）")
      .fill("低波");
    await dialog.getByRole("button", { name: "添加" }).click();

    await expect
      .poll(() => stub.createBodies().length, { timeout: 15_000 })
      .toBe(1);
    expect(stub.createBodies()[0]).toEqual({ name: "低波" });
    // 新建成功后列表多一行
    await expect(dialog.locator(".el-table__row")).toHaveCount(3);
  });
});
