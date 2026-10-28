<template>
  <!-- 柔性 Warning Banner（§6.3）：中性信息色，非红非弹窗；点击切换到待处理域（#1259） -->
  <div
    class="workbench-banner workbench-banner--clickable"
    role="alert"
    tabindex="0"
    @keydown.enter="$emit('go')"
    @click="$emit('go')"
  >
    <IconifyIconOffline icon="ep:warning" class="workbench-banner__icon" />
    <div class="workbench-banner__text">
      有 {{ total }} 项差异待处理，点击切换到对应域处理
    </div>
  </div>
</template>

<script setup lang="ts">
import { IconifyIconOffline } from "@/components/ReIcon";

defineOptions({ name: "WorkbenchBanner" });

defineProps<{ total: number }>();

defineEmits<{ (e: "go"): void }>();
</script>

<style scoped>
/* 柔性 Warning Banner（§6.3）：中性信息色，非红非弹窗 */
.workbench-banner {
  display: flex;
  gap: 10px;
  align-items: center;
  padding: 12px 16px;
  margin-bottom: 16px;
  font-size: var(--text-small);
  color: var(--text-secondary);
  background: var(--bg-soft);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-sm);
}

/* Banner 可点击：点击切换到待处理域（#1259） */
.workbench-banner--clickable {
  cursor: pointer;
  transition:
    border-color 0.15s ease,
    background-color 0.15s ease;
}

.workbench-banner--clickable:hover {
  background: color-mix(in srgb, var(--brand-100) 40%, var(--bg-soft));
  border-color: var(--brand-400);
}

.workbench-banner__icon {
  font-size: var(--text-body);
  color: var(--brand-700);
}

.workbench-banner__text {
  flex: 1;
}
</style>
