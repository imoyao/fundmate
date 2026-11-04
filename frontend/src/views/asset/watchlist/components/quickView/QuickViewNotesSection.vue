<script setup lang="ts">
import DrawerSection from "@/components/ProductDrawer/DrawerSection.vue";
import type { WatchlistItem } from "@/api/watchlist";

/**
 * 「备注」区块：正文可编辑，末行是添加自选日 / 分组 / 标签的元信息。
 *
 * 元信息（原「信息」区块）降为 13px 一行：标签与分组是管理元数据，不是决策信息，
 * 不值得占一个 32px 节奏的独立区块（设计 §6.2）。
 */
defineProps<{
  item: WatchlistItem | null;
  /** 已添加日 · 所属分组 · 标签；缺项由父层跳过，可能为空串 */
  metaText: string;
}>();

const emit = defineEmits<{
  /** 点击「编辑」→ 由页面打开备注编辑弹窗（复用 #1285 的 NotesEditorDialog） */
  "edit-notes": [item: WatchlistItem];
}>();
</script>

<template>
  <DrawerSection title="备注">
    <template #action>
      <el-button text size="small" @click="item && emit('edit-notes', item)">
        编辑
      </el-button>
    </template>

    <p v-if="item?.notes" class="wqv-note">{{ item.notes }}</p>
    <p v-else class="wqv-note wqv-note--empty">暂无备注</p>

    <p v-if="metaText" class="pd-hint wqv-note__meta">{{ metaText }}</p>
  </DrawerSection>
</template>

<style scoped lang="scss">
.wqv-note {
  margin: 0;
  font-size: var(--text-label);
  line-height: 1.5;
  color: var(--text-secondary);
  word-break: break-word;
  white-space: pre-wrap;
}

.wqv-note--empty {
  color: var(--text-tertiary-ink);
}

.wqv-note__meta {
  margin-top: var(--space-2);
}
</style>
