<!--
  账本精灵对话页（#1121 S1-B，2026-09-26 参考竞品截图二次打磨）
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
          text
          size="small"
          :disabled="pending || messages.length === 0"
          @click="resetSession"
        >
          新对话
        </el-button>
      </div>

      <div ref="listRef" class="chat-card__list">
        <!-- 空态：欢迎 hero + 示例问题直达（功能型空态，插画资产就绪前的过渡方案，已同步 design.md） -->
        <div v-if="messages.length === 0 && !pending" class="chat-hero">
          <h2 class="chat-hero__title">
            你未曾留意的账<br />
            <span class="chat-hero__brand">账本精灵</span>全部记清
          </h2>
          <p class="chat-hero__label">试着问一句</p>
          <div class="chat-hero__questions">
            <button
              v-for="ex in EXAMPLES"
              :key="ex"
              type="button"
              class="chat-hero__q"
              @click="send(ex)"
            >
              <el-icon class="chat-hero__q-icon"><MagicStick /></el-icon>
              <span>{{ ex }}</span>
            </button>
          </div>
        </div>

        <div
          v-for="(m, index) in messages"
          :key="index"
          class="msg"
          :class="`msg--${m.role}`"
        >
          <div v-if="roleLabel(m.role)" class="msg__head">
            <span class="msg__avatar" :class="`msg__avatar--${m.role}`">
              <el-icon>
                <component
                  :is="m.role === 'error' ? WarningFilled : MagicStick"
                />
              </el-icon>
            </span>
            <span class="msg__role">{{ roleLabel(m.role) }}</span>
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
          <div class="msg__head">
            <span class="msg__avatar">
              <el-icon><MagicStick /></el-icon>
            </span>
            <span class="msg__role">账本精灵</span>
          </div>
          <div class="msg__bubble msg__bubble--pending">分析中</div>
        </div>
      </div>

      <div class="chat-dock">
        <!-- 能力快捷 chips：贴输入区常驻（对话中也可点），只列后端已有工具支撑的能力 -->
        <div class="chat-quick">
          <button
            v-for="q in QUICK_ACTIONS"
            :key="q.label"
            type="button"
            class="chat-quick__chip"
            :disabled="pending"
            @click="send(q.ask)"
          >
            <el-icon><component :is="q.icon" /></el-icon>
            <span>{{ q.label }}</span>
          </button>
        </div>

        <div class="chat-card__input">
          <div class="chat-input-pill">
            <el-input
              ref="taRef"
              v-model="input"
              type="textarea"
              :rows="1"
              :autosize="{ minRows: 1, maxRows: 4 }"
              placeholder="例如：我最近半年表现怎么样？（Enter 发送，Shift+Enter 换行）"
              :disabled="pending"
              @keydown="onKeydown"
            />
          </div>
          <el-button
            type="primary"
            circle
            class="chat-send"
            aria-label="发送"
            :loading="pending"
            :disabled="input.trim().length === 0"
            @click="send()"
          >
            <el-icon v-if="!pending"><ArrowUp /></el-icon>
          </el-button>
        </div>
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, ref } from "vue";
import {
  ArrowUp,
  MagicStick,
  Sunny,
  TrendCharts,
  WarningFilled,
  Wallet
} from "@element-plus/icons-vue";
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

/** 能力快捷 chips：短标签 + 图标；ask 与空态示例同源，只列后端工具已支撑的能力 */
const QUICK_ACTIONS = [
  { label: "投资表现", icon: TrendCharts, ask: "我最近半年表现怎么样？" },
  { label: "持仓价值", icon: Wallet, ask: "我的持仓现在值多少钱？" },
  { label: "市场温度", icon: Sunny, ask: "现在市场温度是多少？" }
] as const;

const EXAMPLES = QUICK_ACTIONS.map(a => a.ask);

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
  box-shadow: var(--shadow-raised);
}

.chat-card__toolbar {
  display: flex;
  gap: var(--space-compact);
  align-items: center;
  justify-content: space-between;
  padding: var(--space-3) var(--space-standard) 0;
}

.chat-card__hint {
  font-size: var(--text-small);
  color: var(--text-secondary);
}

.chat-card__list {
  flex: 1;
  min-height: 0; // 允许收缩才会有内部滚动，否则整页被撑高
  padding: var(--space-compact) var(--space-standard);
  overflow-y: auto;
}

// —— 空态 hero（参考竞品：两行大标题 + 品牌渐变词 + 示例问题块）——
.chat-hero {
  box-sizing: border-box;
  display: flex;
  flex-direction: column;
  gap: var(--space-5);
  align-items: flex-start;
  min-height: 100%;
  padding: var(--space-6) var(--space-2) var(--space-standard);
}

.chat-hero__title {
  margin: 0;
  font-size: var(--text-title);
  font-weight: 600;
  line-height: 1.4;
  color: var(--text-primary);
}

// 品牌渐变词：不支持 background-clip:text 时回退实色（避免文字被 transparent 藏掉）
.chat-hero__brand {
  color: var(--brand-700);
}

@supports (background-clip: text) or (-webkit-background-clip: text) {
  .chat-hero__brand {
    color: transparent;
    background: linear-gradient(135deg, var(--brand-700), var(--brand-900));
    background-clip: text;
    background-clip: text;
  }
}

.chat-hero__label {
  margin: 0;
  font-size: var(--text-label);
  color: var(--text-tertiary);
}

.chat-hero__questions {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  width: 100%;
  max-width: 640px;
}

.chat-hero__q {
  display: flex;
  gap: var(--space-3);
  align-items: center;
  padding: 14px 18px;
  font-size: var(--text-body);
  color: var(--text-primary);
  text-align: left;
  cursor: pointer;
  background-color: var(--bg-soft);
  border: 1px solid transparent;
  border-radius: var(--radius-md);
  transition:
    background-color 0.15s ease,
    border-color 0.15s ease;

  &:hover {
    background-color: var(--bg-hover);
    border-color: var(--border-default);
  }
}

.chat-hero__q-icon {
  flex: 0 0 auto;
  font-size: 16px;
  color: var(--brand-700);
}

// —— 消息：头像 + 角色标签行，气泡尾角收小 ——
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

.msg__head {
  display: flex;
  gap: var(--space-2);
  align-items: center;
}

.msg__avatar {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 24px;
  font-size: 13px;
  color: var(--brand-700);
  background-color: var(--brand-100);
  border-radius: 50%;
}

.msg__avatar--error {
  color: var(--color-danger-ink);
  background-color: var(--color-danger-10);
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
  border: 1px solid var(--border-subtle);
  // 尾角收小：助手左下 / 用户右下，聊天气泡的经典指向
  border-radius: var(--radius-lg) var(--radius-lg) var(--radius-lg)
    var(--radius-sm);
}

.msg--user .msg__bubble {
  color: var(--text-inverse);
  background-color: var(--brand-solid);
  border-color: transparent;
  border-radius: var(--radius-lg) var(--radius-lg) var(--radius-sm)
    var(--radius-lg);
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
  padding: 4px 12px;
  font-size: var(--text-small);
  background-color: var(--bg-subtle);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-pill);
}

.msg__metric-key {
  color: var(--text-tertiary);
}

.msg__metric-val {
  font-weight: 500;
  font-variant-numeric: tabular-nums;
  color: var(--text-primary);
}

// —— 底部 dock：能力快捷 chips + 胶囊输入 + 圆形发送 ——
.chat-dock {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  padding: var(--space-2) var(--space-standard) var(--space-standard);
  border-top: 1px solid var(--border-subtle);
}

.chat-quick {
  display: flex;
  gap: var(--space-2);
  padding-bottom: 2px;
  overflow-x: auto;
  scrollbar-width: none;

  &::-webkit-scrollbar {
    display: none;
  }
}

.chat-quick__chip {
  display: inline-flex;
  flex: 0 0 auto;
  gap: 6px;
  align-items: center;
  padding: 7px 14px;
  font-size: var(--text-small);
  color: var(--text-secondary);
  cursor: pointer;
  background-color: var(--bg-soft);
  border: 1px solid transparent;
  border-radius: var(--radius-pill);
  transition:
    background-color 0.15s ease,
    border-color 0.15s ease,
    color 0.15s ease;

  &:hover:not(:disabled) {
    color: var(--brand-ink);
    background-color: var(--bg-hover);
    border-color: var(--border-default);
  }

  &:disabled {
    cursor: not-allowed;
    opacity: 0.6;
  }
}

.chat-card__input {
  display: flex;
  gap: var(--space-2);
  align-items: flex-end;
}

.chat-input-pill {
  flex: 1;
  padding: 5px 8px 5px 18px;
  background-color: var(--bg-card);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-pill);
  transition:
    border-color 0.15s ease,
    box-shadow 0.15s ease;

  &:focus-within {
    border-color: var(--brand-700);
    box-shadow: var(--focus-ring);
  }

  :deep(.el-textarea__inner) {
    padding: 4px 8px;
    resize: none;
    background-color: transparent;
    border: none;
    border-radius: var(--radius-pill);
    box-shadow: none;
  }
}

.chat-send {
  flex: 0 0 auto;
  width: 44px;
  height: 44px;
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

  .chat-hero {
    padding-top: var(--space-standard);
  }

  .chat-hero__title {
    font-size: var(--text-heading);
  }
}
</style>
