import { expect, test } from "@playwright/test";
import { injectSupabaseSession } from "./support/session";

/**
 * 对话页的「单滚动 + 贴底输入区」契约（2026-11 反馈「下拉滚动条太多」的回归网）。
 *
 * 背景：上一版把页面高度钉死、让 `.chat-list` 自己滚，于是外层 el-scrollbar
 * （页脚 / 对账横幅都在它的内容流里）多出一条滚动条，页面上同时出现三条。
 * 现在回到 design.md 的单一滚动：页面自己滚，输入区 sticky 贴底。
 *
 * 判据只认机器可验的两条，避免「看着像」：
 * 1. 消息列**不是**滚动容器（overflow-y 为 visible）；
 * 2. 长会话滚到顶时，dock 的底边仍等于视口底（sticky 生效，没被顶到折线以下）。
 */

const items = Array.from({ length: 7 }, (_, i) => ({
  session_id: `sess-scroll-${i}`,
  title: `滚动契约会话 ${i + 1}`,
  goal: "分析账户收益",
  preview: `滚动契约会话 ${i + 1}`,
  turn_count: 1,
  created_at: "2026-11-20T10:00:00+08:00",
  updated_at: "2026-11-20T10:05:00+08:00"
}));

const LONG_TURNS = 12;

test("空态：消息列不自成滚动容器（只有外层一条）", async ({
  page,
  context,
  baseURL
}) => {
  await injectSupabaseSession(context, baseURL!);
  await page.route(/\/api\/agent\/sessions\/?(?:\?.*)?$/, route =>
    route.fulfill({
      json: { data: items, total: items.length, page: 1, per_page: 50 }
    })
  );

  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/#/agent/chat");
  await expect(page.getByText("7 条")).toBeVisible();

  const overflowY = await page.evaluate(
    () =>
      getComputedStyle(document.querySelector(".chat-list") as HTMLElement)
        .overflowY
  );
  expect(overflowY).toBe("visible");
});

test("长会话：滚到顶后 dock 仍贴视口底", async ({ page, context, baseURL }) => {
  await injectSupabaseSession(context, baseURL!);
  await page.route(
    /\/api\/agent\/sessions\/sess-scroll-0\/?(?:\?.*)?$/,
    route =>
      route.fulfill({
        json: {
          data: {
            session_id: "sess-scroll-0",
            title: "滚动契约会话 1",
            goal: "分析账户收益",
            turn_count: LONG_TURNS,
            created_at: "2026-11-20T10:00:00+08:00",
            updated_at: "2026-11-20T10:05:00+08:00",
            messages: Array.from({ length: LONG_TURNS }, (_, i) => ({
              user: `第 ${i + 1} 问：我的持仓现在值多少钱？`,
              assistant: `第 ${i + 1} 轮回答：持仓成本 15200.00 元，当前浮亏 8.4%。补两句让内容够长，确保页面产生纵向滚动。`
            }))
          }
        }
      })
  );
  await page.route(/\/api\/agent\/sessions\/?(?:\?.*)?$/, route =>
    route.fulfill({
      json: { data: items, total: items.length, page: 1, per_page: 50 }
    })
  );

  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/#/agent/chat");
  await expect(page.getByText("7 条")).toBeVisible();
  await page.locator(".session-history__item").first().click();
  await expect(
    page.getByText(`第 ${LONG_TURNS} 轮回答`, { exact: false })
  ).toBeVisible();

  // 滚到顶：dock 若没 sticky，会被内容顶到视口之外
  await page.evaluate(() => {
    const wrap = document.querySelector(
      ".app-main .el-scrollbar__wrap"
    ) as HTMLElement;
    wrap.scrollTop = 0;
  });
  await page.waitForTimeout(300);

  const box = await page.evaluate(() => {
    const dock = document.querySelector(".chat-dock") as HTMLElement;
    const r = dock.getBoundingClientRect();
    const wrap = document.querySelector(
      ".app-main .el-scrollbar__wrap"
    ) as HTMLElement;
    return {
      dockBottom: Math.round(r.bottom),
      dockTop: Math.round(r.top),
      viewportBottom: window.innerHeight,
      pageScrolls: wrap.scrollHeight > wrap.clientHeight
    };
  });

  // 页面确实需要滚动（否则这条用例证明不了 sticky）
  expect(box.pageScrolls).toBe(true);
  // dock 完整落在视口内，且底边贴住视口底（±1px 容差给亚像素）
  expect(Math.abs(box.dockBottom - box.viewportBottom)).toBeLessThanOrEqual(1);
  expect(box.dockTop).toBeLessThan(box.viewportBottom);
});
