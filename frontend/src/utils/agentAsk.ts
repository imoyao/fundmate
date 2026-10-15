/**
 * 「问这个」上下文（#1764）：持仓 / 自选行 → 账本精灵的预填链路。
 *
 * query 键名、预填模板、轻提示文案的**单一真相源**——入口（持仓表 / 自选表）
 * 与接收端（/agent/chat）都从这里取，避免两处手抄漂移。
 * 纯函数、零 vue 依赖，可直接被 vitest 钉住。
 */

/** 行来源标识（query.from）：区分入口页面，供提示文案与后续排查使用 */
export type AgentAskFrom = "watchlist" | "inventory";

export interface AgentAskContext {
  /** 标的代码（必填：缺了就没有「问这个」语义） */
  symbol: string;
  /** 标的名称（缺省回退为代码，保证预填句仍可读） */
  name: string;
  /** 来源页面 */
  from: AgentAskFrom;
}

/** 入口 → 路由 query（`router.push({ name: "AgentChat", query: ... })`） */
export function agentAskQuery(ctx: AgentAskContext): Record<string, string> {
  return { symbol: ctx.symbol, name: ctx.name, from: ctx.from };
}

/** query 值可能是 string | string[] | null（vue-router LocationQuery），统一取首个非空串 */
function firstString(v: unknown): string {
  if (Array.isArray(v)) v = v[0];
  return typeof v === "string" ? v.trim() : "";
}

/**
 * 接收端：从 `route.query` 解析上下文。
 * `symbol` 缺失返回 null——不是「问这个」入口来的（或 URL 被手改过），不预填。
 */
export function parseAgentAskQuery(
  query: Record<string, unknown>
): AgentAskContext | null {
  const symbol = firstString(query.symbol);
  if (!symbol) return null;
  const rawFrom = firstString(query.from);
  const from: AgentAskFrom =
    rawFrom === "inventory" ? "inventory" : "watchlist";
  return { symbol, name: firstString(query.name) || symbol, from };
}

/**
 * 预填句模板（#1764 卡面示例）：只预填、**不自动发送**——不发请求、不烧 token，
 * 用户可改再发。
 */
export function agentAskPrefill(ctx: AgentAskContext): string {
  return `${ctx.name}（${ctx.symbol}）最近的收益情况怎么样？`;
}

/** 进入后的轻提示（#1764 要做的事 4）：让用户知道输入框里这句话从哪来 */
export function agentAskHint(ctx: AgentAskContext): string {
  return `已带上 ${ctx.name}（${ctx.symbol}）上下文`;
}
