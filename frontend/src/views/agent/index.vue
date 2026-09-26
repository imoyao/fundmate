<!--
  账本精灵对话页（#1121 S1-B，2026-09-26 参考竞品截图二次打磨）
  三态渲染：clarify（追问）/ result（结果 + 指标 chips）/ error（服务提示）；
  S2 服务端权威会话：只回带后端下发的 session_id，状态由后端持有（不落地前端）。
  不做：历史会话列表（随后续卡，见 docs/working-notes/agent-dev-progress-2026-09-26.md）。
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
          <!-- 结构化块（#1712）：结论加粗置顶 / 明细文本 / 行级盈亏表（涨红跌绿）/ 风险提示弱化；
               blocks 缺失（后端契约漂移降级）回退纯文本气泡，两态互斥 -->
          <div
            v-if="m.blocks?.length"
            class="msg__bubble msg__bubble--structured"
          >
            <template v-for="(b, bi) in m.blocks" :key="bi">
              <div v-if="b.type === 'table'" class="msg__table-wrap">
                <table class="msg__table">
                  <thead>
                    <tr>
                      <th v-for="col in b.columns" :key="col.key">
                        {{ col.label }}
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr v-for="(row, ri) in b.rows" :key="ri">
                      <td
                        v-for="col in b.columns"
                        :key="col.key"
                        :class="cellClass(row[col.key], col.kind)"
                      >
                        {{ formatCell(row[col.key]) }}
                      </td>
                    </tr>
                  </tbody>
                </table>
                <p v-if="b.truncated" class="msg__table-note">仅展示前 50 行</p>
              </div>
              <p v-else class="msg__block" :class="`msg__block--${b.type}`">
                {{ b.text }}
              </p>
            </template>
          </div>
          <div v-else class="msg__bubble">{{ m.content }}</div>
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
import type { AgentBlock, AgentTableColumnKind, AgentTurn } from "@/api/agent";
import { formatAmount } from "@/utils/currency";

defineOptions({ name: "AgentChat" });

/** 展示层消息（role 与三态 type 解耦：error type 与网络层错误都渲染成 error 气泡） */
type ChatMessage = {
  role: "user" | "assistant" | "error";
  content: string;
  data?: Record<string, unknown>;
  blocks?: AgentBlock[];
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
const sessionId = ref<string | null>(null); // 服务端权威（S2）：首轮 null，后端下发后续带

/**
 * 工具栏提示只说用户视角：快捷键说明在 placeholder、只读保证在页头副标题，
 * 内部机制（两轮模型 / 工具）不外显（#1311 讨论期确认的文案口径）
 */
const statusText = computed(() =>
  pending.value
    ? "正在整理分析结果，约 10~60 秒"
    : "回车发送 · 信息不全会先确认"
);

/** 全站禁 Emoji 是硬约定但没有 lint 兜底，模型输出在这里剔除（AGENTS.md 前端约束） */
function stripEmoji(text: string): string {
  return text.replace(
    /[\u{1F000}-\u{1FAFF}\u{2600}-\u{27BF}\u{2B00}-\u{2BFF}\u{FE0F}\u{200D}]/gu,
    ""
  );
}

/** blocks 双保险：后端已剔 Emoji，文本块与表格字符串单元格在此再兜底一次 */
function sanitizeBlocks(blocks: AgentBlock[]): AgentBlock[] {
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

/** 表格单元格展示：数值千分位 2 位小数（数字格式规范），字符串原样，空值统一 — */
function formatCell(v: string | number | boolean | null | undefined): string {
  if (v === null || v === undefined || v === "") return "—";
  if (typeof v === "number") return formatAmount(v);
  return String(v);
}

/** 行级盈亏语义色（#1712）：kind='pnl' 列按正负染涨红跌绿，0 / 非数值 / 汇总值不染 */
function cellClass(
  v: string | number | boolean | null | undefined,
  kind: AgentTableColumnKind
): string {
  if (kind !== "pnl") return "";
  const n = typeof v === "number" ? v : Number(v);
  if (!Number.isFinite(n) || n === 0) return "";
  return n > 0 ? "msg__cell--rise" : "msg__cell--fall";
}

/** 错误信封 → 可读文案；401/403 由全局拦截器统一提示，这里返回空串表示不入聊天气泡 */ function describeError(
  e: unknown
): string {
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
      // S2 服务端权威会话：首轮不带 id，之后回带后端下发的 session_id，状态不落地前端
      session_id: sessionId.value ?? undefined
    });
    const turn: AgentTurn = res.data;
    sessionId.value = turn.session_id;
    if (turn.type === "error") {
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
    // 会话失效（404：被清理 / 换端）→ 落回新开会话，下一条消息自动重建
    if ((e as { response?: { status?: number } })?.response?.status === 404) {
      sessionId.value = null;
    }
    const msg = describeError(e);
    if (msg) pushMessage({ role: "error", content: msg });
  } finally {
    pending.value = false;
    taRef.value?.focus();
  }
}

function resetSession(): void {
  messages.value = [];
  sessionId.value = null; // 下一条消息由服务端开新会话
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

// 品牌渐变词：@supports 条件与块内声明**同写法**，只用不带前缀的
// background-clip:text——stylelint 的 property-no-vendor-prefix（standard 预设）
// 会把 -webkit-background-clip 剥成 background-clip，既制造重复声明（CI 红灯），
// 又会让「条件认 -webkit-、声明只认标准属性」的老浏览器进块拿到
// transparent 却裁不了背景，文字直接消失。不支持的浏览器整块不生效，
// 落回上面的 --brand-700 实色。
.chat-hero__brand {
  color: var(--brand-700);
}

@supports (background-clip: text) {
  .chat-hero__brand {
    color: transparent;
    background: linear-gradient(135deg, var(--brand-700), var(--brand-900));
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

  // 三个动态省略号点，不用 Emoji；宽度恒定 1.5em（动画只改 clip-path 不触发布局），
  // 否则 width 动画每步 reflow，气泡在思考期间反复变宽变窄（#1311 讨论期发现的抖动）
  &::after {
    display: inline-block;
    width: 1.5em;
    overflow: hidden;
    vertical-align: bottom;
    content: "...";
    animation: chat-ellipsis 1.2s steps(4, end) infinite;
  }
}

// —— 结构化块（#1712）：结论加粗 / 明细文本 / 行级盈亏表 / 风险提示弱化 ——
.msg__bubble--structured {
  min-width: 320px;

  // 块间间距（文本块 / 表格任意相邻组合），首块不加顶部外边距
  .msg__block + .msg__block,
  .msg__block + .msg__table-wrap,
  .msg__table-wrap + .msg__block {
    margin-top: var(--space-2);
  }
}

.msg__block {
  margin: 0;
  color: var(--text-primary);
}

.msg__block--summary {
  font-weight: 600;
}

.msg__block--risk {
  font-size: var(--text-small);
  color: var(--text-tertiary);
}

.msg__table-wrap {
  overflow-x: auto;
}

.msg__table {
  width: 100%;
  font-size: var(--text-small);
  border-collapse: collapse;

  th,
  td {
    padding: 4px 10px;
    text-align: right;
    white-space: nowrap;
  }

  th {
    font-weight: 500;
    color: var(--text-tertiary);
    border-bottom: 1px solid var(--border-default);
  }

  td {
    font-variant-numeric: tabular-nums;
    color: var(--text-primary);
    border-bottom: 1px solid var(--border-subtle);
  }

  th:first-child,
  td:first-child {
    text-align: left;
  }
}

// 涨红跌绿：文字级 token（浅 / 暗色各自保证对比度），仅行级 pnl 列使用
.msg__cell--rise {
  color: var(--color-rise-ink);
}

.msg__cell--fall {
  color: var(--color-fall-ink);
}

.msg__table-note {
  margin: var(--space-2) 0 0;
  font-size: var(--text-label);
  color: var(--text-tertiary);
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
    clip-path: inset(0 100% 0 0);
  }

  100% {
    clip-path: inset(0 0 0 0);
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
