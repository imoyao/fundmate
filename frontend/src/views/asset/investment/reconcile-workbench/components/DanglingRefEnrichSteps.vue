<template>
  <!-- 准入流程显式化：「查看影响」是提交前的必经步骤，不能缩成一个次级小按钮 -->
  <ol class="dr-steps">
    <li
      v-for="(step, i) in ENRICH_STEPS"
      :key="step.title"
      class="dr-steps__item"
      :class="{
        'is-current': state.current === i + 1,
        'is-done': state.completed > i
      }"
    >
      <span class="dr-steps__no">{{ i + 1 }}</span>
      <span class="dr-steps__text">
        <span class="dr-steps__title">{{ step.title }}</span>
        <span class="dr-steps__hint">{{ step.hint }}</span>
      </span>
      <el-button
        v-if="i === 1 && state.current === 2"
        size="small"
        type="primary"
        plain
        :loading="previewing"
        :disabled="!canPreview"
        @click="emit('preview')"
      >
        查看影响
      </el-button>
      <span v-else-if="i === 1 && state.completed > 1" class="dr-steps__done">
        已查看
      </span>
    </li>
  </ol>
  <p class="dr-steps__guide">{{ state.guide }}</p>
</template>

<script setup lang="ts">
import { ENRICH_STEPS, type EnrichStepState } from "../utils/enrichSteps";

/** 补全弹窗的三步清单：纯展示 + 「查看影响」入口，不含任何写动作。 */
defineProps<{
  state: EnrichStepState;
  previewing: boolean;
  canPreview: boolean;
}>();
const emit = defineEmits<{ preview: [] }>();
</script>

<style scoped>
.dr-steps {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 0;
  margin: 8px 0 6px;
  list-style: none;
}

.dr-steps__item {
  display: flex;
  gap: 10px;
  align-items: center;
  padding: 6px 8px;
  color: var(--text-tertiary-ink);
  border: 1px solid transparent;
  border-radius: var(--radius-sm);
}

.dr-steps__item.is-current {
  color: var(--text-primary);
  background: var(--bg-soft);
  border-color: var(--border-light);
}

.dr-steps__no {
  display: inline-flex;
  flex: 0 0 20px;
  align-items: center;
  justify-content: center;
  width: 20px;
  height: 20px;
  font-size: var(--text-label);
  font-variant-numeric: tabular-nums;
  color: var(--text-tertiary-ink);
  background: var(--bg-soft);
  border-radius: 50%;
}

.is-current .dr-steps__no {
  color: var(--text-inverse);
  background: var(--color-primary-ink);
}

.is-done .dr-steps__no {
  color: var(--color-success-ink);
}

.dr-steps__text {
  display: flex;
  flex: 1;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
  font-size: var(--text-label);
  line-height: 1.5;
}

.dr-steps__title {
  font-weight: 600;
  color: inherit;
}

.dr-steps__hint {
  color: var(--text-tertiary-ink);
}

.dr-steps__done {
  font-size: var(--text-label);
  color: var(--color-success-ink);
}

.dr-steps__guide {
  margin: 0 0 10px;
  font-size: var(--text-label);
  line-height: 1.6;
  color: var(--text-secondary);
}
</style>
