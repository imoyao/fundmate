<!--
  账本精灵对话页（#1121 S1-B）
  三态渲染：clarify（追问）/ result（结果 + 指标 chips）/ error（服务提示）；
  session_state 每轮原样回传（G3 白名单，后端只认 4 个键）。
  不做：流式输出、历史会话列表（S1 边界，见 docs/working-notes/agent-dev-progress-2026-09-26.md）。
-->
<template>
  <div class="agent-page">
    <PageHeaderBar
      title="账本精灵"
      subtitle="一句话问账户：查表现、看持仓、问温度。只读分析，不改任何数据。"
    />

    <section class="chat-card">
      <div class="chat-card__toolbar">
        <span class="chat-card__hint">{{ statusText }}</span>
        <el-button
          size="small"
          :disabled="pending || messages.length === 0"
          @click="resetSession"
        >
          新对话
        </el-button>
      </div>

      <div ref="listRef" class="chat-card__list">
        <!-- 空态：示例问题直达（功能型空态，插画资产就绪前的过渡方案，已同步 design.md） -->
        <div v-if="messages.length === 0 && !pending" class="chat-empty">
          <p class="chat-empty__title">试着问一句</p>
          <div class="chat-empty__examples">
            <button
              v-for="ex in EXAMPLES"
              :key="ex"
              type="button"
              class="chat-empty__chip"
              @click="send(ex)"
            >
              {{ ex }}
            </button>
          </div>
        </div>

        <div
          v-for="(m, index) in messages"
          :key="index"
          class="msg"
          :class="`msg--${m.role}`"
        >
          <div v-if="roleLabel(m.role)" class="msg__role">
            {{ roleLabel(m.role) }}
          </div>
          <div class="msg__bubble">{{ m.content }}</div>
          <div v-if="m.data" class="msg__metrics">
            <div v-for="(val, key) in m.data" :key="key" class="msg__metric">
              <span class="msg__metric-key">{{ key }}</span>
              <span class="msg__metric-val">{{ String(val) }}</span>
            </div>
          </div>
        </div>

        <div v-if="pending" class="msg msg--pending">
          <div class="msg__role">账本精灵</div>
          <div class="msg__bubble msg__bubble--pending">分析中</div>
        </div>
      </div>

      <div class="chat-card__input">
        <el-input
          ref="taRef"
          v-model="input"
          type="textarea"
          :rows="2"
          placeholder="例如：我最近半年表现怎么样？（Enter 发送，Shift+Enter 换行）"
          :disabled="pending"
          @keydown="onKeydown"
        />
        <el-button
          type="primary"
          class="chat-card__send"
          :loading="pending"
          :disabled="input.trim().length === 0"
          @click="send()"
        >
          发送
        </el-button>
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, ref } from "vue";
import PageHeaderBar from "@/components/PageHeaderBar/index.vue";
import { agentChat } from "@/api/agent";
import type { AgentSessionState, AgentTurn } from "@/api/agent";

defineOptions({ name: "AgentChat" });

/** 展示层消息（role 与三态 type 解耦：error type 与网络层错误都渲染成 error 气泡） */
type ChatMessage = {
  role: "user" | "assistant" | "error";
  content: string;
  data?: Record<string, unknown>;
};

const EXAMPLES = [
  "我最近半年表现怎么样？",
  "我的持仓现在值多少钱？",
  "现在市场温度是多少？"
];

const messages = ref<ChatMessage[]>([]);
const input = ref("");
const pending = ref(false);
const listRef = ref<HTMLElement>();
const taRef = ref<{ focus: () => void } | null>(null);
const sessionId = ref(newSessionId());
const sessionState = ref<AgentSessionState | undefined>(undefined);

const statusText = computed(() =>
  pending.value
    ? "分析中：决策与总结要过两轮模型，约 10~60 秒"
    : "回车发送 · 缺参数会自动追问 · 工具全部只读"
);

/** 会话 id 前端生成：后端轮次闸按 user_id + session_id 计数（G2） */
function newSessionId(): string {
  return typeof crypto !== "undefined" && "randomUUID" in crypto
    ? crypto.randomUUID()
    : `s-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

/** 全站禁 Emoji 是硬约定但没有 lint 兜底，模型输出在这里剔除（AGENTS.md 前端约束） */
function stripEmoji(text: string): string {
  return text.replace(
    /[\u{1F000}-\u{1FAFF}\u{2600}-\u{27BF}\u{2B00}-\u{2BFF}\u{FE0F}\u{200D}]/gu,
    ""
  );
}

function roleLabel(role: ChatMessage["role"]): string {
  if (role === "user") return "";
  return role === "error" ? "服务提示" : "账本精灵";
}

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

/** 指标 chips 只展示扁平标量记录；嵌套/数组结构只走自然语言，避免渲染出 [object Object] */
function isScalarRecord(
  v: unknown
): v is Record<string, string | number | boolean | null> {
  if (typeof v !== "object" || v === null || Array.isArray(v)) return false;
  return Object.values(v).every(
    val => val === null || ["string", "number", "boolean"].includes(typeof val)
  );
}

/** 错误信封 → 可读文案；401/403 由全局拦截器统一提示，这里返回空串表示不入聊天气泡 */
function describeError(e: unknown): string {
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

function onKeydown(e: KeyboardEvent): void {
  if (e.key !== "Enter" || e.shiftKey) return;
  // 中文输入法组词期间的 Enter 是确认候选词，不能当发送
  if (e.isComposing) return;
  e.preventDefault();
  void send();
}

async function send(preset?: string): Promise<void> {
  const text = (preset ?? input.value).trim();
  if (!text || pending.value) return;
  if (!preset) input.value = "";
  pushMessage({ role: "user", content: text });

  pending.value = true;
  scrollChat();
  try {
    const res = await agentChat({
      message: text,
      session_id: sessionId.value,
      session_state: sessionState.value
    });
    const turn: AgentTurn = res.data;
    // 服务端权威状态原样回传：下一轮缺省带上，白名单外的键后端会 400 拒绝（G3）
    sessionState.value = turn.session_state;
    if (turn.type === "error") {
      pushMessage({ role: "error", content: stripEmoji(turn.content) });
    } else if (turn.type === "result") {
      pushMessage({
        role: "assistant",
        content: stripEmoji(turn.content),
        data: isScalarRecord(turn.data) ? turn.data : undefined
      });
    } else {
      pushMessage({ role: "assistant", content: stripEmoji(turn.content) });
    }
  } catch (e: unknown) {
    const msg = describeError(e);
    if (msg) pushMessage({ role: "error", content: msg });
  } finally {
    pending.value = false;
    taRef.value?.focus();
  }
}

function resetSession(): void {
  messages.value = [];
  sessionState.value = undefined;
  sessionId.value = newSessionId();
}
</script>

<style lang="scss" scoped>
@use "@/style/breakpoints" as bp;

.agent-page {
  display: flex;
  flex-direction: column;
  max-width: var(--layout-content-width);
  height: calc(100vh - 85px);
  padding: 0 var(--space-standard) var(--space-standard);
  margin: 0 auto;
}

.chat-card {
  display: flex;
  flex: 1;
  flex-direction: column;
  min-height: 320px;
  background-color: var(--bg-card);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-lg);
}

.chat-card__toolbar {
  display: flex;
  gap: var(--space-compact);
  align-items: center;
  justify-content: space-between;
  padding: var(--space-compact) var(--space-standard);
  border-bottom: 1px solid var(--border-light);
}

.chat-card__hint {
  font-size: var(--text-small);
  color: var(--text-secondary);
}

.chat-card__list {
  flex: 1;
  min-height: 0; // 允许收缩才会有内部滚动，否则整页被撑高
  padding: var(--space-standard);
  overflow-y: auto;
}

.chat-card__input {
  display: flex;
  gap: var(--space-compact);
  align-items: stretch;
  padding: var(--space-compact) var(--space-standard) var(--space-standard);
  border-top: 1px solid var(--border-light);

  :deep(.el-textarea__inner) {
    resize: none;
  }
}

.chat-card__send {
  flex: 0 0 auto;
  min-width: 72px;
}

.chat-empty {
  display: flex;
  flex-direction: column;
  gap: var(--space-compact);
  align-items: center;
  padding: var(--space-section) var(--space-standard);
}

.chat-empty__title {
  font-size: var(--text-heading);
  font-weight: 300;
  color: var(--text-primary);
}

.chat-empty__examples {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2);
  justify-content: center;
}

// 示例问题 chips：胶囊规范（--brand-100 底 --brand-700 字，见 design.md 分段/胶囊）
.chat-empty__chip {
  padding: 8px 16px;
  font-size: var(--text-small);
  color: var(--brand-700);
  cursor: pointer;
  background-color: var(--brand-100);
  border: none;
  border-radius: var(--radius-pill);
  transition: background-color 0.15s ease;

  &:hover {
    background-color: var(--brand-200);
  }
}

.msg {
  display: flex;
  flex-direction: column;
  gap: 4px;
  max-width: 78%;
  margin-bottom: var(--space-compact);
}

.msg--user {
  align-items: flex-end;
  margin-left: auto;
}

.msg--assistant,
.msg--pending,
.msg--error {
  align-items: flex-start;
  margin-right: auto;
}

.msg__role {
  font-size: var(--text-label);
  color: var(--text-tertiary);
}

.msg--error .msg__role {
  color: var(--color-danger);
}

.msg__bubble {
  padding: var(--space-3) var(--space-compact);
  font-size: var(--text-body);
  line-height: 1.6;
  color: var(--text-primary);
  overflow-wrap: break-word;
  white-space: pre-wrap;
  background-color: var(--bg-soft);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-lg);
}

.msg--user .msg__bubble {
  color: var(--text-inverse);
  background-color: var(--brand-solid);
  border-color: transparent;
}

.msg--error .msg__bubble {
  border-color: var(--color-danger);
}

.msg__bubble--pending {
  color: var(--text-tertiary);

  // 三个动态省略号点，不用 Emoji
  &::after {
    display: inline-block;
    width: 1.5em;
    overflow: hidden;
    vertical-align: bottom;
    content: "...";
    animation: chat-ellipsis 1.2s steps(4, end) infinite;
  }
}

.msg__metrics {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2);
  margin-top: 4px;
}

.msg__metric {
  display: inline-flex;
  gap: 6px;
  align-items: baseline;
  padding: 4px 10px;
  font-size: var(--text-small);
  background-color: var(--bg-soft);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-sm);
}

.msg__metric-key {
  color: var(--text-tertiary);
}

.msg__metric-val {
  font-variant-numeric: tabular-nums;
  color: var(--text-primary);
}

@keyframes chat-ellipsis {
  0% {
    width: 0;
  }

  100% {
    width: 1.5em;
  }
}

@include bp.below("md") {
  .agent-page {
    height: auto;
    min-height: calc(100vh - 85px);
  }

  .msg {
    max-width: 92%;
  }
}
</style>
