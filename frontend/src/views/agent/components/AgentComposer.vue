<!--
  底部输入 dock（#980 拆分产物）：能力 chips + 状态文案 + 胶囊输入 + 发送/停止复合按钮。
  「页面级滚动 + 本块 sticky 贴底」（#1714 复核）：既保住输入区常驻底部，
  又只留一条滚动条（外层 el-scrollbar）。必须给不透明底色，否则消息会从下面透出来。

  两个刻意的设计（改动前先读 index.vue 的历史注释）：
  1. **发送与停止是同一个按钮**：思考中不发禁用、而是就地换成方块停止态，
     aria-label / title 同步（页面任何时刻只有一个「发送|停止」按钮）；
  2. **思考中不锁输入框**：可以先把下一句打好，本轮结束立刻能发。
-->
<template>
  <div class="chat-dock">
    <!-- 状态文案与能力 chips 同行：贴近输入区，不再在页面顶部另起一条「工具栏」 -->
    <div class="chat-dock__bar">
      <!-- 状态文案靠左：右下角有全局「记一笔」FAB 常驻，文案放右侧会被压住 -->
      <span class="chat-dock__status">{{ statusText }}</span>
      <div class="chat-quick">
        <button
          v-for="q in actions"
          :key="q.label"
          type="button"
          class="chat-quick__chip"
          :disabled="pending"
          @click="emit('ask', q.ask)"
        >
          <el-icon><component :is="q.icon" /></el-icon>
          <span>{{ q.label }}</span>
        </button>
      </div>
    </div>

    <div class="chat-input-row">
      <div class="chat-input-pill">
        <el-input
          ref="taRef"
          v-model="model"
          type="textarea"
          :rows="1"
          :autosize="{ minRows: 1, maxRows: 4 }"
          placeholder="例如：我最近半年表现怎么样？（Enter 发送，Shift+Enter 换行）"
          @keydown="onKeydown"
        />
      </div>
      <el-button
        type="primary"
        circle
        class="chat-send"
        :aria-label="pending ? '停止' : '发送'"
        :title="pending ? '停止分析（Esc）' : '发送（Enter）'"
        :disabled="sendDisabled"
        @click="onSendClick"
      >
        <span v-if="pending" class="chat-send__stop-glyph" aria-hidden="true" />
        <el-icon v-else><ArrowUp /></el-icon>
      </el-button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from "vue";
import { ArrowUp } from "@element-plus/icons-vue";
import type { AgentQuickAction } from "../agentQuickActions";

defineOptions({ name: "AgentComposer" });

const model = defineModel<string>({ required: true });

const props = defineProps<{
  /** 思考中：chips 禁用、复合按钮换成停止态 */
  pending: boolean;
  /** 复合按钮是否不可点（空闲=输入为空；思考中=abort 收尾间隙防连点） */
  sendDisabled: boolean;
  /** 状态一句话（用户视角，不外显内部机制） */
  statusText: string;
  /** 能力快捷 chips */
  actions: readonly AgentQuickAction[];
}>();

const emit = defineEmits<{
  /** 发送输入框里的内容（父层负责清空输入并真正发请求） */
  (e: "submit"): void;
  /** 从 chip 直接发一句话（发出的同时**不清空**用户已经打好的草稿） */
  (e: "ask", question: string): void;
  /** 停止当前分析 */
  (e: "stop"): void;
}>();

const taRef = ref<{ focus: () => void } | null>(null);

function onKeydown(e: KeyboardEvent): void {
  // 思考中 Esc = 停止（与按钮 title 提示一致）：textarea 里 Esc 无默认行为，不抢任何输入
  if (e.key === "Escape" && props.pending) {
    e.preventDefault();
    emit("stop");
    return;
  }
  if (e.key !== "Enter" || e.shiftKey) return;
  // 中文输入法组词期间的 Enter 是确认候选词，不能当发送
  if (e.isComposing) return;
  e.preventDefault();
  emit("submit");
}

/** 复合按钮点击（#1714 UI 复核）：一按钮两态——思考中点是停止，空闲才是发送 */
function onSendClick(): void {
  if (props.pending) {
    emit("stop");
    return;
  }
  emit("submit");
}

/** 供父层在一轮结束后把焦点还给输入框（原实现写在 send 的 finally 里） */
function focus(): void {
  taRef.value?.focus();
}

defineExpose({ focus });
</script>

<style lang="scss" scoped>
// —— 底部 dock：能力快捷 chips + 胶囊输入 + 圆形发送 ——
// 「页面级滚动 + 本块 sticky 贴底」（#1714 复核）：既保住输入区常驻底部，
// 又只留一条滚动条。必须给不透明底色——否则消息会从 dock 下面透出来
.chat-dock {
  position: sticky;
  bottom: 0;
  z-index: 2;
  display: flex;
  flex-direction: column;
  gap: var(--space-2);

  /* 本页已在 FAB 隐藏清单内（constants/fab.ts 的 /agent），故**不再**预留安全区——
     预留会让输入区白白短掉 88px。⚠️ 若将来把它从清单摘掉，必须同时恢复
     `padding-right: var(--layout-fab-safe)`，否则发送按钮会被 FAB 压住（#1773 实测） */
  padding: var(--space-2) 0 var(--space-standard);
  background-color: var(--bg-page);
  border-top: 1px solid var(--border-subtle);
}

/* 状态文案与 chips 同行（#1714 UI 复核）：原来这条文案长在卡片顶部的工具栏里，
   既是「页头 + 工具栏」双层头部的一半，也离它描述的操作很远 */
.chat-dock__bar {
  display: flex;
  gap: var(--space-compact);
  align-items: center;
  min-width: 0;
}

.chat-dock__status {
  flex: 0 0 auto;
  font-size: var(--text-small);
  color: var(--text-secondary);
  white-space: nowrap;
}

.chat-quick {
  display: flex;
  flex: 1;
  gap: var(--space-2);
  min-width: 0; // 与状态文案同行：chips 让位收缩，靠横向滚动兜住溢出
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

.chat-input-row {
  display: flex;
  gap: var(--space-2);
  align-items: flex-end;
}

.chat-input-pill {
  /* 胶囊即焦点容器：输入框自身的底色 / 边框全部让位（透明），
     焦点表达完全交给下面的 &:focus-within —— 这样整块只有一个环（#1714 / #1772）。
     视觉参数走 element-plus.scss「输入基线」的 --input-* 令牌，不再 :deep。 */
  --input-bg: transparent;
  --input-border-color: transparent;
  --input-focus-shadow: none;
  --input-radius: var(--radius-pill);
  --input-textarea-padding: 4px 8px;
  --input-textarea-resize: none;

  flex: 1;
  padding: 5px 8px 5px 18px;
  background-color: var(--bg-card);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-pill);
  transition:
    border-color 0.15s ease,
    box-shadow 0.15s ease;

  /* 焦点样式**只画一次**（#1714 复核）：此前是「border 变红 + --focus-ring 双段阴影」叠加，
     视觉上就是内外好几圈线。这里让 border 让位给焦点环（透明），只留干净的一环。
     gap 色取 --bg-card 与胶囊底色同色，实际观感是一条 4px 品牌色环。
     内部 textarea 的静态描边 / :focus 描边由上面的令牌清空，
     否则 EP 的 `0 0 0 1px … inset` 会在胶囊里再描一圈（「很奇怪的外圈」根因）。 */
  &:focus-within {
    border-color: transparent;
    box-shadow: var(--focus-ring);
  }
}

.chat-send {
  flex: 0 0 auto;
  width: 44px;
  height: 44px;

  // 主按钮物理反馈（design.md「按钮物理反馈」）：按下有「被吸进去」的手感。
  // 发送 / 停止两态共用同一按钮：只换图标，不换底色、不换尺寸、不换位置（#1714 UI 复核）——
  // 一旦变色或换位，用户会以为「冒出了另一个按钮」，与「发送键就地变停止」的直觉相反
  &:active {
    transform: translateY(1px);
  }
}

// 停止方块：12px 圆角方块 + currentColor（跟随按钮文字色 --text-inverse，两主题恒为白，
// 落在 --brand-solid 实底 4.92:1，达 WCAG AA 图形 3:1）。不复用图标库的 VideoPause——
// 双竖线是「暂停」语义，方块才是「停止」
.chat-send__stop-glyph {
  width: 12px;
  height: 12px;
  background-color: currentColor;
  border-radius: 2px;
}
</style>
