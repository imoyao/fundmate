import { http } from "@/utils/http";

/** 连接管理页可见的连接字段（后端 list_connections 不含任何 token / 密文） */
export type McpConnection = {
  provider: string;
  auth_type: "oauth2" | "static_token";
  status: string;
  expires_at: string | null;
  updated_at: string | null;
  last_error_kind: string | null;
  key_version: number;
};

/** 统一信封：错误响应是 {data, message, error_code}，由 http 拦截器处理 */
export type McpEnvelope<T> = { data: T; message: string };

/** 发起浏览器授权：返回授权 URL，前端整页跳转（OAuth 回调是后端路由） */
export type McpOAuthBegin = {
  authorization_url: string;
  state: string;
  expires_in: number;
};

/** 当前用户的连接列表 */
export function listMcpConnections() {
  return http.request<McpEnvelope<McpConnection[]>>(
    "get",
    "/api/mcp/connections/"
  );
}

/** 保存用户自带 API Key（静态凭据型） */
export function connectMcpStaticToken(data: {
  provider: string;
  api_key: string;
}) {
  return http.request<
    McpEnvelope<{ provider: string; auth_type: "static_token" }>
  >("post", "/api/mcp/connections/static/", { data });
}

/** 断开连接：删本用户凭据，并尽力通知上游撤销 */
export function disconnectMcp(provider: string) {
  return http.request<McpEnvelope<{ provider: string; connected: false }>>(
    "delete",
    `/api/mcp/connections/${encodeURIComponent(provider)}/`
  );
}

/** 发起 OAuth 授权码流程（DCR + PKCE 在后端完成） */
export function beginMcpOAuth(provider: string) {
  return http.request<McpEnvelope<McpOAuthBegin>>(
    "post",
    "/api/mcp/oauth/begin/",
    { data: { provider } }
  );
}

/** 上游工具清单（连接校验返回）：连接之后能干什么的直接回答 */
export type McpVerifyResult = {
  provider: string;
  tool_count: number;
  tools: { name: string; description: string }[];
};

/** 校验连接：向上游握手并拉工具清单（过期 / 失效在这一步暴露成明确文案） */
export function verifyMcpConnection(provider: string) {
  return http.request<McpEnvelope<McpVerifyResult>>(
    "post",
    `/api/mcp/connections/${encodeURIComponent(provider)}/verify/`
  );
}

/** 工具目录条目（GET tools/）：capabilities = 命中的 Fund Mate 内部能力标签（能力高亮） */
export type McpToolInfo = {
  name: string;
  description: string;
  fetched_at: string;
  capabilities: string[];
};

/** 读工具目录（provider 级共享缓存）：不触发上游调用，未采样过为空数组 */
export function fetchMcpTools(provider: string) {
  return http.request<McpEnvelope<{ provider: string; tools: McpToolInfo[] }>>(
    "get",
    `/api/mcp/connections/${encodeURIComponent(provider)}/tools/`
  );
}

/** 同步向导第一步：上游账户清单的一个条目（id/name 来自账户发现真实返回） */
export type McpAccountEntry = {
  id: string;
  name: string;
  /** 上游 PC 端最后同步时间（证券账户才有；null = 未同步过） */
  lastSyncTime: string | null;
};

/** 按账户类型分好组（label/param 由后端下发，前端不再维护一份映射） */
export type McpAccountGroup = {
  group: string;
  label: string;
  param: string;
  accounts: McpAccountEntry[];
};

/** 拉上游账户清单（同步前必经步骤：不选账户不允许发起同步） */
export function fetchMcpAccounts(provider: string) {
  return http.request<
    McpEnvelope<{ provider: string; groups: McpAccountGroup[] }>
  >("post", `/api/mcp/connections/${encodeURIComponent(provider)}/accounts/`);
}

/** 同步所选账户：组键 + 账户 id */
export type McpSyncAccount = { group: string; id: string };

/** 同步返回的持仓预览条目（字段缺失为 null，不猜） */
export type McpSyncItem = {
  code: string | null;
  name: string | null;
  marketValue: string | null;
  quantity: string | null;
};

/** 同步结果：置信度判定 + 差异摘要 + 预览（低置信默认不导入） */
export type McpSyncResult = {
  tool: string;
  confidence: "high" | "low";
  reasons: string[];
  summary: {
    count: number;
    overlap: number;
    totalAsset: number | null;
    [key: string]: unknown;
  };
  items: McpSyncItem[];
  imported: boolean;
  forced: boolean;
};

/** 发起数据同步（#3304）：后端调上游工具 → 置信度判定 → 审计留痕。
 *  工具名由后端按所选账户的组推导，前端不传——工具是实现细节，不该进请求体。 */
export function syncMcpData(
  provider: string,
  data: { accounts: McpSyncAccount[]; force?: boolean }
) {
  return http.request<McpEnvelope<McpSyncResult>>(
    "post",
    `/api/mcp/connections/${encodeURIComponent(provider)}/sync/`,
    { data }
  );
}
