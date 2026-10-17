<script setup lang="ts">
import { useImportWizardContext } from "../composables/useImportWizardContext";
import { ASSET_TYPE_LABELS } from "@/constants/assetType";

const {
  showProblemOnly,
  tableFilterKeyword,
  tableTypeFilter,
  duplicateCount,
  duplicatesHandled,
  hiddenSelectedDuplicateCount,
  deselectAllDuplicates,
  toggleFullTable,
  showFullTable,
  blockedCount,
  errorCount,
  showFixPanel,
  toggleFixPanel,
  isFundMode
} = useImportWizardContext();
</script>

<template>
  <div class="table-controls">
    <div class="flex items-center gap-4 flex-wrap">
      <el-switch
        v-model="showProblemOnly"
        active-text="只看问题数据"
        inactive-text="全部数据"
      />
      <el-input
        v-model="tableFilterKeyword"
        aria-label="搜索代码或名称"
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
          v-for="(label, key) in ASSET_TYPE_LABELS"
          :key="key"
          :label="label"
          :value="key"
        />
      </el-select>
    </div>
    <div class="flex items-center gap-2 flex-wrap">
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
      <!-- #2274：显隐与勾选解耦后，隐藏但仍勾选的重复行仍会导入——给出可见提示，
           避免「看不见自己要导什么」；仅在问题视图成立（全部数据视图下重复行本就可见） -->
      <el-tooltip
        v-if="showProblemOnly && hiddenSelectedDuplicateCount > 0"
        content="这些行不出现在当前视图，但会随「已选择」一起导入；点「恢复查看重复行」可重新显示并核对"
        placement="bottom"
      >
        <el-tag type="warning" size="small" class="hidden-selected-hint">
          已有 {{ hiddenSelectedDuplicateCount }}
          条勾选的重复行被隐藏，仍将导入
        </el-tag>
      </el-tooltip>
      <el-button
        v-if="blockedCount + errorCount > 0"
        round
        size="small"
        type="warning"
        :plain="!showFixPanel"
        @click="toggleFixPanel"
      >
        <IconifyIconOffline icon="ep:magic-stick" class="mr-1" />
        智能修正
        <span class="fix-count">{{ blockedCount + errorCount }}</span>
      </el-button>
      <el-button link @click="toggleFullTable">
        <IconifyIconOffline
          :icon="showFullTable ? 'ep:arrow-up' : 'ep:arrow-down'"
        />
        {{ showFullTable ? "收起列表" : "展开列表" }}
      </el-button>
    </div>
  </div>

  <!-- 行内编辑交互说明（#1790 验收②「页面有交互说明」） -->
  <p v-if="showFullTable" class="edit-hint">
    点击{{
      isFundMode ? "份额 / 确认净值 / 金额" : "数量 / 单价 / 金额"
    }}单元格可就地修改：Enter 提交并停留、Esc 取消还原、Tab
    跳到下一格；修改数量或单价会自动重算金额
  </p>

  <p
    v-if="showFullTable && (duplicateCount > 0 || blockedCount > 0)"
    class="highlight-legend"
  >
    <span class="legend-item legend-item--duplicate"
      >黄色行：已识别重复，自动跳过，可勾选保留</span
    >
    <span v-if="blockedCount > 0" class="legend-item legend-item--blocked"
      >红色行：信息缺失，需补全数量或价格</span
    >
  </p>
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

/* #2274 隐藏勾选提示：允许在窄断面折行，不撑破控件行 */
.hidden-selected-hint {
  max-width: 240px;
  height: auto;
  line-height: 1.5;
  white-space: normal;
}

.edit-hint {
  margin: -4px 0 8px;
  font-size: 11px;
  line-height: 1.5;
  color: var(--text-tertiary-ink);
}

.highlight-legend {
  display: flex;
  flex-wrap: wrap;
  gap: 16px;
  align-items: center;
  margin: -4px 0 8px;
  font-size: 11px;
  line-height: 1.5;
  color: var(--text-tertiary-ink);
}

.legend-item {
  display: inline-flex;
  gap: 5px;
  align-items: center;
}

.legend-item::before {
  display: inline-block;
  flex-shrink: 0;
  width: 10px;
  height: 10px;
  content: "";
  border-radius: 2px;
}

.legend-item--duplicate::before {
  background: rgb(250 236 216);
}

.legend-item--blocked::before {
  background: var(--bg-card);
  border-left: 3px solid var(--color-danger);
}

.fix-count {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 16px;
  height: 16px;
  padding: 0 4px;
  margin-left: 2px;
  font-size: 11px;
  line-height: 1;
  color: var(--text-primary);
  background: var(--color-warning);
  border-radius: 8px;
}
</style>
