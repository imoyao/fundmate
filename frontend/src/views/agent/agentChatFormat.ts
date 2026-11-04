/**
 * 对话消息的展示层格式化（纯函数，零 Vue 依赖）。
 *
 * 从 index.vue 抽出的原因：这些函数原先夹在模板与请求编排之间，既不能单测、
 * 也让 index.vue 的 script 段看不清「到底做了几件事」。这里每个函数只回答一个
 * 展示问题（文本怎么洗、单元格怎么排、颜色怎么给、错误怎么说），全部可用
 * vitest 直接钉住（见 `__tests__/agentChatFormat.spec.ts`）。
 */

import type { AgentBlock, AgentTableColumnKind } from "@/api/agent";
import { formatAmount } from "@/utils/currency";

/** 展示层消息（role 与三态 type 解耦：error type 与网络层错误都渲染成 error 气泡） */
export type ChatMessage = {
  role: "user" | "assistant" | "error";
  content: string;
  data?: Record<string, unknown>;
  blocks?: AgentBlock[];
};

/**
 * 全站禁 Emoji 是硬约定但没有 lint 兜底，模型输出在这里剔除（AGENTS.md 前端约束）。
 *
 * 正则写在函数内而非模块级常量：带 `g` 的标志位正则是有状态的（lastIndex），
 * 复用同一个实例会在 `replace` 之外（如 `test`）留下脏游标——这里虽然只做
 * replace，但没有必要为省一次字面量构造埋这个坑。
 */
export function stripEmoji(text: string): string {
  return text.replace(
    /[\u{1F000}-\u{1FAFF}\u{2600}-\u{27BF}\u{2B00}-\u{2BFF}\u{FE0F}\u{200D}]/gu,
    ""
  );
}

/** blocks 双保险：后端已剔 Emoji，文本块与表格字符串单元格在此再兜底一次 */
export function sanitizeBlocks(blocks: AgentBlock[]): AgentBlock[] {
  return blocks.map(b => {
    if (b.type === "table") {
      return {
        ...b,
        rows: b.rows.map(row => {
          const clean: Record<string, string | number | boolean | null> = {};
          for (const [k, v] of Object.entries(row)) {
            clean[k] = typeof v === "string" ? stripEmoji(v) : v;
          }
          return clean;
        })
      };
    }
    return { ...b, text: stripEmoji(b.text) };
  });
}

/** 角色标签：用户消息不署名（气泡靠右已足够表达），错误态说人话叫「服务提示」 */
export function roleLabel(role: ChatMessage["role"]): string {
  if (role === "user") return "";
  return role === "error" ? "服务提示" : "账本精灵";
}

/** 指标 chips 只展示扁平标量记录；嵌套/数组结构只走自然语言，避免渲染出 [object Object] */
export function isScalarRecord(
  v: unknown
): v is Record<string, string | number | boolean | null> {
  if (typeof v !== "object" || v === null || Array.isArray(v)) return false;
  return Object.values(v).every(
    val => val === null || ["string", "number", "boolean"].includes(typeof val)
  );
}

/** 表格单元格展示：数值千分位 2 位小数（数字格式规范），字符串原样，空值统一 — */
export function formatCell(
  v: string | number | boolean | null | undefined
): string {
  if (v === null || v === undefined || v === "") return "—";
  if (typeof v === "number") return formatAmount(v);
  return String(v);
}

/** 行级盈亏语义色（#1712）：kind='pnl' 列按正负染涨红跌绿，0 / 非数值 / 汇总值不染 */
export function cellClass(
  v: string | number | boolean | null | undefined,
  kind: AgentTableColumnKind
): string {
  if (kind !== "pnl") return "";
  const n = typeof v === "number" ? v : Number(v);
  if (!Number.isFinite(n) || n === 0) return "";
  return n > 0 ? "msg__cell--rise" : "msg__cell--fall";
}

/**
 * 错误信封 → 可读文案；401/403 由全局拦截器统一提示，这里返回空串表示不入聊天气泡。
 *
 * 超时单独识别（后端单轮可达 60s+，前端也会等到 120s）：此时说「请求失败」会
 * 误导用户以为链路坏了，实际只是模型想久了。
 */
export function describeError(e: unknown): string {
  const err = e as {
    code?: string;
    message?: string;
    response?: { status?: number; data?: { message?: string } };
  };
  if (err?.code === "ECONNABORTED" || /timeout/i.test(err?.message ?? "")) {
    return "请求超时：精灵思考时间过长，请稍后重试。";
  }
  const status = err?.response?.status;
  if (status === 401 || status === 403) return "";
  const backendMsg = err?.response?.data?.message;
  if (status === 429) return backendMsg || "操作过于频繁，请稍后再试。";
  if (status === 503) return backendMsg || "AI 服务暂时繁忙，请稍后重试。";
  return backendMsg || "请求失败，请稍后重试。";
}

/** 用户主动停止（abort 触发）——与超时 / 失败分流：停止不弹错误气泡（验收 1） */
export function isCancelled(e: unknown): boolean {
  const err = e as { code?: string; message?: string };
  return err?.code === "ERR_CANCELED" || /cancel/i.test(err?.message ?? "");
}
