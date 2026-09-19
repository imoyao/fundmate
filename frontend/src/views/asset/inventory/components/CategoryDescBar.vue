<template>
  <div
    class="rounded-xl p-6 flex items-start gap-3"
    :style="{ backgroundColor: 'var(--bg-soft)' }"
  >
    <IconifyIconOffline
      icon="ep:info-filled"
      class="text-xl mt-0.5 shrink-0"
      :style="{ color: 'var(--text-tertiary-ink)' }"
    />
    <p
      class="text-sm leading-relaxed"
      :style="{ color: 'var(--text-secondary)' }"
    >
      {{ desc }}
    </p>
  </div>
</template>

<script setup lang="ts">
/**
 * 大类注释卡片（全面盘点页内容区第一层）。
 *
 * 自 `views/asset/inventory/index.vue` 拆出（#955）。文案由页面按当前大类注入。
 */
import { IconifyIconOffline } from "@/components/ReIcon";

defineProps<{
  /** 当前大类的说明文案 */
  desc: string;
}>();
</script>
