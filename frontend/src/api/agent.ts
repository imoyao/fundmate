import { http } from "@/utils/http";

// LLM 单轮内部可能多次调用模型（决策轮 + 叙事轮，单次可达 60s + 重试），
// 全局 axios 超时 10s 不够，同 ocr.ts 单独放宽
const CHAT_TIMEOUT = 120000;

/**
 * 会话状态白名单（对齐后端 agent_loop.ALLOWED_KEYS：
 * goal / missing_params / collected_params / history，
 * 多余键会被 G3 白名单校验以 400 拒绝，前端只做原样回传）
 */
export type AgentSessionState = {
  goal?: string;
  missing_params?: string[];
  collected_params?: Record<string, unknown>;
  history?: Array<{ role: string; content: string }>;
};

/** 澄清态：模型信息不足，content 即追问文本 */
export type AgentClarifyTurn = {
  type: "clarify";
  content: string;
  missing_params: string[];
  session_state: AgentSessionState;
};

/** 结果态：content 为自然语言总结，data 为工具返回的标量指标 */
export type AgentResultTurn = {
  type: "result";
  content: string;
  data: Record<string, unknown>;
  session_state: AgentSessionState;
};

/** 错误态：工具两轮失败等，content 为可读错误说明 */
export type AgentErrorTurn = {
  type: "error";
  content: string;
  session_state: AgentSessionState;
};

export type AgentTurn = AgentClarifyTurn | AgentResultTurn | AgentErrorTurn;

/** POST /api/agent/chat/ 成功信封（错误信封为 {data, message, error_code}） */
export type AgentChatResponse = {
  data: AgentTurn;
  message: string;
};

export type AgentChatRequest = {
  /** 本轮用户输入 */
  message: string;
  /** 会话 id（前端生成；后端轮次闸按 user_id + session_id 计数） */
  session_id: string;
  /** 上一轮回传的会话状态，首轮不传 */
  session_state?: AgentSessionState;
  /** 分析目标，缺省后端用默认值 */
  goal?: string;
};

/** 单轮对话（尾斜杠端点，需登录；限流/熔断/预算/轮次四道闸都在服务端） */
export function agentChat(payload: AgentChatRequest) {
  return http.request<AgentChatResponse>(
    "post",
    "/api/agent/chat/",
    { data: payload },
    { timeout: CHAT_TIMEOUT }
  );
}
