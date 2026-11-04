<!--
  额度通栏（#980 拆分产物）：三态（正常 / 紧张 / 用尽）。
  极简通栏，弱化存在感，聚焦「粘贴区」与「开始识别」——所以无背景无边框，
  纯文字分层留白（图标弱色 / 说明次要色 / 数字等宽品牌色），用空间代替色块。

  三态的派生量（文案 / 类名 / 图标）由 useOcrQuota 计算，本组件只负责画：
  阈值改一处即可，不必在模板里再写一遍 `<= 2`。
-->
<template>
  <div class="usage-banner" :class="stateClass">
    <IconifyIconOffline class="usage-banner__icon" :icon="icon" />
    <span class="usage-banner__label">今日 AI 导入额度剩余</span>
    <span class="usage-banner__count">
      <!-- :key 触发动画：额度变化时数字轻微跳动，直给「扣了一次额度」的反馈 -->
      <strong :key="remaining">{{ remaining }}</strong> / {{ quota }} 次
    </span>
    <span v-if="hint" class="usage-banner__hint">{{ hint }}</span>
  </div>
</template>

<script setup lang="ts">
import { Icon as IconifyIconOffline } from "@iconify/vue";

defineOptions({ name: "OcrUsageBanner" });

defineProps<{
  /** 今日剩余次数 */
  remaining: number;
  /** 今日总额度 */
  quota: number;
  /** 状态类名（is-low / is-used-up / 空串） */
  stateClass: string;
  /** 图标名（ep:magic-stick / ep:bell / ep:warning） */
  icon: string;
  /** 额外提示（额度紧张 / 已用尽），正常态为空串 */
  hint: string;
}>();
</script>

<style lang="scss" scoped>
/* 额度数字跳动：扣除次数时轻微缩放反馈 */
@keyframes usage-pop {
  0% {
    transform: scale(1);
  }

  50% {
    transform: scale(1.18);
  }

  100% {
    transform: scale(1);
  }
}

/* 额度提示：无背景无边框，纯文字分层留白（图标 --text-tertiary / 说明 --text-secondary /
   数字等宽加粗 --brand-700），用空间代替色块，高级感来自留白 */
.usage-banner {
  display: flex;
  gap: var(--space-2);
  align-items: baseline;
  margin-bottom: var(--space-standard);
  transition: color 0.2s ease;

  &__icon {
    display: inline-flex;
    flex-shrink: 0;
    align-self: center;
    font-size: var(--text-small);
    color: var(--text-tertiary-ink);
  }

  &__label {
    font-size: var(--text-label);
    color: var(--text-secondary);
  }

  &__count {
    font-size: var(--text-small);
    color: var(--text-secondary);

    strong {
      display: inline-block;
      font-family: var(--font-mono);
      font-size: var(--text-mono-small);
      font-weight: 700;
      font-variant-numeric: tabular-nums;
      color: var(--brand-700);
      animation: usage-pop 0.2s ease; /* :key 变化时重放：额度扣除的微小「跳动」 */
    }
  }

  &__hint {
    flex-shrink: 0;
    margin-left: auto;
    font-size: var(--text-label);
    color: var(--text-tertiary-ink);
  }

  /* 额度紧张：仅数字/图标变色，不新增背景块 */
  &.is-low .usage-banner__count strong {
    color: var(--text-primary);
  }

  /* 额度用尽：数字/提示变危险色，不新增背景块 */
  &.is-used-up {
    .usage-banner__count strong,
    .usage-banner__hint {
      color: var(--color-danger);
    }
  }
}
</style>
