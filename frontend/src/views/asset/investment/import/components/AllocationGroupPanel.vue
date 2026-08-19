<script setup lang="ts">
import { computed } from "vue";
import { ALLOCATION_OPTIONS } from "@/constants";
import { useImportWizardContext } from "../composables/useImportWizardContext";

const {
  selectedCount,
  batchSetAllocation,
  currentAllocationGroups,
  applyAllocationGroupSetting
} = useImportWizardContext();

const hasContent = computed(
  () =>
    selectedCount.value > 0 ||
    Object.keys(currentAllocationGroups.value).length > 0
);
</script>

<template>
  <div v-if="hasContent" class="allocation-group-panel">
    <div class="allocation-group-header">
      <span class="font-weight-500">配置目标</span>
    </div>
    <div v-if="selectedCount > 0" class="allocation-group-item">
      <div class="allocation-group-info">
        <span class="allocation-group-label">已选行批量设置</span>
        <el-tag size="small" type="primary">{{ selectedCount }} 条已选</el-tag>
      </div>
      <el-select
        model-value=""
        placeholder="选择配置目标"
        size="small"
        style="width: 140px"
        @change="(val: string) => batchSetAllocation(val)"
      >
        <el-option
          v-for="opt in ALLOCATION_OPTIONS"
          :key="opt.value"
          :label="opt.label"
          :value="opt.value"
        />
      </el-select>
    </div>
    <div class="allocation-group-list">
      <div
        v-for="(group, key) in currentAllocationGroups"
        :key="key"
        class="allocation-group-item"
      >
        <div class="allocation-group-info">
          <span class="allocation-group-label">{{ group.label }}</span>
          <el-tag size="small" type="info">{{ group.count }} 条</el-tag>
        </div>
        <el-select
          :model-value="group.currentAllocation"
          size="small"
          style="width: 140px"
          @change="(val: string) => applyAllocationGroupSetting(group, val)"
        >
          <el-option
            v-for="opt in ALLOCATION_OPTIONS"
            :key="opt.value"
            :label="opt.label"
            :value="opt.value"
          />
        </el-select>
      </div>
    </div>
  </div>
  <div v-else class="allocation-group-empty">
    所有数据已手动设置配置目标，无需分组调整
  </div>
</template>

<style scoped>
.allocation-group-panel {
  display: flex;
  flex-direction: column;
  padding: 14px 16px;
  background: var(--bg-card);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
  min-width: 0;
}

.allocation-group-panel :deep(.allocation-group-list),
.allocation-group-panel :deep(.allocation-group-item) {
  width: 100%;
}

.allocation-group-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 10px;
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
}

.allocation-group-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.allocation-group-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 8px;
  border: 1px solid var(--border-default);
  border-radius: 6px;
  transition: border-color 0.2s;
}

.allocation-group-item:hover {
  border-color: var(--color-primary);
}

.allocation-group-info {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.allocation-group-label {
  font-size: 12px;
  font-weight: 500;
  color: var(--text-primary);
}

.allocation-group-empty {
  padding: 6px 0;
  font-size: 12px;
  color: var(--text-tertiary);
  text-align: center;
}
</style>
