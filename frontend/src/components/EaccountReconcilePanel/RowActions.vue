<script setup lang="ts">
/**
 * 操作列（迁移自 reconcile/reconcileView/ReconcileRowActions.vue）。
 *
 * 三种非待处理状态只回显去向、不给操作；待处理的两颗按钮常显——操作即本表主题，
 * 不做 hover 隐藏（触屏无 hover 态时入口会彻底不可达）。
 *
 * 回显文案由 `model.resolveHint` 统一给出：状态列说「处理完了」，这里说「处理到哪儿」。
 * 此前工作台把三种状态压成一个「已处理」，与状态列互为同义词，等于没写。
 */
import type { ReconciliationItem } from "@/api/eaccount";
import { resolveHint } from "./model";

defineProps<{
  row: ReconciliationItem;
  coverLoading: boolean;
  ignoreLoading: boolean;
}>();

const emit = defineEmits<{
  (e: "cover", row: ReconciliationItem): void;
  (e: "ignore", row: ReconciliationItem): void;
}>();
</script>

<template>
  <div class="row-actions">
    <!-- 待处理：核心操作常显（本表操作即页面主题，不做 hover 隐藏） -->
    <template v-if="row.status === 'pending'">
      <el-button
        link
        size="small"
        class="btn-cover-danger"
        :loading="coverLoading"
        @click="emit('cover', row)"
      >
        归因覆盖
      </el-button>
      <el-button
        link
        size="small"
        :loading="ignoreLoading"
        @click="emit('ignore', row)"
      >
        忽略
      </el-button>
    </template>
    <!-- 已处理 / 已核对 / 已忽略：写出去向，不给操作 -->
    <span v-else class="row-actions__readonly">{{ resolveHint(row) }}</span>
  </div>
</template>

<style scoped>
/* 触屏设备无 hover 态：行内操作常显，避免入口不可达 */
@media (hover: none) {
  .row-actions {
    opacity: 1;
  }
}

/* ===== 操作列 ===== */
.row-actions {
  display: flex;
  gap: var(--space-3);
  align-items: center;
  justify-content: center;
}

.row-actions__readonly {
  font-size: var(--text-label);
  color: var(--text-tertiary-ink);
  white-space: nowrap;
}

/* 归因覆盖按钮：危险语义（覆盖 = 删除渠道原记录），危险色走
   --color-danger（design.md「危险按钮」幽灵态） */
.btn-cover-danger {
  --el-button-text-color: var(--color-danger);
  --el-button-hover-text-color: var(--color-danger);
  --el-button-hover-bg-color: var(--color-danger-20);
}
</style>

<!-- 归因覆盖确认框按钮：ElMessageBox 渲染在 body 下，scoped 样式不可达，
     需全局样式将确认按钮染为危险色（--color-danger） -->
<style>
.el-message-box .reconcile-confirm-danger.el-button--primary {
  --el-button-bg-color: var(--color-danger);
  --el-button-border-color: var(--color-danger);
  --el-button-hover-bg-color: var(--color-danger);
  --el-button-hover-border-color: var(--color-danger);
  --el-button-active-bg-color: var(--color-danger);
  --el-button-active-border-color: var(--color-danger);
}
</style>
