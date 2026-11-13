<template>
  <!--
    统一四态容器。旧页面所有 loader 都是 catch 后置空，加载失败与「真的没有待办」
    渲染得一模一样，用户会把网络错误当成「已经处理完了」。
    这里把加载 / 失败 / 空 / 正常分开，并给失败态一个可点的下一步。
  -->
  <div class="recon-state">
    <div
      v-if="loading"
      class="recon-state__line"
      role="status"
      aria-live="polite"
    >
      <span class="recon-state__spinner" aria-hidden="true" />
      正在检查账上记录…
    </div>

    <div
      v-else-if="error"
      class="recon-state__line recon-state__line--error"
      role="alert"
    >
      <span>{{ error }}</span>
      <el-button size="small" @click="emit('retry')">重新加载</el-button>
    </div>

    <div v-else-if="empty" class="recon-state__empty" role="status">
      <slot name="empty">
        <p class="recon-state__empty-title">{{ emptyTitle }}</p>
        <p class="recon-state__empty-hint">{{ emptyHint }}</p>
      </slot>
    </div>

    <slot v-else />
  </div>
</template>

<script setup lang="ts">
defineOptions({ name: "ReconStatusState" });

withDefaults(
  defineProps<{
    loading?: boolean;
    /** 加载失败原因；为空串 / null 表示没有错误 */
    error?: string | null;
    empty?: boolean;
    emptyTitle?: string;
    emptyHint?: string;
  }>(),
  {
    loading: false,
    error: null,
    empty: false,
    emptyTitle: "这一类现在没有待办",
    emptyHint: "账上记录都核对过了。"
  }
);

const emit = defineEmits<{ retry: [] }>();
</script>

<style scoped>
.recon-state__line {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2);
  align-items: center;
  padding: var(--space-compact) var(--space-standard);
  font-size: var(--text-label);
  color: var(--text-secondary);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-sm);
}

.recon-state__line--error {
  color: var(--color-danger-ink);
  border-color: var(--color-danger-30);
}

.recon-state__spinner {
  width: 12px;
  height: 12px;
  border: 2px solid var(--border-default);
  border-top-color: var(--brand-solid);
  border-radius: 50%;
  animation: recon-spin 0.8s linear infinite;
}

.recon-state__empty {
  padding: var(--space-standard);
  text-align: center;
}

.recon-state__empty-title {
  margin: 0 0 6px;
  font-size: var(--text-body);
  font-weight: 600;
  color: var(--text-primary);
}

.recon-state__empty-hint {
  margin: 0;
  font-size: var(--text-label);
  line-height: 1.7;
  color: var(--text-tertiary-ink);
}

@keyframes recon-spin {
  to {
    transform: rotate(360deg);
  }
}

@media (prefers-reduced-motion: reduce) {
  .recon-state__spinner {
    animation: none;
  }
}
</style>
