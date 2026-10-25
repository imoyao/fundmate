<script setup lang="ts">
import { computed } from "vue";
import { Icon as IconifyIconOffline } from "@iconify/vue";
import {
  usageHintOf,
  usageIconOf,
  usageStateClassOf
} from "./recognizerImportModel";

const props = defineProps<{
  remaining: number;
  quota: number;
  occupied: boolean;
}>();

const hint = computed(() => usageHintOf(props.remaining, props.occupied));
const stateClass = computed(() =>
  usageStateClassOf(props.remaining, props.occupied)
);
const icon = computed(() => usageIconOf(props.remaining, props.occupied));
</script>

<template>
  <!-- 额度提示（三态：正常 / 紧张 / 用尽） -->
  <div class="usage-banner" :class="stateClass">
    <IconifyIconOffline class="usage-banner__icon" :icon="icon" />
    <span class="usage-banner__label">今日 AI 识别额度剩余</span>
    <span class="usage-banner__count">
      <strong :key="remaining">{{ remaining }}</strong> / {{ quota }} 次
    </span>
    <span v-if="hint" class="usage-banner__hint">{{ hint }}</span>
  </div>
</template>

<style scoped lang="scss">
.usage-banner {
  display: flex;
  gap: var(--space-2);
  align-items: baseline;
  margin-bottom: var(--space-standard);

  &__icon {
    display: inline-flex;
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
      font-family: var(--font-mono);
      font-size: var(--text-mono-small);
      font-weight: 700;
      font-variant-numeric: tabular-nums;
      color: var(--brand-700);
    }
  }

  &__hint {
    margin-left: auto;
    font-size: var(--text-label);
    color: var(--text-tertiary-ink);
  }

  &.is-low .usage-banner__count strong {
    color: var(--text-primary);
  }

  &.is-used-up {
    .usage-banner__count strong,
    .usage-banner__hint {
      color: var(--color-danger);
    }
  }
}
</style>
