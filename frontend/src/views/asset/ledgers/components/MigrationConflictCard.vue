<template>
  <div class="mig-conflict">
    <div class="mig-conflict__head">
      <span class="mig-conflict__name">
        {{ item.name }}
        <span v-if="item.symbol" class="mig-conflict__symbol">{{
          item.symbol
        }}</span>
      </span>
      <span class="mig-conflict__fields"
        >不一致字段：{{ diffFieldLabels(item) }}</span
      >
    </div>

    <!-- 源/目标数值并排对比，差异字段高亮（警示色底） -->
    <div class="mig-compare">
      <span class="mig-compare__label" />
      <span class="mig-compare__tag">来源账户</span>
      <span class="mig-compare__tag">目标账户</span>
      <template v-for="cell in compareCells(item)" :key="cell.key">
        <span class="mig-compare__label">{{ cell.label }}</span>
        <span class="mig-compare__value" :class="{ 'is-diff': cell.diff }">{{
          cell.source
        }}</span>
        <span class="mig-compare__value" :class="{ 'is-diff': cell.diff }">{{
          cell.target
        }}</span>
      </template>
    </div>

    <div class="mig-decide">
      <el-radio-group v-model="resolutionProxy" size="small">
        <el-radio
          v-for="opt in actionOptions(item)"
          :key="opt.value"
          :value="opt.value"
          >{{ opt.label }}</el-radio
        >
      </el-radio-group>
      <p v-if="actionNote(item, resolution)" class="mig-action-note">
        {{ actionNote(item, resolution) }}
      </p>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from "vue";
import type { MigrationPreviewItem, MigrationAction } from "@/api/ledger";
import {
  diffFieldLabels,
  compareCells,
  actionOptions,
  actionNote
} from "@/composables/useBatchMigration";

const props = defineProps<{
  item: MigrationPreviewItem;
  resolution: MigrationAction;
}>();

const emit = defineEmits<{
  "update:resolution": [value: MigrationAction];
}>();

const resolutionProxy = computed({
  get: () => props.resolution,
  set: (v: MigrationAction) => emit("update:resolution", v)
});
</script>

<style scoped>
/* conflict 卡片：头部 + 对比表 + 内联决议 */
.mig-conflict {
  padding: var(--space-3);
  background: var(--bg-card);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
}

.mig-conflict + .mig-conflict {
  margin-top: var(--space-2);
}

.mig-conflict__head {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2);
  align-items: baseline;
  justify-content: space-between;
  margin-bottom: var(--space-2);
}

.mig-conflict__name {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
}

.mig-conflict__symbol {
  margin-left: 6px;
  font-family: var(--font-mono);
  font-size: 12px;
  font-weight: normal;
  color: var(--text-tertiary);
}

.mig-conflict__fields {
  font-size: 12px;
  color: var(--text-secondary);
}

/* 源/目标并排对比：标签列 + 双值列；警示底色只落在数值单元格上，
   文字保持 --text-primary 保证 WCAG 对比度（--color-warning 直接做小字文字色不达标） */
.mig-compare {
  display: grid;
  grid-template-columns: 72px 1fr 1fr;
  overflow: hidden;
  background: var(--bg-warm);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-sm);
}

.mig-compare > span {
  padding: 6px 10px;
  font-size: 13px;
  line-height: 20px;
  border-top: 1px solid var(--border-subtle);
}

.mig-compare > span:nth-child(-n + 3) {
  border-top: none;
}

.mig-compare__tag {
  font-size: 12px;
  color: var(--text-secondary);
  background: var(--bg-soft);
}

.mig-compare__label {
  font-size: 12px;
  color: var(--text-tertiary);
  background: var(--bg-soft);
}

.mig-compare__value {
  font-family: var(--font-mono);
  font-variant-numeric: tabular-nums;
  color: var(--text-primary);
}

/* 差异字段高亮：警示色 20% 底 + 左侧警示色细条，亮暗色均由语义变量驱动 */
.mig-compare__value.is-diff {
  font-weight: 600;
  background: var(--color-warning-20);
  box-shadow: inset 2px 0 0 var(--color-warning);
}

/* 决议区：单选 + 当前选中态说明文案 */
.mig-decide {
  margin-top: var(--space-2);
}

.mig-action-note {
  margin: 4px 0 0;
  font-size: 12px;
  font-variant-numeric: tabular-nums;
  color: var(--text-tertiary);
}
</style>
