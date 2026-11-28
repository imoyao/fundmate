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
  /** OAuth 为主、API Key 兜底：卡片出「改用 API Key」次入口（且慢双通道，#3304） */
  staticFallback?: boolean;
  /** 已接入数据同步流（#3304）：连接后卡片出「同步数据」入口 */
  supportsSync?: boolean;
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
      "在弹窗中完成授权后自动回到本页，无需离开当前页面；凭证过期后点「重新授权」即可一键静默续期。",
    supportsSync: true
  },
  {
    provider: "qieman",
    name: "且慢",
    description:
      "授权且慢账号后，可验证连接并查看你账户的数据工具；也可以改用 API Key，只看市场温度等平台公开数据。",
    authType: "oauth2",
    authLabel: "浏览器授权",
    connectHint:
      "在弹窗中登录且慢账号并确认授权后自动回到本页；没有弹窗登录条件时，可改用 API Key 连接。",
    staticFallback: true
  }
];

/** provider → 中文名；未登记的返回「该服务」兜底（不猜具体名） */
export function serviceName(provider: string): string {
  return (
    MCP_SERVICES.find(service => service.provider === provider)?.name ??
    "该服务"
  );
}

/** 该服务是否已接入数据同步流（#3304）：只有登记了的才出「同步数据」入口 */
export function syncSupported(provider: string): boolean {
  return (
    MCP_SERVICES.find(service => service.provider === provider)
      ?.supportsSync === true
  );
}

/**
 * 已登记服务的工具展示元数据：**给普通用户读的中文标签 + 一句话说明**。
 *
 * 上游的 name（`queryStockPosition`）与 description（含 fundKey→fundKey 这类
 * 调用方参数说明）是喂给 AI / 程序员的，直接上页面等于把接口文档甩给用户
 * （#3303 页面走查反馈）。这里按工具名单点收口人话版；**未登记的工具回落
 * 原始 name + description**——宁可露英文也不猜错，新工具上线等这里补登记。
 */
const TOOL_LABELS: Record<
  string,
  Record<string, { label: string; summary: string }>
> = {
  tzzb: {
    promptAccountSelection: {
      label: "选择同步账户",
      summary: "拉取你在同花顺的账户清单，数据同步前先在这里选账户"
    },
    queryStockPosition: {
      label: "股票持仓",
      summary: "股票账户的持仓明细与总资产"
    },
    queryClearedPosition: {
      label: "已清仓记录",
      summary: "股票账户的历史清仓记录"
    },
    queryAssetChangeSummary: {
      label: "资金变动",
      summary: "某段时间内股票、基金账户的资金进出汇总"
    },
    queryMoneyHistory: {
      label: "资金流水",
      summary: "股票账户的资金交易流水明细"
    },
    queryDayProfitSummary: {
      label: "当日盈亏明细",
      summary: "某个交易日里每只股票、基金的盈亏"
    },
    queryPnlSummary: {
      label: "盈亏汇总",
      summary: "一段时间内的资产变化、总盈亏和收益率，可对比大盘"
    },
    queryDayCalendarSummary: {
      label: "每日盈亏日历",
      summary: "按月查看每天的盈亏走势和品种明细"
    },
    queryMonthCalendarSummary: {
      label: "月度盈亏日历",
      summary: "按年查看每个月的盈亏走势和品种明细"
    },
    queryFundAccount: {
      label: "基金账户持仓",
      summary: "基金账户的汇总资产与持仓明细"
    },
    queryFundHoldingReturns: {
      label: "基金持有收益",
      summary: "基金持仓的日、周、月、年与累计收益"
    },
    queryFundSummaryHistory: {
      label: "基金交易流水",
      summary: "基金账户的历史交易流水"
    },
    queryFundConfirmNav: {
      label: "基金确认净值",
      summary: "申购、赎回确认日的基金单位净值"
    },
    queryFundFeeRate: {
      label: "基金费率",
      summary: "基金申购、赎回的费率查询"
    },
    queryStockMarketRemark: {
      label: "行情备注",
      summary: "你在同花顺里记录的股票行情备注"
    }
  }
};

export type McpToolDisplayMeta = { label: string; summary: string };

/** 工具 → 页面展示用的标签与说明；未登记回落原始 name + description（不猜） */
export function toolDisplayMeta(
  provider: string,
  tool: { name: string; description: string }
): McpToolDisplayMeta {
  return (
    TOOL_LABELS[provider]?.[tool.name] ?? {
      label: tool.name,
      summary: tool.description
    }
  );
}

/** 连接状态 → 展示文案与徽标语义（未知状态一律按「未连接」处理，不猜）
 *
 * 库里 status 位只在断开/撤销时翻（token 过期 status 仍是 active，
 * oauthPopup.ts 头注释同款事实），徽章若只看 status 会「已连接」与
 * 「授权已于 X 过期」同屏矛盾。expires_at 已过 ⇒ 展示为 problem——这是
 * **展示态**判定，不回写库（上游 5 分钟寿命的 token 到点换新属常态）。
 * authExpired 是 verify / 同步调用收到 McpAuthError 时的兜底：上游可能提前
 * 撤销凭据，expires_at 还没到点也要把卡片切到 problem（#3303）。
 */
export function connectionState(
  status?: string | null,
  expiresAt?: string | null,
  nowMs: number = Date.now(),
  authExpired = false
): {
  label: string;
  tone: "connected" | "problem" | "idle";
} {
  if (authExpired) return { label: "授权已过期", tone: "problem" };
  if (status === "active") {
    if (isExpired(expiresAt, nowMs)) {
      return { label: "授权已过期", tone: "problem" };
    }
    return { label: "已连接", tone: "connected" };
  }
  if (status === "expired" || status === "revoked" || status === "error") {
    return { label: "需要重新连接", tone: "problem" };
  }
  return { label: "未连接", tone: "idle" };
}

/**
 * 后端 McpAuthError 的 4xx 响应 → 该把卡片切到「重新授权」。
 * 只认 4xx + 后端稳定文案（授权已过期 / 授权已失效 / 请更新 Token），
 * 不把「验证失败，请稍后重试」这类通用文案或 5xx 误判成过期。
 * 映射契约见 backend/app/domains/mcp/views.py 的 McpAuthError → 400 分支。
 */
export function isMcpAuthError(error: unknown): boolean {
  const payload = (
    error as {
      response?: { status?: number; data?: { message?: string } };
    }
  )?.response;
  if (!payload || ![400, 401, 403].includes(payload.status ?? 0)) return false;
  const message = payload.data?.message ?? "";
  return /授权已(过期|失效)|请更新\s*Token/.test(message);
}

/** 主按钮文案：OAuth 过期态点名「重新授权」，API Key 态仍是「重新连接」 */
export function connectButtonLabel(
  tone: "connected" | "problem" | "idle",
  authType: McpAuthType
): string {
  if (tone !== "problem") return "连接";
  return authType === "oauth2" ? "重新授权" : "重新连接";
}

/** expires_at 是否已过；空值 / 不可解析一律视为未过期（API Key 无过期概念）。
 *
 * ``nowMs`` 可选注入当前时间：过期徽章由页面的心跳钟驱动（useMcpConnections
 * 的 nowMs），否则 computed 只在 connection 变化时算一次——5 分钟寿命的 token
 * 到点后卡片会一直挂着「已连接」，直到用户手动刷新页面才翻面。
 */
export function isExpired(
  expiresAt?: string | null,
  nowMs: number = Date.now()
): boolean {
  if (!expiresAt) return false;
  const time = new Date(expiresAt).getTime();
  return !Number.isNaN(time) && time <= nowMs;
}

/** 是否即将过期（60 秒内）：给「已连接」卡片一个黄色弱化预警 + 立即续期入口，
 * 别等翻成 problem 用户才反应过来。已过期 / 空值 / 远未到期都是 false。 */
export function isExpiringSoon(
  expiresAt?: string | null,
  nowMs: number = Date.now()
): boolean {
  if (!expiresAt) return false;
  const time = new Date(expiresAt).getTime();
  if (Number.isNaN(time)) return false;
  const remaining = time - nowMs;
  return remaining > 0 && remaining <= 60_000;
}

/** 验证按钮文案：随校验状态换字，让「正在验证 / 再验一次」一眼可辨 */
export function verifyButtonLabel(
  verify: { status: "loading" | "ok" | "fail" } | null
): string {
  if (!verify) return "验证连接";
  if (verify.status === "loading") return "验证中…";
  return verify.status === "ok" ? "再验一次" : "重新验证";
}

/** 数据清单折叠钮文案：展开 / 收起两态，计数让「有多少数据可查」不点开也知道 */
export function toolsToggleLabel(open: boolean, count: number): string {
  return open ? "收起数据清单" : `可查询的数据（${count} 项）`;
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
 * 文案要与「点重新授权即可静默续期」的预期对齐，不制造「坏掉了」的恐慌。
 */
export function expiryHint(
  expiresAt?: string | null,
  nowMs: number = Date.now(),
  authExpired = false
): string {
  // verify / 数据调用报授权失效但 expires_at 尚未到点：文案与主按钮同指一个动作
  if (authExpired) return "授权已过期，点「重新授权」即可恢复连接";
  if (!expiresAt) return "";
  const date = new Date(expiresAt);
  if (Number.isNaN(date.getTime())) return "";
  const at = date.toLocaleString("zh-CN", {
    month: "numeric",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit"
  });
  if (date.getTime() <= nowMs) {
    return `授权已于 ${at} 过期，可一键静默续期`;
  }
  if (isExpiringSoon(expiresAt, nowMs)) {
    return `即将过期，授权将于 ${at} 过期，点「立即续期」保持连接`;
  }
  return `授权有效期至 ${at}`;
}
