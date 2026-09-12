<script setup lang="ts">
import type { AggregationDimension } from "@/api/ledger";

/**
 * 聚合维度切换（果冻胶囊按钮组，设计语言 D13）。
 *
 * 适用于「多选一、选项数少」的紧凑选择。选项由父组件传入，
 * 使场外基金与场内证券两个下钻页复用同一交互与视觉。
 *
 * #1133：维度已由 3 个收敛为 2 个（原「按 App」本质即销售机构，与「按机构」重复）。
 */
defineOptions({ name: "AggregationDimensionTabs" });

const props = defineProps<{
  modelValue: AggregationDimension;
  options: { label: string; value: AggregationDimension }[];
}>();

const emit = defineEmits<{
  (e: "update:modelValue", value: AggregationDimension): void;
}>();

function select(value: AggregationDimension) {
  if (value === props.modelValue) return;
  emit("update:modelValue", value);
}
</script>

<template>
  <div class="dimension-tabs" role="tablist">
    <button
      v-for="opt in options"
      :key="opt.value"
      type="button"
      role="tab"
      class="dimension-capsule"
      :class="{ active: modelValue === opt.value }"
      :aria-selected="modelValue === opt.value"
      @click="select(opt.value)"
    >
      {{ opt.label }}
    </button>
  </div>
</template>

<style scoped>
@keyframes style-pop {
  0% {
    transform: scale(1);
  }

  30% {
    transform: scale(0.92);
  }

  60% {
    transform: scale(1.05);
  }

  80% {
    transform: scale(0.97);
  }

  100% {
    transform: scale(1);
  }
}

@media (prefers-reduced-motion: reduce) {
  .dimension-capsule {
    transition: none;
  }

  .dimension-capsule.active {
    animation: none;
  }
}

.dimension-tabs {
  display: inline-flex;
  gap: 8px;
}

/* 未选中：透明底 + 1px 边框；选中：品牌实心填充 + 白字（对齐参考截图的果冻胶囊） */
.dimension-capsule {
  padding: 6px 16px;
  font-family: var(--font-ui);
  font-size: 14px;
  color: var(--text-tertiary);
  cursor: pointer;
  background: transparent;
  border: 1px solid var(--border-default);
  border-radius: var(--radius-pill);
  transform: translateZ(0);

  /* 弹性动画准备：居中缩放 + 合成层，避免缩放时文字模糊 */
  transform-origin: center;
  transition:
    color 0.2s ease,
    background-color 0.2s ease,
    border-color 0.2s ease;
  will-change: transform;
}

.dimension-capsule:hover {
  color: var(--text-primary);
  border-color: var(--brand-400);
}

/* 对齐截图：选中态为品牌色实心填充（非浅底），白字，带轻投影 */
.dimension-capsule.active {
  color: var(--text-inverse);
  background: var(--brand-600, #f06b57);
  border-color: var(--brand-600, #f06b57);
  box-shadow: 0 1px 3px rgb(0 0 0 / 6%);
  animation: style-pop 0.4s cubic-bezier(0.34, 1.56, 0.64, 1);
}

.dimension-capsule:active {
  transform: scale(0.92);
}

.dimension-capsule:focus-visible {
  outline: none;
  box-shadow: var(--focus-ring);
}
</style>
