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
