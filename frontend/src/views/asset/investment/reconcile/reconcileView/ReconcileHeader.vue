<script setup lang="ts">
/**
 * 页头：标题 + 数据日期胶囊 + 刷新（对齐 ledgers 页头模式，#980 拆分）。
 */
import { IconifyIconOffline } from "@/components/ReIcon";
import { formatDate } from "@/utils/date";

defineProps<{
  /** E账户快照日期；空串显示 `--` */
  dataDate: string;
  refreshing: boolean;
}>();

const emit = defineEmits<{ (e: "refresh"): void }>();
</script>

<template>
  <header class="reconcile-head">
    <div class="reconcile-head__text">
      <h1 class="reconcile-head__title">E账户对账</h1>
      <p class="reconcile-head__subtitle">
        核对 E账户快照与各销售渠道的持仓差异，将快照归因到对应账户
      </p>
    </div>
    <div class="reconcile-head__actions">
      <el-tooltip
        content="E账户数据为最近一次导入的快照，如需更新请重新导入"
        placement="top"
      >
        <span class="data-date-capsule">
          <IconifyIconOffline
            icon="ep:calendar"
            class="data-date-capsule__icon"
          />
          <span>数据日期 {{ dataDate ? formatDate(dataDate) : "--" }}</span>
        </span>
      </el-tooltip>
      <el-button :loading="refreshing" @click="emit('refresh')">
        <IconifyIconOffline icon="ep:refresh" class="mr-1" />
        刷新
      </el-button>
    </div>
  </header>
</template>

<style scoped>
/* ===== 页头 ===== */
.reconcile-head {
  display: flex;
  gap: var(--space-3);
  align-items: flex-start;
  justify-content: space-between;
  margin-bottom: var(--space-standard);
}

.reconcile-head__title {
  margin: 0;
  font-size: var(--text-display);
  font-weight: 300;
  line-height: 1.3;
  color: var(--text-primary);
  letter-spacing: -0.3px;
}

.reconcile-head__subtitle {
  margin: 6px 0 0;
  font-size: var(--text-small);
  line-height: 1.5;
  color: var(--text-secondary);
}

.reconcile-head__actions {
  display: inline-flex;
  flex-shrink: 0;
  gap: var(--space-2);
  align-items: center;
}

/* 数据日期胶囊：--bg-soft 底 + 胶囊圆角（PageHeaderBar 更新时间胶囊同语言） */
.data-date-capsule {
  display: inline-flex;
  gap: 6px;
  align-items: center;
  padding: 4px 10px;
  font-size: var(--text-label);
  color: var(--text-tertiary-ink);
  white-space: nowrap;
  background: var(--bg-soft);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-pill);
}

.data-date-capsule__icon {
  font-size: var(--text-label);
}
</style>
