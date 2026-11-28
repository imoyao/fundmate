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
    description:
      "授权同花顺投资账本后，可验证连接并查看上游提供的全部数据工具（账户、持仓、盈亏、流水等）。",
    authType: "oauth2",
    authLabel: "浏览器授权",
    connectHint:
      "在弹窗中完成授权后自动回到本页，无需离开当前页面；凭证过期后点「重新连接」即可一键静默续期。"
  },
  {
    provider: "qieman",
    name: "且慢",
    description:
      "填入且慢的 API Key 后，可验证连接并查看上游提供的数据工具（市场温度、组合持仓与净值等）。",
    authType: "static_token",
    authLabel: "API Key",
    connectHint: "API Key 加密保存，仅用于代表你调用且慢的数据。"
  }
];

/** provider → 中文名；未登记的返回「该服务」兜底（不猜具体名） */
export function serviceName(provider: string): string {
  return (
    MCP_SERVICES.find(service => service.provider === provider)?.name ??
    "该服务"
  );
}

/** 连接状态 → 展示文案与徽标语义（未知状态一律按「未连接」处理，不猜）
 *
 * 两参形态：库里 status 位只在断开/撤销时翻（token 过期 status 仍是 active，
 * oauthPopup.ts 头注释同款事实），徽章若只看 status 会「已连接」与
 * 「授权已于 X 过期」同屏矛盾。expires_at 已过 ⇒ 展示为 problem——这是
 * **展示态**判定，不回写库（上游 5 分钟寿命的 token 到点换新属常态）。
 */
export function connectionState(
  status?: string | null,
  expiresAt?: string | null
): {
  label: string;
  tone: "connected" | "problem" | "idle";
} {
  if (status === "active") {
    if (isExpired(expiresAt)) {
      return { label: "授权已过期", tone: "problem" };
    }
    return { label: "已连接", tone: "connected" };
  }
  if (status === "expired" || status === "revoked" || status === "error") {
    return { label: "需要重新连接", tone: "problem" };
  }
  return { label: "未连接", tone: "idle" };
}

/** expires_at 是否已过；空值 / 不可解析一律视为未过期（API Key 无过期概念） */
export function isExpired(expiresAt?: string | null): boolean {
  if (!expiresAt) return false;
  const time = new Date(expiresAt).getTime();
  return !Number.isNaN(time) && time <= Date.now();
}

/** 验证按钮文案：随校验状态换字，让「正在验证 / 再验一次」一眼可辨 */
export function verifyButtonLabel(
  verify: { status: "loading" | "ok" | "fail" } | null
): string {
  if (!verify) return "验证连接";
  if (verify.status === "loading") return "验证中…";
  return verify.status === "ok" ? "再验一次" : "重新验证";
}

/** 能力清单折叠钮文案：展开 / 收起两态，计数让「有多少工具」不点开也知道 */
export function toolsToggleLabel(open: boolean, count: number): string {
  return open ? "收起能力清单" : `能力清单（${count}）`;
}

/**
 * 工具的能力徽章文案：命中 Fund Mate 内部能力时「已对上：交易对账」样式。
 * 语义是**能力映射命中**（上游工具对得上我们的某个内部能力），不是对账已完成。
 */
export function toolCapLabel(capabilities: string[]): string {
  return capabilities.length ? `已对上：${capabilities.join("、")}` : "";
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
