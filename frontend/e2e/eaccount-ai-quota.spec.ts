import { expect, test } from "@playwright/test";

import { injectSupabaseSession } from "./support/session";

/**
 * #1695 回归网：E账户导入 AI 面板的额度展示与按钮状态必须与接口一致。
 *
 * 修复前本用例必红——两处曾同时存在的缺陷：
 * 1. `aiQuota = limit || 10` 把配额耗尽的合法 0 吞成 10 → 显示「10 / 10」、按钮不禁用；
 * 2. `fetchAiUsage` 读后端没有的 `d.count`（后端字段是 used，见 usage/views.py）→
 *    used=undefined → aiRemaining 恒 NaN → 线上真实显示「NaN / 30 次」（2026-09-25 实测）。
 *
 * 为什么是 E2E 而非单测：本仓无前端单测框架（落地方式决策见 #1695 评论）；额度消费是
 * 「接口 → computed → 模板 → 按钮 disabled」的完整链路，page.route 打桩即可端到端覆盖，
 * 且不依赖后端（docs/dev/frontend-e2e.md §7：依赖后端数据的场景用 page.route 打桩）。
 */

/** 后端 GET /api/usage/<feature>/ 的真实成功形态（信封结构，见 usage/views.py get_usage） */
function usageBody(used: number, quota: number): string {
  return JSON.stringify({
    data: {
      feature: "holding_import",
      period_date: new Date().toISOString().slice(0, 10),
      used,
      quota,
      remaining: Math.max(0, quota - used)
    },
    message: "ok"
  });
}

/** 面板两个关键选择器（结构见 EaccountAiPanel.vue） */
const USAGE_COUNT = ".ai-import-panel__usage-count";
const USAGE_LINE = ".ai-import-panel__usage";
const SUBMIT_BTN = ".ai-import-panel__submit";

test.describe("E账户导入 AI 额度（#1695：limit=0 不被 || 吞、used 不读成 count）", () => {
  test("配额耗尽（quota=0）：显示 0/0，填入文本后「开始识别」仍禁用", async ({
    context,
    page,
    baseURL
  }) => {
    await injectSupabaseSession(context, baseURL!);

    // 打桩当日额度耗尽（count:0/used:0 + quota:0），不依赖后端
    let usageHits = 0;
    await page.route("**/api/usage/**", route => {
      usageHits += 1;
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: usageBody(0, 0)
      });
    });

    await page.goto("/#/investment/eaccount-import");
    // 切到 AI 模式才会拉取额度（switchMode → fetchAiUsage）；入口是 tablist 里的 role="tab"
    await page.getByRole("tab", { name: /AI 识别持仓/ }).click();

    const count = page.locator(USAGE_COUNT);
    await expect(count).toBeVisible();
    // 打桩路径确实被走到（防「根本没发请求」造成的假绿）
    expect(usageHits).toBeGreaterThan(0);
    // 核心断言 1：剩余显示 0——修复前 || 吞 0 显示 10、count 错配显示 NaN
    await expect(count).toHaveText("0");
    await expect(page.locator(USAGE_LINE)).toContainText("/ 0 次");

    // 核心断言 2：canAiRecognize 已满足（填入文本），此时按钮只能因额度耗尽而禁用
    await page
      .getByPlaceholder("在此粘贴持仓文本")
      .fill("110011 易方达中小盘 份额4526.51 市值5000");
    await expect(page.locator(SUBMIT_BTN)).toBeDisabled();
  });

  test("配额充足（used=5/quota=30）：显示 25/30 且按钮可用（防过度禁用）", async ({
    context,
    page,
    baseURL
  }) => {
    await injectSupabaseSession(context, baseURL!);

    await page.route("**/api/usage/**", route =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: usageBody(5, 30)
      })
    );

    await page.goto("/#/investment/eaccount-import");
    await page.getByRole("tab", { name: /AI 识别持仓/ }).click();

    // 核心断言：正确读 used → 30-5=25——修复前 d.count=undefined 显示 NaN（本条即抓出线上缺陷的回归网）
    await expect(page.locator(USAGE_COUNT)).toHaveText("25");
    await expect(page.locator(USAGE_LINE)).toContainText("/ 30 次");

    await page
      .getByPlaceholder("在此粘贴持仓文本")
      .fill("110011 易方达中小盘 份额4526.51 市值5000");
    await expect(page.locator(SUBMIT_BTN)).toBeEnabled();
  });
});
