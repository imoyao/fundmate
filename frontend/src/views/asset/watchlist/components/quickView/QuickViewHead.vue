<script setup lang="ts">
import type { WatchlistItem } from "@/api/watchlist";

defineProps<{
  item: WatchlistItem;
  /** 组合 / 经理：不展示代码 */
  isComposite: boolean;
  compositeMeta: string;
}>();
</script>

<template>
  <!-- 头部：名称 / 代码 / 类型 / 组合分层信息 -->
  <div class="wqv-head">
    <div class="wqv-name" :title="item.display_name || item.symbol">
      {{ item.display_name || item.symbol }}
    </div>
    <div class="wqv-meta">
      <span v-if="!isComposite && item.symbol" class="wqv-code">
        {{ item.symbol }}
      </span>
      <span v-if="item.type_label" class="wqv-type">
        {{ item.type_label }}
      </span>
    </div>
    <div v-if="compositeMeta" class="wqv-meta">{{ compositeMeta }}</div>
  </div>
</template>

<style scoped lang="scss">
.wqv-head {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.wqv-name {
  font-size: var(--text-body);
  font-weight: 600;
  color: var(--text-primary);
}

.wqv-meta {
  display: flex;
  gap: 8px;
  align-items: center;
  font-size: var(--text-label);
  color: var(--text-tertiary-ink);
}
</style>
