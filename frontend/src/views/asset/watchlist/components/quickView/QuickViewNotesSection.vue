<script setup lang="ts">
import type { WatchlistItem } from "@/api/watchlist";

defineProps<{
  item: WatchlistItem;
}>();

const emit = defineEmits<{
  /** 点击「编辑」→ 由页面打开备注编辑弹窗（复用 #1285 的 NotesEditorDialog） */
  "edit-notes": [item: WatchlistItem];
}>();
</script>

<template>
  <!-- 备注（可编辑） -->
  <section class="wqv-sec">
    <div class="wqv-sec__head">
      <h4 class="wqv-sec__title">备注</h4>
      <el-button text size="small" @click="emit('edit-notes', item)">
        编辑
      </el-button>
    </div>
    <p v-if="item.notes" class="wqv-notes">{{ item.notes }}</p>
    <p v-else class="wqv-empty">暂无备注</p>
  </section>
</template>

<style scoped lang="scss">
@use "./wqv-base";

.wqv-notes {
  margin: 0;
  font-size: var(--text-label);
  line-height: 1.5;
  color: var(--text-secondary);
  word-break: break-word;
  white-space: pre-wrap;
}
</style>
