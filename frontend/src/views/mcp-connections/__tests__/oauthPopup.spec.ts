// oauthPopup 静默重授权机制的回归网。
//
// 环境是 node（vitest.config 统一配置），浏览器面全部用 vi.stubGlobal 打桩：
// window.open / addEventListener / location.origin / opener 都由本文件控制。
// 覆盖判据：
// - 弹窗被拦截 → blocked（调用方降级整页跳转的依据）；
// - 同源 + 匹配 provider 的完成消息 → 立即成功（主通道）；
// - 异源 / 不匹配 provider 的消息被忽略（多服务并发互不干扰）；
// - 轮询只在「凭据相比发起前有变化且 active」时判成功 —— 防拿旧凭据
//   的 active 状态位误判（旧 token 过期但状态位未翻时可能仍是 active）；
// - 弹窗被用户提前关闭且状态未恢复 → cancelled；等待超上限 → timeout。

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("@/api/mcp", () => ({ listMcpConnections: vi.fn() }));

import { listMcpConnections } from "@/api/mcp";
import {
  MCP_OAUTH_DONE_MESSAGE,
  notifyOpenerAndClose,
  reauthorizeViaPopup,
  snapshotOf
} from "../oauthPopup";

const ORIGIN = "https://app.test";

type Handler = (event: unknown) => void;

function makePopup({ closed = false } = {}) {
  return { closed, close: vi.fn() };
}

function stubWindow(options: { popup?: object; opener?: object } = {}) {
  const listeners = new Map<string, Handler[]>();
  const win = {
    open: vi.fn(() => options.popup ?? null),
    addEventListener: vi.fn((type: string, handler: Handler) => {
      const list = listeners.get(type) ?? [];
      list.push(handler);
      listeners.set(type, list);
    }),
    removeEventListener: vi.fn((type: string, handler: Handler) => {
      listeners.set(
        type,
        (listeners.get(type) ?? []).filter(item => item !== handler)
      );
    }),
    location: { origin: ORIGIN },
    screenX: 0,
    screenY: 0,
    outerWidth: 1200,
    outerHeight: 800,
    close: vi.fn(),
    opener: options.opener ?? null
  };
  vi.stubGlobal("window", win);
  return { win, listeners };
}

function emitMessage(
  listeners: Map<string, Handler[]>,
  event: Record<string, unknown>
): void {
  for (const handler of listeners.get("message") ?? []) handler(event);
}

beforeEach(() => {
  vi.useFakeTimers();
});

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
  vi.mocked(listMcpConnections).mockReset();
});

describe("notifyOpenerAndClose", () => {
  it("没有 opener（整页跳转落地）时返回 false，不尝试自关", () => {
    const { win } = stubWindow();
    expect(notifyOpenerAndClose("tzzb")).toBe(false);
    expect(win.close).not.toHaveBeenCalled();
  });

  it("opener 就是自己（手动新开标签页）时返回 false", () => {
    const { win } = stubWindow();
    (win as { opener?: unknown }).opener = win;
    expect(notifyOpenerAndClose("tzzb")).toBe(false);
    expect(win.close).not.toHaveBeenCalled();
  });

  it("有 opener 时发送完成消息并自关", () => {
    const opener = { postMessage: vi.fn() };
    const { win } = stubWindow({ opener });
    expect(notifyOpenerAndClose("tzzb")).toBe(true);
    expect(opener.postMessage).toHaveBeenCalledWith(
      { type: MCP_OAUTH_DONE_MESSAGE, provider: "tzzb" },
      ORIGIN
    );
    expect(win.close).toHaveBeenCalled();
  });
});

describe("snapshotOf", () => {
  it("只提取参与比对的三个字段", () => {
    expect(
      snapshotOf({
        provider: "tzzb",
        auth_type: "oauth2",
        status: "active",
        expires_at: "2026-11-28T10:50:00",
        updated_at: "2026-11-28 10:45:00",
        last_error_kind: null,
        key_version: 1
      })
    ).toEqual({
      status: "active",
      expires_at: "2026-11-28T10:50:00",
      updated_at: "2026-11-28 10:45:00"
    });
  });
});

describe("reauthorizeViaPopup", () => {
  it("弹窗被拦截 → blocked，不注册任何监听", async () => {
    const { listeners } = stubWindow();
    await expect(
      reauthorizeViaPopup("https://auth.example/authorize", "tzzb", null)
    ).resolves.toEqual({ ok: false, reason: "blocked" });
    expect(listeners.get("message")).toBeUndefined();
  });

  it("同源且 provider 匹配的完成消息 → 立即成功并清理", async () => {
    const popup = makePopup();
    const { listeners } = stubWindow({ popup });
    const promise = reauthorizeViaPopup(
      "https://auth.example/authorize",
      "tzzb",
      null
    );
    emitMessage(listeners, {
      origin: ORIGIN,
      data: { type: MCP_OAUTH_DONE_MESSAGE, provider: "tzzb" }
    });
    await expect(promise).resolves.toEqual({ ok: true });
    expect(popup.close).toHaveBeenCalled();
    expect(listeners.get("message")).toEqual([]);
  });

  it("异源或 provider 不匹配的消息被忽略，最终按超时收场", async () => {
    const popup = makePopup();
    const { listeners } = stubWindow({ popup });
    vi.mocked(listMcpConnections).mockResolvedValue({ data: [], message: "" });
    const promise = reauthorizeViaPopup(
      "https://auth.example/authorize",
      "tzzb",
      null,
      { timeoutMs: 5000, pollMs: 1500 }
    );
    emitMessage(listeners, {
      origin: "https://evil.example",
      data: { type: MCP_OAUTH_DONE_MESSAGE, provider: "tzzb" }
    });
    emitMessage(listeners, {
      origin: ORIGIN,
      data: { type: MCP_OAUTH_DONE_MESSAGE, provider: "qieman" }
    });
    await vi.advanceTimersByTimeAsync(5000);
    await expect(promise).resolves.toEqual({ ok: false, reason: "timeout" });
    expect(popup.close).toHaveBeenCalled();
  });

  it("轮询兜底：凭据相比快照有变化且 active → 成功", async () => {
    const popup = makePopup();
    stubWindow({ popup });
    vi.mocked(listMcpConnections).mockResolvedValue({
      data: [
        {
          provider: "tzzb",
          auth_type: "oauth2",
          status: "active",
          expires_at: "2026-11-28T10:50:00",
          updated_at: "2026-11-28 10:45:01",
          last_error_kind: null,
          key_version: 1
        }
      ],
      message: ""
    });
    const promise = reauthorizeViaPopup(
      "https://auth.example/authorize",
      "tzzb",
      {
        status: "expired",
        expires_at: "2026-11-28T10:40:00",
        updated_at: "2026-11-28 10:35:00"
      },
      { timeoutMs: 5000, pollMs: 1500 }
    );
    await vi.advanceTimersByTimeAsync(1500);
    await expect(promise).resolves.toEqual({ ok: true });
  });

  it("旧凭据仍是 active 且未变化 → 不误判，弹窗被用户关闭后按 cancelled 收场", async () => {
    const popup = makePopup();
    stubWindow({ popup });
    const stale = {
      provider: "tzzb",
      auth_type: "oauth2" as const,
      status: "active",
      expires_at: "2026-11-28T10:40:00",
      updated_at: "2026-11-28 10:35:00",
      last_error_kind: null,
      key_version: 1
    };
    vi.mocked(listMcpConnections).mockResolvedValue({
      data: [stale],
      message: ""
    });
    const promise = reauthorizeViaPopup(
      "https://auth.example/authorize",
      "tzzb",
      {
        status: "active",
        expires_at: "2026-11-28T10:40:00",
        updated_at: "2026-11-28 10:35:00"
      },
      { timeoutMs: 10000, pollMs: 1500 }
    );
    await vi.advanceTimersByTimeAsync(1500);
    expect(vi.mocked(listMcpConnections)).toHaveBeenCalledTimes(1);
    popup.closed = true;
    await vi.advanceTimersByTimeAsync(1500);
    await expect(promise).resolves.toEqual({ ok: false, reason: "cancelled" });
  });
});
