<template>
  <div class="starred-card" :style="{ borderTopColor: cardColor }">
    <div class="card-header">
      <span class="star-icon">⭐</span>
      <span class="asset-name">{{ item.display_name }}</span>
      <span class="asset-symbol">{{ item.symbol }}</span>
    </div>
    <div class="card-body">
      <!-- Sparkline 占位 -->
      <div v-if="item.type !== 'manager'" class="sparkline-area">
        <div class="placeholder-chart">价格走势积累中...</div>
      </div>
      <!-- 笔记摘要 -->
      <div v-if="item.notes_summary" class="notes-summary">
        💬 {{ item.notes_summary }}
      </div>
      <div class="meta-row">
        <span v-if="item.holding_days">持有 {{ item.holding_days }} 天</span>
        <span v-if="item.cycle_count">· 清仓 {{ item.cycle_count }} 次</span>
      </div>
    </div>
    <div class="card-actions">
      <slot name="actions">
        <el-button size="small" @click="$emit('view-analysis', item)"
          >清仓分析</el-button
        >
        <el-button size="small" @click="$emit('write-note', item)"
          >写笔记</el-button
        >
        <el-button
          size="small"
          type="warning"
          @click="$emit('unfavorite', item)"
          >加回自选</el-button
        >
      </slot>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from "vue";
import type { FavoriteItem } from "@/types/favorites";
import { ElButton } from "element-plus";

const props = defineProps<{ item: FavoriteItem }>();
defineEmits(["view-analysis", "write-note", "unfavorite"]);

const cardColor = computed(() => {
  switch (props.item.type) {
    case "stock":
      return "var(--card-stock)";
    case "fund":
      return "var(--card-fund)";
    case "manager":
      return "var(--card-manager)";
    case "portfolio":
      return "var(--card-portfolio)";
    default:
      return "#ccc";
  }
});
</script>

<style scoped>
.starred-card {
  padding: 0 0 12px;
  overflow: hidden;
  background: var(--bg-card);
  border-top: 5px solid;
  border-radius: 16px;
  box-shadow: 0 2px 12px rgb(0 0 0 / 4%);
  transition: all 0.3s ease;
}

.card-header {
  display: flex;
  gap: 6px;
  align-items: center;
  padding: 16px 16px 0;
}

.star-icon {
  flex-shrink: 0;
}

.asset-name {
  overflow: hidden;
  text-overflow: ellipsis;
  font-weight: 600;
  color: var(--text-primary);
  white-space: nowrap;
}

.asset-symbol {
  flex-shrink: 0;
  margin-left: 4px;
  font-size: 12px;
  color: var(--text-tertiary);
}

.sparkline-area {
  padding: 12px 16px;
}

.placeholder-chart {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 80px;
  font-size: 13px;
  color: var(--text-tertiary);
  background: var(--bg-hover);
  border-radius: 12px;
}

.notes-summary {
  padding: 8px 16px 12px;
  font-size: 14px;
  line-height: 1.6;
  color: var(--text-secondary);
}

.meta-row {
  padding: 0 16px;
  font-size: 12px;
  color: var(--text-tertiary);
}

.card-actions {
  display: flex;
  gap: 8px;
  padding: 12px 16px 0;
  border-top: 1px solid #f0f0f0;
}
</style>
