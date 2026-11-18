<template>
  <!--
    一条待办 = 一件用户能动手处理的事。可见文本全部来自 utils/reconDisplay.ts 的
    翻译层：没有英文枚举、ISO 时间戳、复合主键和内部 ID。
    来源域只作右上角小标签，不再是导航维度。
  -->
  <li
    class="recon-queue__item"
    :class="[`recon-queue__item--${item.state}`, { 'is-active': active }]"
    :aria-current="active ? 'true' : undefined"
  >
    <div class="recon-queue__top">
      <el-checkbox
        v-if="selectable"
        class="recon-queue__check"
        :model-value="selected"
        :aria-label="`选中「${item.title}」`"
        @change="emit('toggle', item.id)"
      />
      <div class="recon-queue__head">
        <button
          type="button"
          class="recon-queue__title"
          @click="emit('open', item)"
        >
          {{ item.title }}
        </button>
        <span class="recon-queue__source">{{ item.sourceLabel }}</span>
        <span class="recon-queue__state" :class="`is-${item.state}`">
          {{ stateLabel }}
        </span>
      </div>
      <span v-if="item.count > 0" class="recon-queue__count">
        涉及 {{ item.count }} 条
      </span>
    </div>

    <p class="recon-queue__summary">{{ item.summary }}</p>

    <ul v-if="item.facts.length" class="recon-queue__facts">
      <li v-for="(fact, i) in item.facts" :key="`${i}-${fact}`">{{ fact }}</li>
    </ul>

    <div class="recon-queue__foot">
      <span class="recon-queue__reason">{{ item.stateReason }}</span>
      <el-button size="small" type="primary" plain @click="emit('open', item)">
        {{ item.actionLabel }}
      </el-button>
    </div>
  </li>
</template>

<script setup lang="ts">
import { computed } from "vue";
import { RECON_QUEUE_STATES } from "../constants/reconTasks";
import type { ReconQueueItem } from "../utils/reconQueue";

defineOptions({ name: "ReconQueueCard" });

const props = defineProps<{
  item: ReconQueueItem;
  active: boolean;
  /** 是否可进批量（后端判定可修且状态为「可直接处理」） */
  selectable: boolean;
  selected: boolean;
}>();

const emit = defineEmits<{
  open: [item: ReconQueueItem];
  toggle: [id: string];
}>();

const stateLabel = computed(
  () =>
    RECON_QUEUE_STATES.find(s => s.value === props.item.state)?.label ?? "待办"
);
</script>

<style scoped>
.recon-queue__item {
  padding: var(--space-compact) var(--space-standard);
  list-style: none;
  background: var(--bg-card);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-raised);
  transition: border-color 0.15s ease;
}

.recon-queue__item:hover {
  border-color: var(--border-default);
}

.recon-queue__item.is-active {
  border-color: var(--brand-300);
}

.recon-queue__top {
  display: flex;
  gap: var(--space-2);
  align-items: flex-start;
}

.recon-queue__check {
  flex: none;
  margin-top: 2px;
}

.recon-queue__head {
  display: flex;
  flex: 1 1 auto;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
  min-width: 0;
}

.recon-queue__title {
  padding: 0;
  font-family: var(--font-ui);
  font-size: var(--text-body);
  font-weight: 600;
  color: var(--text-primary);
  text-align: left;
  cursor: pointer;
  background: transparent;
  border: none;
}

.recon-queue__title:hover {
  color: var(--brand-ink);
}

.recon-queue__title:focus-visible {
  outline: none;
  border-radius: var(--radius-sm);
  box-shadow: var(--focus-ring);
}

.recon-queue__source,
.recon-queue__state,
.recon-queue__count {
  padding: 2px 8px;
  font-size: var(--text-label);
  line-height: 1.5;
  border-radius: var(--radius-pill);
}

.recon-queue__source {
  color: var(--text-tertiary-ink);
  background: var(--bg-soft);
}

.recon-queue__state {
  color: var(--text-secondary);
  background: var(--bg-soft);
}

.recon-queue__state.is-ready {
  color: var(--color-success-ink);
  background: var(--color-success-20);
}

.recon-queue__state.is-judge {
  color: var(--brand-ink);
  background: var(--brand-100);
}

.recon-queue__state.is-incomplete {
  color: var(--color-warning-ink);
  background: var(--color-warning-20);
}

.recon-queue__count {
  flex: none;
  font-variant-numeric: tabular-nums;
  color: var(--text-tertiary-ink);
}

.recon-queue__summary {
  margin: 10px 0 8px;
  font-size: var(--text-small);
  line-height: 1.7;
  color: var(--text-secondary);
}

.recon-queue__facts {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  padding: 0;
  margin: 0 0 10px;
  list-style: none;
}

.recon-queue__facts li {
  padding: 2px 8px;
  font-size: var(--text-label);
  color: var(--text-tertiary-ink);
  background: var(--bg-soft);
  border-radius: var(--radius-sm);
}

.recon-queue__foot {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2);
  align-items: center;
  justify-content: space-between;
}

.recon-queue__reason {
  font-size: var(--text-label);
  line-height: 1.6;
  color: var(--text-tertiary-ink);
}
</style>
