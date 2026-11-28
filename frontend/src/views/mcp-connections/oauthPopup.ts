// OAuth 弹窗授权通道（静默重授权的机制层）。
//
// 背景：同花顺的 access_token 寿命很短（实测约 5 分钟），refresh_token 实测
// 一直 invalid_grant（#3286 验证记录），「刷新令牌续期」走不通。唯一可持续的
// 续期方式是重跑一遍授权码流程；整页跳转会打断用户当前操作，所以续期改成
// **弹窗**：浏览器里还留着上游会话时，授权页会自动跳回，用户全程无感（静默）。
//
// 完成检测是双通道，两条任意一条命中即成功：
// 1. 主通道：弹窗里的落地页（useMcpConnections.consumeRedirectNotice →
//    notifyOpenerAndClose）postMessage 通知 opener 后自关 —— 即时，不依赖轮询；
// 2. 兜底：opener 定时轮询连接列表，凭据相比发起前有变化且 status=active 视为
//    成功 —— 防 postMessage 丢失（如回调落地路由被 env 改走、落地页脚本未跑）。
//    只认「有变化」是防误判：旧凭据本来就可能是 active（token 过了期但状态位
//    还没翻），不能拿发起前的旧状态当成功。
//
// 失败语义：window.open 返回空（弹窗拦截器）→ blocked，调用方降级整页跳转；
// 弹窗被用户提前关掉且状态未恢复 → cancelled；等待超过上限 → timeout。

import { listMcpConnections, type McpConnection } from "@/api/mcp";

/** 弹窗落地页 → opener 的完成信号；消息契约只在这里和 notifyOpenerAndClose 出现 */
export const MCP_OAUTH_DONE_MESSAGE = "mcp_oauth_done";

/** 弹窗名固定，重复发起时复用同一窗口（避免弹一屏窗） */
const POPUP_NAME = "mcp-oauth";

const POLL_INTERVAL_MS = 1500;
const TIMEOUT_MS = 120_000;

export type SilentReauthResult = {
  ok: boolean;
  /** blocked=弹窗被拦截；cancelled=弹窗被提前关闭；timeout=等待超时；成功时缺省 */
  reason?: "blocked" | "cancelled" | "timeout";
};

/** 发起前抓一份连接快照，轮询用它判定「凭据确实换新了」 */
export type ConnectionSnapshot = {
  status: string;
  expires_at: string | null;
  updated_at: string | null;
};

export type ReauthOptions = {
  timeoutMs?: number;
  pollMs?: number;
};

/** 弹窗落地页调用：通知主窗口「授权完成」并自关。返回是否通知成功（无 opener 或异常为 false） */
export function notifyOpenerAndClose(provider: string): boolean {
  try {
    const opener = window.opener as Window | null | undefined;
    if (!opener || opener === window) return false;
    opener.postMessage(
      { type: MCP_OAUTH_DONE_MESSAGE, provider },
      window.location.origin
    );
    // 弹窗是脚本打开的，window.close() 允许自关；关不掉也无害，落地页照常展示
    window.close();
    return true;
  } catch {
    return false;
  }
}

/** 从连接列表项提取参与比对的三个字段（不含任何敏感信息） */
export function snapshotOf(connection: McpConnection): ConnectionSnapshot {
  return {
    status: connection.status,
    expires_at: connection.expires_at,
    updated_at: connection.updated_at
  };
}

function snapshotsEqual(
  current: ConnectionSnapshot,
  baseline: ConnectionSnapshot
): boolean {
  return (
    current.status === baseline.status &&
    current.expires_at === baseline.expires_at &&
    current.updated_at === baseline.updated_at
  );
}

function openPopup(url: string): Window | null {
  const width = 560;
  const height = 680;
  // 居中打开；拿不到屏幕参数时给 0，让浏览器兜底
  const left = Math.max(
    0,
    Math.round(
      ((window.screenX ?? 0) + ((window.outerWidth ?? width) - width)) / 2
    )
  );
  const top = Math.max(
    0,
    Math.round(
      ((window.screenY ?? 0) + ((window.outerHeight ?? height) - height)) / 2
    )
  );
  return window.open(
    url,
    POPUP_NAME,
    `width=${width},height=${height},left=${left},top=${top},toolbar=no,menubar=no`
  );
}

/**
 * 在弹窗中完成一次 OAuth 授权（不离开当前页）。
 *
 * 调用方先拿好 authorization_url，并把发起前的连接快照（无连接传 null）传进来；
 * 这里只负责弹窗、等待与判定。成功判据：收到落地页消息，或轮询到该 provider
 * 的连接相比快照有变化且 status=active。
 */
export async function reauthorizeViaPopup(
  authorizationUrl: string,
  provider: string,
  baseline: ConnectionSnapshot | null,
  options: ReauthOptions = {}
): Promise<SilentReauthResult> {
  const timeoutMs = options.timeoutMs ?? TIMEOUT_MS;
  const pollMs = options.pollMs ?? POLL_INTERVAL_MS;

  const popup = openPopup(authorizationUrl);
  if (!popup || popup.closed) return { ok: false, reason: "blocked" };

  return await new Promise<SilentReauthResult>(resolve => {
    let settled = false;
    let pollTimer: ReturnType<typeof setTimeout> | undefined;
    const timeoutTimer = setTimeout(() => {
      finish({ ok: false, reason: "timeout" });
    }, timeoutMs);

    function finish(result: SilentReauthResult): void {
      if (settled) return;
      settled = true;
      clearTimeout(timeoutTimer);
      if (pollTimer !== undefined) clearTimeout(pollTimer);
      window.removeEventListener("message", onMessage);
      try {
        popup.close();
      } catch {
        // 弹窗可能已被浏览器回收，忽略
      }
      resolve(result);
    }

    function onMessage(event: MessageEvent): void {
      // 只认同源信号；provider 不匹配的信号不消费（多服务并发授权互不干扰）
      if (event.origin !== window.location.origin) return;
      const data = event.data as { type?: string; provider?: string } | null;
      if (data?.type !== MCP_OAUTH_DONE_MESSAGE) return;
      if (data.provider !== provider) return;
      finish({ ok: true });
    }

    window.addEventListener("message", onMessage);

    async function poll(): Promise<void> {
      let pending = true;
      try {
        const response = await listMcpConnections();
        const current = (response.data ?? []).find(
          item => item.provider === provider
        );
        if (current && current.status === "active") {
          const changed =
            baseline === null || !snapshotsEqual(snapshotOf(current), baseline);
          if (changed) {
            pending = false;
            finish({ ok: true });
          }
        }
      } catch {
        // 单次轮询失败（网络抖动）不打断等待，下一轮再看
      }
      if (settled) return;
      if (!pending) return;
      // 弹窗被用户提前关掉且状态未恢复 → 视为放弃
      if (popup.closed) {
        finish({ ok: false, reason: "cancelled" });
        return;
      }
      pollTimer = setTimeout(poll, pollMs);
    }

    pollTimer = setTimeout(poll, pollMs);
  });
}
