<script setup lang="ts">
import { useImportWizardContext } from "../composables/useImportWizardContext";

const {
  tableStatusFilter,
  showProblemOnly,
  tableFilterKeyword,
  tableTypeFilter,
  typeLabels,
  duplicateCount,
  duplicatesHandled,
  deselectAllDuplicates,
  toggleFullTable,
  showFullTable,
  blockedCount
} = useImportWizardContext();
</script>

<template>
  <div class="table-controls">
    <div class="flex items-center gap-4 flex-wrap">
      <el-select
        v-model="tableStatusFilter"
        placeholder="按状态筛选"
        size="small"
        style="width: 130px"
        clearable
      >
        <el-option label="全部" value="" />
        <el-option label="待补全" value="blocked" />
        <el-option label="重复" value="duplicate" />
        <el-option label="错误" value="error" />
        <el-option label="正常" value="normal" />
      </el-select>
      <el-switch
        v-model="showProblemOnly"
        active-text="只看问题数据"
        inactive-text="全部数据"
      />
      <el-input
        v-model="tableFilterKeyword"
        placeholder="搜索代码或名称"
        size="small"
        style="width: 200px"
        clearable
      />
      <el-select
        v-model="tableTypeFilter"
        placeholder="按类型筛选"
        size="small"
        style="width: 140px"
        clearable
        multiple
        collapse-tags
        collapse-tags-tooltip
      >
        <el-option
          v-for="(label, key) in typeLabels"
          :key="key"
          :label="label"
          :value="key"
        />
      </el-select>
    </div>
    <div class="flex items-center gap-2">
      <el-tooltip
        content="请切换到“只看问题数据”视图后使用"
        :disabled="showProblemOnly"
      >
        <span>
          <el-button
            v-if="duplicateCount > 0"
            size="small"
            :type="duplicatesHandled ? 'warning' : ''"
            :disabled="!showProblemOnly"
            @click="deselectAllDuplicates"
          >
            {{ duplicatesHandled ? "恢复查看重复行" : "取消显示重复行" }}
          </el-button>
        </span>
      </el-tooltip>
      <el-button link @click="toggleFullTable">
        <IconifyIconOffline
          :icon="showFullTable ? 'ep:arrow-up' : 'ep:arrow-down'"
        />
        {{ showFullTable ? "收起列表" : "展开列表" }}
      </el-button>
    </div>
  </div>

  <div
    v-if="showFullTable && (duplicateCount > 0 || blockedCount > 0)"
    class="highlight-legend"
  >
    <span class="legend-item"
      ><span
        class="legend-color legend-color--duplicate"
      />黄色背景：已识别的重复数据，已自动跳过，可手动勾选保留</span
    >
    <span v-if="blockedCount > 0" class="legend-item"
      ><span
        class="legend-color legend-color--blocked"
      />红色左边框：信息缺失，需补全数量或价格后可导入</span
    >
  </div>
</template>

<style scoped>
.table-controls {
  display: flex;
  gap: 12px;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}

.table-controls > div:last-child {
  flex-shrink: 0;
}

.highlight-legend {
  display: flex;
  gap: 16px;
  align-items: center;
  flex-wrap: wrap;
  padding: 8px 12px;
  margin-bottom: 8px;
  font-size: 12px;
  color: var(--text-secondary);
  background: var(--bg-card);
  border: 1px solid var(--border-default);
  border-radius: 6px;
}

.legend-item {
  display: inline-flex;
  gap: 6px;
  align-items: center;
}

.legend-color {
  display: inline-block;
  width: 14px;
  height: 14px;
  border-radius: 3px;
}

.legend-color--duplicate {
  background: rgb(250 236 216);
}

.legend-color--blocked {
  background: var(--bg-card);
  border-left: 3px solid var(--color-danger);
}
</style>
