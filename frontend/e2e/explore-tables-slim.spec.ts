import { expect, test, type Page } from "@playwright/test";
import { injectSupabaseSession } from "./support/session";

/**
 * #980 批 B5 回归网：拥挤度表格拆分后的接线。
 *
 * 钉三件事（都在下面两个用例里）：
 * 1. **三类单元格**（分值+条 / 双数字 / 百万大单）拆成子组件后，单元格内容不变；
 * 2. **归一化**：拆出 `CrowdingMetricCell` 后条宽由 `crowdingBarStyle` 单独决定，
 *    满值必须是整条（分母就是它自己）；
 * 3. **缺数据不许画成 0%**：外部源不可用时后端整行 `null`，此时值显示 `--`、条宽为 0。
 *    写错的后果是静默的——表里出现 `0.0%` 和满格条，用户会读成「这个行业一点不拥挤」。
 *
 * ⚠️ 数据源的键名不是 `crowding`：页面按分类分别取 `industry_crowding`（申万行业）
 * 与 `track_crowding`（热门赛道）。初版只 match 了 `crowding`，桩一次都没命中，
 * 表格静默为空而页面不报错。
 */
const MULTI_URL =
  /\/api\/temperature\/multi\?source=(industry_crowding|track_crowding)/;

type CrowdingItem = {
  item_type: string;
  item_code: string;
  item_name: string;
  data: Record<string, number | null>;
  stale?: boolean;
};

function item(
  code: string,
  name: string,
  data: Record<string, number | null>
): CrowdingItem {
  return { item_type: "sw", item_code: code, item_name: name, data };
}

/** 两行：一行满值（100 / 50 / 0），一行全缺数据（后端外部源不可用时的真实形态） */
const FULL = item("801010", "行业甲", {
  crowding_pct: 100,
  amount_pct_rank: 50,
  turnover_rank: 0,
  ma60_ratio: 40,
  ma60_ratio_pct: 60,
  high60_ratio: 12.34,
  high60_ratio_pct: 30,
  margin_ratio: 2.5,
  margin_ratio_pct: 70,
  big_order: 2.34,
  bias6: 1.2,
  bias20: -0.4,
  bias60: 3.5
});

const EMPTY = item("801020", "行业乙", {
  crowding_pct: null,
  amount_pct_rank: null,
  turnover_rank: null,
  ma60_ratio: null,
  ma60_ratio_pct: null,
  high60_ratio: null,
  high60_ratio_pct: null,
  margin_ratio: null,
  margin_ratio_pct: null,
  big_order: null,
  bias6: null,
  bias20: null,
  bias60: null
});

async function mockCrowding(page: Page, items: CrowdingItem[]) {
  // 兜底最宽，最先注册（Playwright **后注册先匹配**）
  await page.route(/^https?:\/\/[^/]+\/api\//, route =>
    route.fulfill({ status: 404, json: { data: null, message: "e2e 未打桩" } })
  );
  await page.route(MULTI_URL, route =>
    route.fulfill({
      json: {
        data: {
          source: "industry_crowding",
          date: "2026-10-27",
          stale: false,
          items
        },
        message: ""
      }
    })
  );
}

test.describe("拥挤度表格拆分后回归（#980 批 B5）", () => {
  test.setTimeout(180_000);

  test.beforeEach(async ({ context, baseURL }) => {
    await injectSupabaseSession(context, baseURL!);
  });

  test("单元格：满值归一为整条、缺数据显示 -- 且条宽为 0", async ({ page }) => {
    await mockCrowding(page, [FULL, EMPTY]);
    await page.goto("/#/explore?view=detail");

    const section = page.locator(".crowding-section");
    await expect(section).toBeVisible({ timeout: 90_000 });
    // embedded 模式不该自带标题行（外壳由父级卡片提供）
    await expect(section.locator(".section-header")).toHaveCount(0);

    const full = section.locator(".el-table__row", { hasText: "行业甲" });
    await expect(full.locator(".crowding-value")).toHaveText([
      "100.0%",
      "50.0%",
      "0.0%"
    ]);
    // 满值那条条宽 100%（归一化的分母就是它自己）
    await expect(full.locator(".crowding-cell-fill").first()).toHaveAttribute(
      "style",
      /width:\s*100%/
    );
    // 双数字列：当期值 40.0%，历史分位 60.0%
    await expect(full.locator(".dim-cell").first()).toContainText("40.0%");
    await expect(full.locator(".dim-cell").first()).toContainText("60.0%");
    // 百万大单带正号与亿
    await expect(full).toContainText("+2.3亿");

    const empty = section.locator(".el-table__row", { hasText: "行业乙" });
    await expect(empty.locator(".crowding-value")).toHaveText([
      "--",
      "--",
      "--"
    ]);
    // 缺数据不许画成 0%：条宽必须为 0，且文案里不能出现 0.0%
    await expect(empty.locator(".crowding-cell-fill").first()).toHaveAttribute(
      "style",
      /width:\s*0%/
    );
    await expect(empty).not.toContainText("0.0%");
  });

  test("空表：给「稍后自动恢复」的说明句，不空白也不报错", async ({ page }) => {
    await mockCrowding(page, []);
    await page.goto("/#/explore?view=detail");

    const section = page.locator(".crowding-section");
    await expect(section).toBeVisible({ timeout: 90_000 });
    await expect(section.locator(".empty-state")).toHaveText(
      "暂无数据，稍后自动恢复；不影响页面其它部分。"
    );
    await expect(section.locator(".el-table__row")).toHaveCount(0);
  });
});
