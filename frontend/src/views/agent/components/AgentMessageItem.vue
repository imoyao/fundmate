<!--
  单条对话消息。三态渲染：
  - clarify / 降级：纯文本；
  - result（#1712 结构化）：结论加粗置顶 / 明细文本 / 行级盈亏表（涨红跌绿）/ 风险提示弱化，
    blocks 缺失（后端契约漂移降级）回退纯文本，两态互斥；
  - error：服务提示。
  另带 `pending` 变体（思考中）——它复用 `.msg*` 样式，故不做成独立组件。

  2026-11 改版（去掉「demo 感」的关键一步）：
  - **助手回复不再套气泡**。旧版每条助手消息都是「头像 + 角色名 + 灰底圆角气泡」，
    一条结构化回答被塞进气泡 78% 宽度里，表格挤成豆腐块——读起来像聊天插件截图，
    而不像一份查数结果。现在助手侧是无框的「答案块」占满消息列，表格拿到整列宽度。
  - **只有用户发言是气泡**（品牌色、右对齐）：对话里唯一的「人」的痕迹，视觉重心也就落在提问上。
  - 角色标签只在助手侧保留一个 20px 徽标行（它是「这堆数字是机器查的」的唯一提示），
    用户侧不重复「我」。
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

    <!-- 思考态只有一行提示：停止动作收口到输入区复合按钮（#1714 UI 复核） -->
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
    /** 思考中（与消息共用 .msg* 样式，故同组件不同变体） */
    pending?: boolean;
  }>(),
  { message: null, pending: false }
);

/** 思考态在语义上属于助手一方（角色标签 / 头像都按 assistant 走） */
const role = computed<ChatMessage["role"]>(
  () => props.message?.role ?? "assistant"
);

/** 根类名：pending 保留独立类名（与拆分前 DOM 逐字一致） */
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

.msg {
  display: flex;
  flex-direction: column;
  gap: 4px;
  width: 100%;
  margin-bottom: var(--space-5);
}

/* 用户：气泡右对齐，收窄行宽（提问短，不需要整列） */
.msg--user {
  align-items: flex-end;

  .msg__bubble {
    max-width: 78%;
    color: var(--text-inverse);
    background-color: var(--brand-solid);
    border-color: transparent;
    border-radius: var(--radius-lg) var(--radius-lg) var(--radius-sm)
      var(--radius-lg);
  }
}

.msg--assistant,
.msg--pending,
.msg--error {
  align-items: flex-start;
}

/* 助手答案块：无框、占满消息列——结构化表格才有地方铺开 */
.msg--assistant .msg__bubble {
  max-width: 100%;
  padding: 0;
  background: none;
  border: 0;
}

.msg__head {
  display: flex;
  gap: var(--space-2);
  align-items: center;
  height: 20px;
}

.msg__avatar {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 20px;
  height: 20px;
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
  max-width: 100%;
  padding: var(--space-3) var(--space-compact);
  font-size: var(--text-body);
  line-height: 1.75;
  color: var(--text-primary);
  overflow-wrap: break-word;
  white-space: pre-wrap;
  background-color: var(--bg-soft);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-lg);
}

.msg--error .msg__bubble {
  border-color: var(--color-danger);
}

.msg__bubble--pending {
  padding: 4px 10px;
  font-size: var(--text-small);
  color: var(--text-tertiary);
  background-color: var(--bg-soft);
  border-radius: var(--radius-pill);

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
  min-width: 0;

  // 块间间距（文本块 / 表格任意相邻组合），首块不加顶部外边距
  .msg__block + .msg__block,
  .msg__block + .msg__table-wrap,
  .msg__table-wrap + .msg__block {
    margin-top: var(--space-3);
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

/* 表格自带卡片：与正文区分开，横向可滚（窄屏 8 列时不撑破消息列） */
.msg__table-wrap {
  padding: 4px var(--space-3) var(--space-2);
  overflow-x: auto;
  background-color: var(--bg-card);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-md);
}

.msg__table {
  width: 100%;
  font-size: var(--text-small);
  border-collapse: collapse;

  th,
  td {
    padding: 6px 10px;
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

  tbody tr:last-child td {
    border-bottom: 0;
  }

  th:first-child,
  td:first-child {
    padding-left: 0;
    text-align: left;
  }

  th:last-child,
  td:last-child {
    padding-right: 0;
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
  margin-top: 2px;
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
  .msg--user .msg__bubble {
    max-width: 88%;
  }
}
</style>
