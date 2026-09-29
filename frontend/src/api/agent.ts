import { http } from "@/utils/http";

// LLM 单轮内部可能多次调用模型（决策轮 + 叙事轮，单次可达 60s + 重试），
// 全局 axios 超时 10s 不够，同 ocr.ts 单独放宽
const CHAT_TIMEOUT = 120000;

/** 澄清态：模型信息不足，content 即追问文本 */
export type AgentClarifyTurn = {
  type: "clarify";
  content: string;
  missing_params: string[];
  /** 服务端权威会话 id（S2）：前端只回带 id，状态由后端持有 */
  session_id: string;
};

/** 表格列语义 kind（#1712）：'pnl' 列前端按正负染涨跌色（行级语义），'plain' 不染 */
export type AgentTableColumnKind = "plain" | "pnl";

/**
 * 结构化叙事块（#1712）：后端 parse_narrative_blocks 把【结论】/【明细】/【风险提示】
 * 三小节解析为块，行级工具数据组装成表格块；blocks 缺失 / 为 null / 空数组时
 * 前端回退纯文本气泡（契约漂移降级，见后端 narrative_blocks.py 模块注释）。
 */
export type AgentBlock =
  | { type: "summary"; text: string }
  | { type: "text"; text: string }
  | { type: "risk"; text: string }
  | {
      type: "table";
      columns: Array<{
        key: string;
        label: string;
        kind: AgentTableColumnKind;
      }>;
      rows: Array<Record<string, string | number | boolean | null>>;
      truncated: boolean;
    };

/** 结果态：content 为自然语言总结，data 为工具返回的标量指标 */
export type AgentResultTurn = {
  type: "result";
  content: string;
  data: Record<string, unknown>;
  /** 结构化块（可缺省：后端解析失败降级时不带，见 narrative_blocks.py） */
  blocks?: AgentBlock[] | null;
  /** 服务端权威会话 id（S2）：前端只回带 id，状态由后端持有 */
  session_id: string;
};

/** 错误态：工具两轮失败等，content 为可读错误说明 */
export type AgentErrorTurn = {
  type: "error";
  content: string;
  session_id: string;
};

/** 取消态（#1714 L2）：服务端在检查点提前收尾，该轮不落库（从未发生语义） */
export type AgentCancelledTurn = {
  type: "cancelled";
  content: string;
  session_id: string;
};

export type AgentTurn =
  AgentClarifyTurn | AgentResultTurn | AgentErrorTurn | AgentCancelledTurn;

/** POST /api/agent/chat/ 成功信封（错误信封为 {data, message, error_code}） */
export type AgentChatResponse = {
  data: AgentTurn;
  message: string;
};

export type AgentChatRequest = {
  /** 本轮用户输入 */
  message: string;
  /** 会话 id（服务端生成；首轮不传，之后回带响应里的 session_id） */
  session_id?: string;
  /** 分析目标（仅新建会话时生效），缺省后端用默认值 */
  goal?: string;
};

/** 单轮对话（尾斜杠端点，需登录；限流/熔断/预算/轮次四道闸都在服务端）。
 * signal（#1714 L1）：停止按钮 abort 后请求立即断开，UI 即刻回空闲；
 * 服务端是否提前收尾由 cancel 端点的标志决定（协作式取消，两层解耦） */
export function agentChat(payload: AgentChatRequest, signal?: AbortSignal) {
  return http.request<AgentChatResponse>(
    "post",
    "/api/agent/chat/",
    { data: payload, signal },
    { timeout: CHAT_TIMEOUT }
  );
}

/** 标记会话取消（#1714 L2）：正在跑的轮次在服务端下一检查点收尾，不再烧后续模型调用。
 * 前端 fire-and-forget 调用（abort 已保证本地体验，此调用失败静默） */
export function agentCancel(sessionId: string) {
  return http.request<{ data: { session_id: string }; message: string }>(
    "post",
    "/api/agent/chat/cancel/",
    { data: { session_id: sessionId } }
  );
}

// —— 历史会话（#1719 历史栏读路径）——

/** 历史栏列表项：**不含 messages**，preview 为末条用户输入截断（60 字），行体积与会话长度无关 */
export type AgentSessionItem = {
  session_id: string;
  /** 会话标题（后端缺省值统一为默认目标，故前端以 preview 辨认会话） */
  goal: string;
  preview: string;
  turn_count: number;
  created_at: string | null;
  updated_at: string | null;
};

/** GET /api/agent/sessions/ 成功信封（分页家规 {data,total,page,per_page}） */
export type AgentSessionListResponse = {
  data: AgentSessionItem[];
  total: number;
  page: number;
  per_page: number;
  message: string;
};

/** 单会话详情：messages 为原文轮次 [{user, assistant}]，供历史栏点击后回放 */
export type AgentSessionDetail = {
  session_id: string;
  goal: string;
  turn_count: number;
  created_at: string | null;
  updated_at: string | null;
  messages: Array<{ user: string; assistant: string }>;
};

export type AgentSessionDetailResponse = {
  data: AgentSessionDetail;
  message: string;
};

/** 本人历史会话列表（按更新时间倒序；他人会话在服务端即不可见） */
export function listAgentSessions(params?: {
  page?: number;
  per_page?: number;
}) {
  return http.request<AgentSessionListResponse>("get", "/api/agent/sessions/", {
    params
  });
}

/** 单会话详情（越权 / 不存在统一 404，全局拦截器提示） */
export function getAgentSession(sessionId: string) {
  return http.request<AgentSessionDetailResponse>(
    "get",
    `/api/agent/sessions/${sessionId}/`
  );
}
