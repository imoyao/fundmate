<!--
  单条对话消息（#980 拆分产物）。三态渲染：
  - clarify / 降级：纯文本气泡；
  - result（#1712 结构化）：结论加粗置顶 / 明细文本 / 行级盈亏表（涨红跌绿）/ 风险提示弱化，
    blocks 缺失（后端契约漂移降级）回退纯文本气泡，两态互斥；
  - error：服务提示气泡。
  另带一个 `pending` 变体（思考中气泡）：它与消息共用 `.msg*` 全套样式，
  单独抽组件会把这些样式复制一份，故用同一个组件按 `pending` 切换。
-->
<template>
  <div class="msg" :class="rootClass">
    <div v-if="headLabel" class="msg__head">
      <span class="msg__avatar" :class="avatarClass">
        <el-icon>
          <component :is="icon" />
        </el-icon>
      </span>
      <span class="msg__role">{{ headLabel }}</span>
    </div>

    <!-- 思考态只有气泡：停止动作收口到输入区复合按钮（#1714 UI 复核：
         停止键不是独立按钮，而是发送键就地切换的形态） -->
    <div v-if="pending" class="msg__bubble msg__bubble--pending">分析中</div>

    <template v-else-if="message">
      <div
        v-if="message.blocks?.length"
        class="msg__bubble msg__bubble--structured"
      >
        <template v-for="(b, bi) in message.blocks" :key="bi">
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
      <div v-else class="msg__bubble">{{ message.content }}</div>

      <div v-if="message.data" class="msg__metrics">
        <div v-for="(val, key) in message.data" :key="key" class="msg__metric">
          <span class="msg__metric-key">{{ key }}</span>
          <span class="msg__metric-val">{{ String(val) }}</span>
        </div>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed } from "vue";
import { MagicStick, WarningFilled } from "@element-plus/icons-vue";
import { cellClass, formatCell, roleLabel } from "../agentChatFormat";
import type { ChatMessage } from "../agentChatFormat";

defineOptions({ name: "AgentMessageItem" });

const props = withDefaults(
  defineProps<{
    /** 要渲染的消息；`pending` 为 true 时可省略 */
    message?: ChatMessage | null;
    /** 思考中气泡（与消息共用 .msg* 样式，故同组件不同变体） */
    pending?: boolean;
  }>(),
  { message: null, pending: false }
);

/** 思考态在语义上属于助手一方（角色标签 / 头像都按 assistant 走） */
const role = computed<ChatMessage["role"]>(
  () => props.message?.role ?? "assistant"
);

/** 但根类名保留 `msg--pending`（不是 `msg--assistant`）：与拆分前 DOM 逐字一致 */
const rootClass = computed(() =>
  props.pending ? "msg--pending" : `msg--${role.value}`
);

/** 思考态头像不带修饰类（原实现如此）；错误态换成警示色 */
const avatarClass = computed(() =>
  props.pending ? "" : `msg__avatar--${role.value}`
);

const headLabel = computed(() =>
  props.pending ? "账本精灵" : roleLabel(role.value)
);

const icon = computed(() =>
  role.value === "error" ? WarningFilled : MagicStick
);
</script>

<style lang="scss" scoped>
@use "@/style/breakpoints" as bp;

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
  font-size: var(--text-label);
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

@keyframes chat-ellipsis {
  0% {
    clip-path: inset(0 100% 0 0);
  }

  100% {
    clip-path: inset(0 0 0 0);
  }
}

@include bp.below("md") {
  .msg {
    max-width: 92%;
  }
}
</style>
