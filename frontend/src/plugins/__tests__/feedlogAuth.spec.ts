/**
 * FeedLog widget 的 SSO 身份回调契约（#1998 任务 B）。
 *
 * ## 为什么这张网必须存在
 *
 * 官方 SDK 对 `getToken` 的约定是「返回 null = 已登出；throw = 临时故障，
 * SDK 会提示可重试」。这两者对用户是天壤之别：
 *
 * - 把**网络错误**吞成 null → widget 认定用户已登出 → **清掉缓存会话** →
 *   用户「莫名频繁掉线」（卡面点名的严重回归）；
 * - 把**响应结构异常**吞成 null → 同上，而且更难排查。
 *
 * 所以这里逐条钉死：令牌直返、null 只在「后端明确说未登录」时出现、
 * 一切异常都必须以 reject 形式冒出去。
 */
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";

const { createWidgetMock, getFeedlogTokenMock, routerPushMock } = vi.hoisted(
  () => ({
    createWidgetMock: vi.fn(),
    getFeedlogTokenMock: vi.fn(),
    routerPushMock: vi.fn()
  })
);

vi.mock("@feedlog/widget", () => ({
  createWidget: createWidgetMock,
  updateWidget: vi.fn()
}));

vi.mock("@/api/feedlog", () => ({
  getFeedlogToken: getFeedlogTokenMock
}));

vi.mock("@/router", () => ({
  default: { push: routerPushMock }
}));

/** 挂载 widget，返回传给 createWidget 的 options（含 auth 回调）。 */
async function mountWidget() {
  vi.resetModules();
  const mod = await import("../feedlog");
  mod.initFeedlogWidget();
  const call = createWidgetMock.mock.calls.at(-1);
  if (!call) throw new Error("createWidget 未被调用");
  return call[0] as {
    auth?: {
      getToken: () => Promise<string | null>;
      login?: () => Promise<void>;
    };
  };
}

beforeEach(() => {
  createWidgetMock.mockClear();
  getFeedlogTokenMock.mockReset();
  routerPushMock.mockReset();
  vi.stubEnv("VITE_FEEDLOG_BASE_URL", "https://feedback.example.com");
  // 本仓 vitest 跑在 node 环境（无 DOM），补齐 plugin 用到的两个浏览器对象
  vi.stubGlobal("document", {
    documentElement: { classList: { contains: () => false } }
  });
  vi.stubGlobal(
    "MutationObserver",
    class {
      observe() {}
      disconnect() {}
    }
  );
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.unstubAllEnvs();
});

describe("FeedLog widget 身份回调（#1998）", () => {
  it("createWidget 收到 auth 回调（getToken + login）", async () => {
    const options = await mountWidget();
    expect(typeof options.auth?.getToken).toBe("function");
    expect(typeof options.auth?.login).toBe("function");
  });

  it("已登录：令牌原样返回", async () => {
    getFeedlogTokenMock.mockResolvedValue({
      data: { token: "jwt-abc" },
      message: "ok"
    });
    const options = await mountWidget();
    await expect(options.auth!.getToken()).resolves.toBe("jwt-abc");
  });

  it("未登录：后端明确回 null 时返回 null（合法答案，不是故障）", async () => {
    getFeedlogTokenMock.mockResolvedValue({
      data: { token: null },
      message: "ok"
    });
    const options = await mountWidget();
    await expect(options.auth!.getToken()).resolves.toBeNull();
  });

  it("网络错误必须 throw —— 吞成 null 会让 widget 清会话（用户频繁掉线）", async () => {
    getFeedlogTokenMock.mockRejectedValue(new Error("network down"));
    const options = await mountWidget();
    await expect(options.auth!.getToken()).rejects.toThrow("network down");
  });

  it("响应结构异常也必须 throw（不是「未登录」）", async () => {
    getFeedlogTokenMock.mockResolvedValue({ message: "ok" } as never);
    const options = await mountWidget();
    await expect(options.auth!.getToken()).rejects.toThrow(/结构异常/);
  });

  it("login 跳转到登录页", async () => {
    const options = await mountWidget();
    await options.auth!.login!();
    expect(routerPushMock).toHaveBeenCalledWith("/login");
  });

  it("login 即使导航失败也要 settle（否则 widget 一直隐藏）", async () => {
    routerPushMock.mockRejectedValue(new Error("navigation aborted"));
    const options = await mountWidget();
    await expect(options.auth!.login!()).resolves.toBeUndefined();
  });
});
