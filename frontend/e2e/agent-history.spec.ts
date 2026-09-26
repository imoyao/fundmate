import { expect, test } from "@playwright/test";
import { injectSupabaseSession } from "./support/session";

/**
 * 历史会话栏（#1719，方案 A 页内折叠）。
 *
 * 与 agent-chat.spec.ts 同因 mock：本仓 E2E 取舍是「不依赖后端」（见
 * playwright.config.ts）。这里验证**前端**接线——默认折叠不发请求、展开可见、
 * 点击回放、新对话复位；端点真实行为由 backend/tests/domains/test_agent_sessions.py 覆盖。
 */

/** 列表信封：分页家规 {data,total,page,per_page}；preview 故意避开示例问题文案，避免定位歧义 */
const listEnvelope = {
  data: [
    {
      session_id: "sess-hist-1",
      goal: "分析账户收益",
      preview: "核对白酒持仓成本与浮亏",
      turn_count: 2,
      created_at: "2026-09-26T10:00:00+08:00",
      updated_at: "2026-09-26T10:05:00+08:00"
    },
    {
      session_id: "sess-hist-2",
      goal: "分析账户收益",
      preview: "9 月定投扣款是否到账",
      turn_count: 1,
      created_at: "2026-09-25T09:00:00+08:00",
      updated_at: "2026-09-25T09:01:00+08:00"
    }
  ],
  total: 2,
  page: 1,
  per_page: 50,
  message: "ok"
};

/** 详情信封：messages 原文轮次，点击条目后应按序还原成聊天气泡 */
const detailEnvelope = {
  data: {
    session_id: "sess-hist-1",
    goal: "分析账户收益",
    turn_count: 2,
    created_at: "2026-09-26T10:00:00+08:00",
    updated_at: "2026-09-26T10:05:00+08:00",
    messages: [
      { user: "核对白酒持仓成本与浮亏", assistant: "持仓成本 15200.00 元，当前浮亏 8.4%。" },
      { user: "那要是按半年算呢？", assistant: "近半年该标的回撤 11.2%，跑输基准。" }
    ]
  },
  message: "ok"
};

test.describe("历史会话栏（#1719 方案 A 页内折叠）", () => {
  test("默认折叠不发请求 → 展开可见历史 → 点击回放 → 新对话复位", async ({
    page,
    context,
    baseURL
  }) => {
    await injectSupabaseSession(context, baseURL!);

    let listCalls = 0;
    // 详情与列表端点用不同正则（列表带 query，详情带 id），互不串
    await page.route(
      /\/api\/agent\/sessions\/sess-hist-1\/?(?:\?.*)?$/,
      async route => {
        await route.fulfill({ json: detailEnvelope });
      }
    );
    await page.route(/\/api\/agent\/sessions\/?(?:\?.*)?$/, async route => {
      listCalls += 1;
      await route.fulfill({ json: listEnvelope });
    });

    await page.goto("/#/agent/chat");
    await expect(page).toHaveURL(/#\/agent\/chat/);

    // 刷新首屏：面板不可见且**不发列表请求**（默认折叠，不给首屏加负担）
    await expect(page.getByText("历史会话", { exact: true })).toHaveCount(0);
    expect(listCalls).toBe(0);

    // 展开：历史栏可见（刷新后历史可见的验收点）
    await page.getByRole("button", { name: "历史" }).click();
    await expect(page.getByText("历史会话", { exact: true })).toBeVisible();
    await expect(page.getByText("核对白酒持仓成本与浮亏")).toBeVisible();
    await expect(page.getByText("9 月定投扣款是否到账")).toBeVisible();
    await expect(page.getByText("2 条")).toBeVisible();
    expect(listCalls).toBe(1);

    // 点击条目：拉详情回放（用户 + 助手原文都上屏），面板收起
    await page.getByTitle("核对白酒持仓成本与浮亏").click();
    await expect(page.getByText("持仓成本 15200.00 元，当前浮亏 8.4%。")).toBeVisible();
    await expect(page.getByText("近半年该标的回撤 11.2%，跑输基准。")).toBeVisible();
    await expect(page.getByText("历史会话", { exact: true })).toHaveCount(0);

    // 新对话：清空回空态（会话 id 与消息列表一起复位）
    await page.getByRole("button", { name: "新对话" }).click();
    await expect(page.getByText("试着问一句")).toBeVisible();
    await expect(
      page.getByText("近半年该标的回撤 11.2%，跑输基准。")
    ).toHaveCount(0);

    // 截图留档（面试演示素材；test-results/ 已 gitignore）
    await page.screenshot({
      path: "test-results/agent-history-panel.png"
    });
  });
});
