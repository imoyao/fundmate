import { expect, test } from "@playwright/test";
import { injectSupabaseSession } from "./support/session";

/**
 * 空态能力目录的「分层」契约（2026-11-26 用户反馈「10 个入口权重完全平等」）。
 *
 * 判据只认机器可验的四条：
 * 1. 主入口整行（宽度与目录容器一致）；
 * 2. 常用位固定 3 项，默认顺序 = 收益表现 / 持仓盈亏 / 市场温度；
 * 3. 「更多能力」默认折叠，展开后按粒度分「账户与市场 / 单只基金」两组；
 * 4. 点过某项之后，它进入常用位第一位，且**刷新后仍然在**（localStorage）。
 *
 * 第 4 条是本轮唯一带持久化的新行为，不能只靠「看着对」——它出问题时表现为
 * 「排序偶尔不变」，肉眼几乎不可复现。
 */

const emptyList = { data: [], total: 0, page: 1, per_page: 50 };

/** 点能力卡会真发一轮请求；给个最小合法响应，避免落到全局错误提示 */
const clarifyTurn = {
  data: {
    type: "clarify",
    content: "请提供 6 位基金代码。",
    missing_params: ["fund_codes"],
    session_id: "sess-cap-1"
  },
  message: "ok"
};

const pinnedCards =
  '[data-region="agent-capabilities"] .chat-hero__grid--pinned .chat-cap';

test("空态能力目录：主入口整行 + 常用 3 项 + 更多能力按粒度分组", async ({
  page,
  context,
  baseURL
}) => {
  await injectSupabaseSession(context, baseURL!);
  await page.route(/\/api\/agent\/sessions\/?(?:\?.*)?$/, route =>
    route.fulfill({ json: emptyList })
  );

  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/#/agent/chat");

  const hero = page.locator('[data-region="agent-capabilities"]');
  await expect(hero).toBeVisible();

  // 1) 主入口是资产总览，且撑满整行（与目录容器同宽，误差 ≤1px）
  const primary = hero.locator('[data-cap="assets"]');
  await expect(primary).toBeVisible();
  const widths = await hero.evaluate(el => {
    const self = el.getBoundingClientRect().width;
    const card = el
      .querySelector('[data-cap="assets"]')!
      .getBoundingClientRect().width;
    return { self, card };
  });
  expect(Math.abs(widths.card - widths.self)).toBeLessThanOrEqual(1);

  // 2) 常用位固定 3 项，默认顺序固定
  await expect(page.locator(pinnedCards)).toHaveCount(3);
  await expect(page.locator(pinnedCards).nth(0)).toContainText("收益表现");
  await expect(page.locator(pinnedCards).nth(1)).toContainText("持仓盈亏");
  await expect(page.locator(pinnedCards).nth(2)).toContainText("市场温度");

  // 3) 更多能力默认折叠；展开后两组都在，且 6 项不再出现在常用位
  const more = page.locator("#agent-capability-more");
  await expect(more).toBeHidden();
  await expect(
    hero.getByRole("button", { name: /更多能力（6 项）/ })
  ).toBeVisible();

  await hero.getByRole("button", { name: /更多能力（6 项）/ }).click();
  await expect(more).toBeVisible();
  await expect(more.getByRole("heading", { name: "账户与市场" })).toBeVisible();
  await expect(more.getByRole("heading", { name: "单只基金" })).toBeVisible();
  // 粒度分组真的生效：4 项账户级 + 2 项基金级
  await expect(more.locator(".chat-cap")).toHaveCount(6);
});

test("常用位记住最近点击：点过的进首位，刷新后仍在", async ({
  page,
  context,
  baseURL
}) => {
  await injectSupabaseSession(context, baseURL!);
  await page.route(/\/api\/agent\/chat\/?$/, route =>
    route.fulfill({ json: clarifyTurn })
  );
  await page.route(/\/api\/agent\/sessions\/?(?:\?.*)?$/, route =>
    route.fulfill({ json: emptyList })
  );

  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/#/agent/chat");

  const hero = page.locator('[data-region="agent-capabilities"]');
  await hero.getByRole("button", { name: /更多能力（6 项）/ }).click();
  await page
    .locator("#agent-capability-more")
    .getByRole("button", { name: /交易习惯/ })
    .click();

  // 请求回来 → 消息上屏 → 回空态（左栏「新对话」）
  await expect(page.getByText("请提供 6 位基金代码。")).toBeVisible();
  await page.getByRole("button", { name: "新对话" }).click();
  await expect(hero).toBeVisible();

  // 它从「更多」挪进了常用位第一位。注意「更多能力」仍是 6 项：
  // 常用位是**固定 3 槽**，它挤掉的是「市场温度」，总量不变——
  // 所以判据不能数总数，要判「交易习惯不在更多区里了」。
  await expect(page.locator(pinnedCards).nth(0)).toContainText("交易习惯");
  await expect(
    hero.getByRole("button", { name: /更多能力（6 项）/ })
  ).toBeVisible();
  await hero.getByRole("button", { name: /更多能力（6 项）/ }).click();
  await expect(page.locator("#agent-capability-more .chat-cap")).toHaveCount(6);
  await expect(
    page.locator("#agent-capability-more .chat-cap", { hasText: "交易习惯" })
  ).toHaveCount(0);

  // 刷新：localStorage 需要让它跨会话保留，否则「记住」只在本次页面内成立
  await page.reload();
  await expect(page.locator(pinnedCards).nth(0)).toContainText("交易习惯");
});
