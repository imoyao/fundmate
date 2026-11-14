<!--
  空态：能力目录（功能型空态，不是营销落地页）。

  2026-11 改版要点（原版是「两行大标题 + 品牌渐变词 + 3 个示例块」）：
  - 去掉口号式文案：这页是工作台，第一屏该回答「我能查什么」，不是讲品牌故事；
  - 3 个示例 → 8 项能力目录：与后端 10 个工具对齐（见 agentQuickActions.ts），
    空态成为一次性的能力导航，用后即消失（有对话就不占地方）；
  - 每项都是 button（点一下直接发问、键盘可达、有焦点环），不是装饰文案；
  - 不再用 `min-height: calc(100vh - 260px)` 猜视口高——那个魔法数字在 375px 高
    屏上把内容顶到输入区下面（实测第三条示例被 dock 压住）。改自然流 + 上下留白。
-->
<template>
  <div class="chat-hero">
    <div class="chat-hero__intro">
      <h2 class="chat-hero__title">问一句，我把账户里的事实查给你</h2>
      <p class="chat-hero__desc">
        只读查询，不改任何数据；不预测涨跌，不给买卖建议。
      </p>
    </div>

    <p class="chat-hero__label">试着问一句</p>

    <div class="chat-hero__grid">
      <button
        v-for="cap in capabilities"
        :key="cap.key"
        type="button"
        class="chat-cap"
        :data-cap="cap.key"
        @click="emit('ask', cap.ask)"
      >
        <el-icon class="chat-cap__icon">
          <component :is="cap.icon" />
        </el-icon>
        <span class="chat-cap__body">
          <span class="chat-cap__label">{{ cap.label }}</span>
          <span class="chat-cap__hint">{{ cap.hint }}</span>
        </span>
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import type { AgentCapability } from "../agentQuickActions";

defineOptions({ name: "AgentCapabilityGrid" });

defineProps<{
  /** 能力目录（唯一来源见 agentQuickActions.ts 的 AGENT_CAPABILITIES） */
  capabilities: readonly AgentCapability[];
}>();

const emit = defineEmits<{
  (e: "ask", question: string): void;
}>();
</script>

<style lang="scss" scoped>
@use "@/style/breakpoints" as bp;

.chat-hero {
  display: flex;
  flex-direction: column;
  gap: var(--space-compact);
  padding: clamp(8px, 3vh, 32px) 0 var(--space-standard);
}

.chat-hero__intro {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}

.chat-hero__title {
  margin: 0;
  font-size: var(--text-heading);
  font-weight: 600;
  line-height: 1.45;
  color: var(--text-primary);
}

.chat-hero__desc {
  margin: 0;
  font-size: var(--text-small);
  line-height: 1.6;
  color: var(--text-secondary);
}

.chat-hero__label {
  margin: var(--space-2) 0 0;
  font-size: var(--text-label);
  color: var(--text-tertiary);
}

/* 目录：≥sm 两列（一行两项，扫读快、不做成「设置菜单」），窄屏一列 */
.chat-hero__grid {
  display: grid;
  grid-template-columns: 1fr;
  gap: var(--space-2);

  @include bp.above("sm") {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

.chat-cap {
  display: flex;
  gap: var(--space-3);
  align-items: flex-start;
  padding: 12px 14px;
  font-family: inherit;
  text-align: left;
  cursor: pointer;
  background-color: transparent;
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
  transition:
    background-color 0.15s ease,
    border-color 0.15s ease;

  &:hover {
    background-color: var(--bg-soft);
    border-color: var(--border-default);
  }

  &:focus-visible {
    outline: none;
    box-shadow: var(--focus-ring);
  }
}

.chat-cap__icon {
  flex: 0 0 auto;
  margin-top: 2px;
  font-size: var(--text-body);
  color: var(--brand-700);
}

.chat-cap__body {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}

.chat-cap__label {
  font-size: var(--text-small);
  font-weight: 600;
  color: var(--text-primary);
}

.chat-cap__hint {
  font-size: var(--text-label);
  line-height: 1.5;
  color: var(--text-tertiary);
}

@include bp.below("md") {
  .chat-hero__title {
    font-size: var(--text-body);
  }
}
</style>
