<!--
  对话页页头操作区（2026-11-26 从 index.vue 拆出，见 check_vue_size 门禁）。

  这里只放**页头右侧**的两个动作，状态与副作用仍归 index.vue：
  - 「会话记录」：一个按钮两种语义 —— ≥lg 收/展常驻左栏（disclosure），窄屏开抽屉。
    `aria-expanded` 跟着**当前形态**走，读屏才知道按下去是展开还是收起。
  - 「新对话」：左栏收起 / 窄屏时左栏自带的那枚入口没了，由这里补位。

  可发现性（2026-11-26 用户反馈「文案指向不明、看着不像按钮」）：
  - 文案「历史」→「会话记录」：明确被操作的对象是一组会话，不是浏览器历史；
  - 图标 Clock → ChatLineSquare：时钟表达「时间」而非「会话列表」；
  - `text` 无边框形态 → 有边框 + 卡片底的实体按钮：纯文字在页头右侧读起来
    像一个不重要的标签，用户不会去点；
  - 宽屏补方向 chevron（收起态指向右 = 可展开，展开态指向左 = 可收起），
    文案保持恒定，避免按钮宽度随状态抖动。窄屏是抽屉语义，不加箭头。
-->
<template>
  <div class="agent-header-actions">
    <el-button
      class="agent-header-actions__history"
      size="small"
      :aria-expanded="isWide ? String(!railCollapsed) : String(historyOpen)"
      :aria-controls="isWide ? 'agent-session-panel' : undefined"
      @click="emit('toggleHistory')"
    >
      <el-icon class="agent-header-actions__history-icon">
        <ChatLineSquare />
      </el-icon>
      会话记录
      <el-icon
        v-if="isWide"
        class="agent-header-actions__chevron"
        aria-hidden="true"
      >
        <ArrowRight v-if="railCollapsed" />
        <ArrowLeft v-else />
      </el-icon>
    </el-button>

    <el-button v-if="showNew" text size="small" @click="emit('newSession')">
      新对话
    </el-button>
  </div>
</template>

<script setup lang="ts">
import { ArrowLeft, ArrowRight, ChatLineSquare } from "@element-plus/icons-vue";

defineOptions({ name: "AgentHeaderActions" });

defineProps<{
  /** ≥lg：常驻左栏形态（按钮语义是收/展左栏，而不是开抽屉） */
  isWide: boolean;
  /** 左栏当前是否收起（决定 chevron 方向与 aria-expanded） */
  railCollapsed: boolean;
  /** 窄屏抽屉是否打开 */
  historyOpen: boolean;
  /** 是否显示「新对话」（有内容可清 且 左栏没有自带入口） */
  showNew: boolean;
}>();

const emit = defineEmits<{
  /** 宽屏 = 切换左栏收/展；窄屏 = 打开抽屉（由父级按 isWide 分流） */
  (e: "toggleHistory"): void;
  (e: "newSession"): void;
}>();
</script>

<style lang="scss" scoped>
.agent-header-actions {
  display: flex;
  gap: var(--space-2);
  align-items: center;
}

/* 「会话记录」是**实体按钮**而不是纯文字：纯 text 按钮在页头右侧只是一个
   无边界、无底色的文字串，视觉权重低于副标题，用户不会把它当控件。
   高度 28px：高于 EP small 的 24px，低于标题行的 43px，不与 32px 标题抢焦点。 */
.agent-header-actions__history {
  height: 28px;
  padding: 0 10px;
  font-size: var(--text-small);
  color: var(--text-secondary);
  background-color: var(--bg-card);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-sm);

  &:hover,
  &:focus-visible {
    color: var(--text-primary);
    background-color: var(--bg-soft);
  }

  /* 图标与文字的间距压一点，否则「会话记录」会被左右两个图标夹成等距字符流 */
  .agent-header-actions__history-icon {
    margin-right: 4px;
  }

  .agent-header-actions__chevron {
    margin-left: 4px;
    color: var(--text-tertiary);
  }
}
</style>
