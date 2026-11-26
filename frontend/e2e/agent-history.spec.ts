import { expect, test } from "@playwright/test";
import { injectSupabaseSession } from "./support/session";

/**
 * 历史会话（2026-11 形态：≥lg 常驻左栏 / 窄屏抽屉）。
 *
 * 与 agent-chat.spec.ts 同因 mock：本仓 E2E 取舍是「不依赖后端」（见
 * playwright.config.ts）。这里验证**前端**接线：
 * - 桌面端左栏常驻，首屏即拉列表（不再有「展开才请求」这回事）；
 * - 窄屏左栏**不挂载**（v-if，不是 CSS 隐藏），所以仍然零请求；点页头「历史」开抽屉；
 * - 点击条目回放原文、抽屉自动收起；新对话复位。
 * 端点真实行为由 backend/tests/domains/test_agent_sessions.py 覆盖。
 */

/** 列表信封：分页家规 {data,total,page,per_page}；preview 故意避开示例问题文案，避免定位歧义。
 * title（2026-11-23 起）= 首条用户输入；与 preview 不同源的条目会渲染成「标题 + 结尾」两行，
 * 相同则只渲染一行——两种形态都要有用例数据，否则模板里的 v-if 永远不会被检出。 */
const listEnvelope = {
  data: [
    {
      session_id: "sess-hist-1",
      title: "核对白酒持仓成本",
      goal: "分析账户收益",
      preview: "核对白酒持仓成本与浮亏",
      turn_count: 2,
      created_at: "2026-09-26T10:00:00+08:00",
      updated_at: "2026-09-26T10:05:00+08:00"
    },
    {
      session_id: "sess-hist-2",
      title: "9 月定投扣款是否到账",
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
    title: "核对白酒持仓成本",
    goal: "分析账户收益",
    turn_count: 2,
    created_at: "2026-09-26T10:00:00+08:00",
    updated_at: "2026-09-26T10:05:00+08:00",
    messages: [
      {
        user: "核对白酒持仓成本与浮亏",
        assistant: "持仓成本 15200.00 元，当前浮亏 8.4%。"
      },
      {
        user: "那要是按半年算呢？",
        assistant: "近半年该标的回撤 11.2%，跑输基准。"
      }
    ]
  },
  message: "ok"
};

test.describe("历史会话（常驻左栏 / 窄屏抽屉）", () => {
  test("桌面：左栏常驻首屏即加载 → 点击回放 → 新对话复位", async ({
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

    await page.setViewportSize({ width: 1280, height: 800 });
    await page.goto("/#/agent/chat");
    await expect(page).toHaveURL(/#\/agent\/chat/);

    // 桌面端左栏常驻：不再需要点「历史」开关，首屏就应该看见列表
    const rail = page.locator(".agent-rail");
    await expect(rail).toBeVisible();
    await expect(rail.getByText("历史会话", { exact: true })).toBeVisible();
    await expect(page.getByText("核对白酒持仓成本与浮亏")).toBeVisible();
    await expect(page.getByText("9 月定投扣款是否到账")).toBeVisible();
    await expect(page.getByText("2 条")).toBeVisible();
    expect(listCalls).toBe(1);

    // 点击条目：拉详情回放（用户 + 助手原文都上屏）
    await page.getByTitle("核对白酒持仓成本与浮亏").click();
    await expect(
      page.getByText("持仓成本 15200.00 元，当前浮亏 8.4%。")
    ).toBeVisible();
    await expect(
      page.getByText("近半年该标的回撤 11.2%，跑输基准。")
    ).toBeVisible();

    // 新对话：清空回空态（会话 id 与消息列表一起复位）
    await page.getByRole("button", { name: "新对话" }).click();
    await expect(
      page.locator('[data-region="agent-capabilities"]')
    ).toBeVisible();
    await expect(
      page.getByText("近半年该标的回撤 11.2%，跑输基准。")
    ).toHaveCount(0);

    // 截图留档（面试演示素材；test-results/ 已 gitignore）
    await page.screenshot({
      path: "test-results/agent-history-panel.png"
    });
  });

  test("窄屏：左栏不挂载（零请求）→ 点历史开抽屉 → 选完自动收起", async ({
    page,
    context,
    baseURL
  }) => {
    await injectSupabaseSession(context, baseURL!);

    let listCalls = 0;
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

    await page.setViewportSize({ width: 375, height: 812 });
    await page.goto("/#/agent/chat");
    await expect(page).toHaveURL(/#\/agent\/chat/);

    // v-if 而非 CSS 隐藏：窄屏连节点都不该存在，列表请求一次都不发
    await expect(page.locator(".agent-rail")).toHaveCount(0);
    await expect(page.getByText("历史会话", { exact: true })).toHaveCount(0);
    expect(listCalls).toBe(0);

    // 抽屉打开才挂载 → 此时才发一次列表请求
    // exact 必写：能力目录里「自选与净值」的 hint 含「基金历史净值」，模糊匹配会命中两个按钮
    await page.getByRole("button", { name: "历史", exact: true }).click();
    await expect(page.getByText("历史会话", { exact: true })).toBeVisible();
    await expect(page.getByText("核对白酒持仓成本与浮亏")).toBeVisible();
    expect(listCalls).toBe(1);

    // 选条目：回放并自动收起抽屉（否则用户回不到对话本身）
    await page.getByTitle("核对白酒持仓成本与浮亏").click();
    await expect(
      page.getByText("持仓成本 15200.00 元，当前浮亏 8.4%。")
    ).toBeVisible();
    await expect(page.getByText("历史会话", { exact: true })).toHaveCount(0);
  });

  test("桌面：搜索框只把关键词作为 q 下发，清空即回全量", async ({
    page,
    context,
    baseURL
  }) => {
    await injectSupabaseSession(context, baseURL!);

    // 记下每次列表请求的 q（未带 = 空串），用来断言「防抖后只发一次」与「参数名是 q」
    const queries: string[] = [];
    await page.route(/\/api\/agent\/sessions\/?(?:\?.*)?$/, async route => {
      const q = new URL(route.request().url()).searchParams.get("q") ?? "";
      queries.push(q);
      await route.fulfill({
        json: q
          ? { ...listEnvelope, data: listEnvelope.data.slice(0, 1), total: 1 }
          : listEnvelope
      });
    });

    await page.setViewportSize({ width: 1280, height: 800 });
    await page.goto("/#/agent/chat");
    await expect(page.getByText("2 条")).toBeVisible();

    await page.getByLabel("搜索历史会话").fill("白酒");
    await expect(page.getByText("1 条")).toBeVisible();
    // 命中项留下、未命中项消失（过滤发生在服务端，前端不再自己筛）
    await expect(page.getByText("核对白酒持仓成本与浮亏")).toBeVisible();
    await expect(page.getByText("9 月定投扣款是否到账")).toHaveCount(0);
    // 防抖生效：连打字不会一个字一发（fill 一次 = 一次输入事件，故只应出现一次带 q 的请求）
    expect(queries.filter(Boolean)).toEqual(["白酒"]);

    await page.getByLabel("搜索历史会话").fill("");
    await expect(page.getByText("2 条")).toBeVisible();

    await page.screenshot({
      path: "test-results/agent-history-search.png"
    });
  });

  /**
   * 左栏可收起（2026-11 反馈：常驻栏吃掉 232px，用户要能收起来）。
   *
   * 判据是「节点消失」而不是「宽度归零」：宽度为 0 的栏里那串 button 仍在 Tab 序里，
   * 键盘用户会掉进一个看不见的区域——所以用 v-if，不是 CSS 折叠。
   */
  test("桌面：左栏可收起 → aria-expanded 跟随 → 再点恢复", async ({
    page,
    context,
    baseURL
  }) => {
    await injectSupabaseSession(context, baseURL!);

    await page.route(/\/api\/agent\/sessions\/?(?:\?.*)?$/, async route => {
      await route.fulfill({ json: listEnvelope });
    });

    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto("/#/agent/chat");

    const rail = page.locator(".agent-rail");
    const toggle = page.getByRole("button", { name: "历史", exact: true });

    // 默认展开（不改既有默认契约）：列表在、按钮报 true
    await expect(rail).toBeVisible();
    await expect(toggle).toHaveAttribute("aria-expanded", "true");

    // 收起：节点移除 + 按钮报 false
    await toggle.click();
    await expect(rail).toHaveCount(0);
    await expect(toggle).toHaveAttribute("aria-expanded", "false");

    // 再点恢复（状态是一次切换，不是单向关闭）
    await toggle.click();
    await expect(rail).toBeVisible();
    await expect(toggle).toHaveAttribute("aria-expanded", "true");
  });
});
