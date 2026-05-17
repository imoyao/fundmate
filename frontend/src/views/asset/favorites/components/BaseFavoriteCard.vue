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
        <el-button size="small" @click="$emit('view-analysis', item)">清仓分析</el-button>
        <el-button size="small" @click="$emit('write-note', item)">写笔记</el-button>
        <el-button size="small" type="warning" @click="$emit('unfavorite', item)">加回自选</el-button>
      </slot>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import type { FavoriteItem } from '@/types/favorites';
import { ElButton } from 'element-plus'

const props = defineProps<{ item: FavoriteItem }>();
defineEmits(['view-analysis', 'write-note', 'unfavorite']);

const cardColor = computed(() => {
  switch (props.item.type) {
    case 'stock': return 'var(--card-stock)';
    case 'fund': return 'var(--card-fund)';
    case 'manager': return 'var(--card-manager)';
    case 'portfolio': return 'var(--card-portfolio)';
    default: return '#ccc';
  }
});
</script>

<style scoped>
.starred-card {
  background: var(--bg-card);
  border-radius: 16px;
  padding: 0 0 12px 0;
  border-top: 5px solid;
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.04);
  transition: all 0.3s ease;
  overflow: hidden;
}
.card-header {
  padding: 16px 16px 0;
  display: flex;
  align-items: center;
  gap: 6px;
}
.star-icon {
  flex-shrink: 0;
}
.asset-name {
  font-weight: 600;
  color: var(--text-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.asset-symbol {
  font-size: 12px;
  color: var(--text-tertiary);
  margin-left: 4px;
  flex-shrink: 0;
}
.sparkline-area {
  padding: 12px 16px;
}
.placeholder-chart {
  height: 80px;
  background: var(--bg-hover);
  border-radius: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--text-tertiary);
  font-size: 13px;
}
.notes-summary {
  padding: 8px 16px 12px;
  line-height: 1.6;
  color: var(--text-secondary);
  font-size: 14px;
}
.meta-row {
  padding: 0 16px;
  font-size: 12px;
  color: var(--text-tertiary);
}
.card-actions {
  padding: 12px 16px 0;
  border-top: 1px solid #f0f0f0;
  display: flex;
  gap: 8px;
}
</style>
