/**
 * 账本精灵的会话编排（#980 拆分产物）。
 *
 * 从 index.vue 抽出的东西只有一类：**「这一轮对话怎么走」的状态机**——
 * 消息列表、发送/停止两态、服务端权威 session_id、历史栏开合与刷新计数。
 * 渲染（消息长什么样、空态长什么样、输入区长什么样）在各自的组件里，
 * 页面外壳（index.vue）只负责把它们接起来。
 *
 * 三条不变量，改动时别破：
 * 1. **服务端权威会话（S2）**：`sessionId` 只 ← 后端下发的 `turn.session_id`，
 *    前端不自己生成、不落 localStorage；404（会话被清理/换端）时置 null，
 *    下一条消息由后端开新会话。
 * 2. **停止是两层**（#1714）：abort 管本地体验（请求断开、UI 即刻回空闲），
 *    `agentCancel` 管服务端（检查点收尾、不再烧后续模型调用）——缺一不可。
 * 3. **停止不留痕**：abort 后该轮不进消息列表，改用页头一句「已停止本轮分析」
 *    反馈，否则用户会以为「点了没反应」（但也不能弹错误气泡，那是验收 1）。
 */

import { computed, nextTick, ref } from "vue";
import { agentCancel, agentChat, getAgentSession } from "@/api/agent";
import type { AgentTurn } from "@/api/agent";
import {
  describeError,
  isCancelled,
  isScalarRecord,
  sanitizeBlocks,
  stripEmoji
} from "./agentChatFormat";
import type { ChatMessage } from "./agentChatFormat";

export function useAgentChat() {
  const messages = ref<ChatMessage[]>([]);
  const input = ref("");
  const pending = ref(false);
  /** 复合按钮防抖（#1714）：abort 已发出、等 catch 收尾的间隙 */
  const stopping = ref(false);
  /** 本轮被用户停止：停止后气泡消失，需一句明确反馈 */
  const stopped = ref(false);
  const sessionId = ref<string | null>(null);
  /** 历史栏默认折叠（#1719）：未展开时不发任何列表请求 */
  const historyOpen = ref(false);
  /** 每完成一轮 / 新对话 +1，通知历史栏重拉列表 */
  const historyRefreshToken = ref(0);
  /** 消息滚动容器：只由本页滚动定位，无需响应式 */
  const listRef = ref<HTMLElement>();
  /** 本轮请求的控制器（abort 用，无需响应式） */
  let abortRef: AbortController | null = null;

  /**
   * 复合按钮可用性（#1714 UI 复核）：空闲按输入内容判断；思考中只有 abort 已发出、
   * 等 catch 收尾的瞬间（stopping）不可点，用于防连点——其余时候必须可点（点了就是停止）
   */
  const sendDisabled = computed(() =>
    pending.value ? stopping.value : input.value.trim().length === 0
  );

  /**
   * 工具栏提示只说用户视角：快捷键说明在 placeholder、只读保证在页头副标题，
   * 内部机制（两轮模型 / 工具）不外显（#1311 讨论期确认的文案口径）
   */
  const statusText = computed(() => {
    if (pending.value) return "正在整理分析结果，约 10~60 秒";
    if (stopped.value) return "已停止本轮分析，可直接再问";
    return "回车发送 · 信息不全会先确认";
  });

  function scrollChat(): void {
    void nextTick().then(() => {
      const el = listRef.value;
      if (el) el.scrollTop = el.scrollHeight;
    });
  }

  function pushMessage(msg: ChatMessage): void {
    messages.value.push(msg);
    scrollChat();
  }

  /**
   * 停止当前分析（#1714 L1+L2）：abort 管体验（请求断开、UI 即刻回空闲），
   * cancel 端点管服务端（检查点收尾，不再烧后续模型调用）——两层解耦，缺一不可。
   */
  function stopPending(): void {
    if (!abortRef || stopping.value) return;
    stopping.value = true;
    stopped.value = true;
    if (sessionId.value) {
      agentCancel(sessionId.value).catch(() => {
        // fire-and-forget：取消置位失败不打扰用户（abort 已保证本地体验）
      });
    }
    abortRef.abort();
  }

  /**
   * 发一轮：`preset` 给定时用它（chips / 空态示例），否则取输入框内容并清空。
   * 返回值在**所有路径**都会 resolve（含被停止），调用方可直接 await 后聚焦输入框。
   */
  async function send(preset?: string): Promise<void> {
    const text = (preset ?? input.value).trim();
    if (!text || pending.value) return;
    if (!preset) input.value = "";
    pushMessage({ role: "user", content: text });

    pending.value = true;
    stopping.value = false;
    stopped.value = false; // 新一轮开始，清掉上一轮的「已停止」提示
    const controller = new AbortController();
    abortRef = controller;
    scrollChat();
    try {
      const res = await agentChat(
        {
          message: text,
          // S2 服务端权威会话：首轮不带 id，之后回带后端下发的 session_id，状态不落地前端
          session_id: sessionId.value ?? undefined
        },
        controller.signal
      );
      const turn: AgentTurn = res.data;
      sessionId.value = turn.session_id;
      if (turn.type === "cancelled") {
        // 服务端检查点收尾的取消态：该轮从未发生（不落库），无需提示气泡
        pushMessage({ role: "assistant", content: stripEmoji(turn.content) });
      } else if (turn.type === "error") {
        pushMessage({ role: "error", content: stripEmoji(turn.content) });
      } else if (turn.type === "result") {
        pushMessage({
          role: "assistant",
          content: stripEmoji(turn.content),
          data: isScalarRecord(turn.data) ? turn.data : undefined,
          blocks:
            Array.isArray(turn.blocks) && turn.blocks.length
              ? sanitizeBlocks(turn.blocks)
              : undefined
        });
      } else {
        pushMessage({ role: "assistant", content: stripEmoji(turn.content) });
      }
    } catch (e: unknown) {
      // 用户主动停止（L1 abort）：UI 即刻回空闲，不弹错误气泡（验收 1）
      if (isCancelled(e)) {
        return; // finally 仍执行（pending 复位等）
      }
      // 会话失效（404：被清理 / 换端）→ 落回新开会话，下一条消息自动重建
      if ((e as { response?: { status?: number } })?.response?.status === 404) {
        sessionId.value = null;
      }
      const msg = describeError(e);
      if (msg) pushMessage({ role: "error", content: msg });
    } finally {
      pending.value = false;
      stopping.value = false;
      abortRef = null;
      historyRefreshToken.value += 1; // 会话有了新轮次，历史栏重拉（面板关闭时也只是白拉一次）
    }
  }

  /**
   * 点击历史条目：拉详情回放并切换续聊（#1719）。
   * 回放只还原文本轮次——指标 chips 属当轮工具返回，未持久化到 messages，不伪造。
   */
  async function switchSession(id: string): Promise<void> {
    if (pending.value || id === sessionId.value) return;
    pending.value = true;
    try {
      const res = await getAgentSession(id);
      const detail = res.data;
      sessionId.value = detail.session_id;
      messages.value = detail.messages.flatMap(t => {
        const out: ChatMessage[] = [];
        if (t.user?.trim())
          out.push({ role: "user", content: stripEmoji(t.user) });
        if (t.assistant?.trim()) {
          out.push({ role: "assistant", content: stripEmoji(t.assistant) });
        }
        return out;
      });
      historyOpen.value = false;
      scrollChat();
    } catch (e: unknown) {
      const msg = describeError(e);
      if (msg) pushMessage({ role: "error", content: msg });
    } finally {
      pending.value = false;
    }
  }

  function resetSession(): void {
    messages.value = [];
    sessionId.value = null; // 下一条消息由服务端开新会话
    stopped.value = false; // 新对话不留上一轮的「已停止」提示
    historyOpen.value = false; // 新对话即收起历史栏（工具栏与面板内按钮同路径）
    historyRefreshToken.value += 1;
  }

  return {
    messages,
    input,
    pending,
    sessionId,
    historyOpen,
    historyRefreshToken,
    listRef,
    sendDisabled,
    statusText,
    send,
    stopPending,
    switchSession,
    resetSession
  };
}
