<script setup lang="ts">
/**
 * 备注列的单元格渲染：**迁移占位 → 安静徽标 + 人话**，普通备注 → 原样。
 *
 * 从 `TransactionTable/index.vue` 拆出（`scripts/check_vue_size.mjs` 的 400 行门禁，
 * 且「迁移备注怎么显示」这条口径在表格 / 流水线 / 详情面板三处都要一致，
 * 各写一份迟早分叉）。判定逻辑在 `model.parseMigrationNote`，本组件只负责渲染。
 */
import { computed } from "vue";
import MigrationNoteTag from "./MigrationNoteTag.vue";
import { parseMigrationNote } from "./model";

const props = defineProps<{
  /** 原始备注；`null` / 空串按「无备注」处理 */
  notes?: string | null;
  /** 无备注时的占位文案（表格用 `-`，详情面板用「无备注」） */
  empty?: string;
}>();

const note = computed(() => parseMigrationNote(props.notes));
</script>

<template>
  <MigrationNoteTag v-if="note.isMigration" :note="note" />
  <span v-else class="txn-notes__text">{{ notes || empty || "-" }}</span>
</template>

<style scoped>
/* 普通备注是弱信息：不与真实数字抢注意力（与「无此语义」同一条声量规则） */
.txn-notes__text {
  color: var(--text-tertiary-ink);
}
</style>
