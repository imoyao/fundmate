// 连接管理页的服务清单（UI 侧登记）。
//
// 与后端两份登记表一一对应，**新增服务必须前后端同步**：
// - 浏览器跳转型 → backend/app/services/mcp/oauth.py 的 PROVIDERS；
// - API Key 型 → backend/app/services/mcp/registry.py 的 @register_provider。
//
// 为什么不从后端拉清单：后端只返回 provider 名，展示名 / 说明 / 认证方式本来就是
// UI 元数据；让前端再按名字映射一遍等于多一次漂移机会。这里直接把「名字 + 展示」
// 放在一起，改一家服务只动这一行。
//
// 不提供 URL 输入框：SSRF 红线（docs/dev/mcp-connection-management.md §7），
// provider 只能是代码登记的常量，用户输入地址一概不接受。

export type McpAuthType = "oauth2" | "static_token";

export type McpService = {
  /** 与后端 provider 名逐字一致，大小写敏感 */
  provider: string;
  /** 展示名：用户看到的就是这个，不要在这里拼 provider 名 */
  name: string;
  /** 一句话说明这个服务能带来什么，面向小白 */
  description: string;
  authType: McpAuthType;
  /** 认证方式的中文短标签（卡片角标） */
  authLabel: string;
  /** 点击连接前的提示（OAuth 会跳浏览器，API Key 只在本站填） */
  connectHint: string;
};

export const MCP_SERVICES: readonly McpService[] = [
  {
    provider: "tzzb",
    name: "同花顺投资账本",
    description: "授权后可在账本精灵里直接查询投资账本的持仓与收益。",
    authType: "oauth2",
    authLabel: "浏览器授权",
    connectHint:
      "在弹窗中完成授权后自动回到本页，无需离开当前页面；凭证过期后点「重新连接」即可一键静默续期。"
  },
  {
    provider: "qieman",
    name: "且慢",
    description: "填入且慢的 API Key，即可在账本精灵里查询你的且慢账户。",
    authType: "static_token",
    authLabel: "API Key",
    connectHint: "API Key 加密保存，仅用于代表你调用且慢的数据。"
  }
];

/** 连接状态 → 展示文案与徽标语义（未知状态一律按「未连接」处理，不猜） */
export function connectionState(status?: string | null): {
  label: string;
  tone: "connected" | "problem" | "idle";
} {
  if (status === "active") return { label: "已连接", tone: "connected" };
  if (status === "expired" || status === "revoked" || status === "error") {
    return { label: "需要重新连接", tone: "problem" };
  }
  return { label: "未连接", tone: "idle" };
}

/**
 * 过期时间 → 卡片上的辅助说明；没有过期时间（API Key）返回空串。
 * 已过期明确说「已过期」——上游凭证寿命短（同花顺约 5 分钟），到点换新属常态，
 * 文案要与「点重新连接即可静默续期」的预期对齐，不制造「坏掉了」的恐慌。
 */
export function expiryHint(expiresAt?: string | null): string {
  if (!expiresAt) return "";
  const date = new Date(expiresAt);
  if (Number.isNaN(date.getTime())) return "";
  const at = date.toLocaleString("zh-CN", {
    month: "numeric",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit"
  });
  return date.getTime() <= Date.now()
    ? `授权已于 ${at} 过期，可一键静默续期`
    : `授权有效期至 ${at}`;
}
