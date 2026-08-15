<script setup lang="ts">
import { ALLOCATION_OPTIONS } from "@/constants";
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
  blockedCount,
  filteredPagedData,
  getRowClassName,
  getCellClassName,
  handleSelectionChange,
  isAllSelected,
  isIndeterminate,
  handleHeaderCheckboxChange,
  isRowSelected,
  isRowBlocked,
  handleRowCheckboxChange,
  tableColumns,
  getFundTypeColor,
  getTypeColor,
  startEdit,
  finishEdit,
  cancelEdit,
  onRowAllocationChange,
  currentPage,
  pageSize,
  filteredTotal,
  handleSizeChange,
  handlePageChange,
  totalRows,
} = useImportWizardContext();
</script>

<template>
  <div class="step3-right">
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
              {{
                duplicatesHandled ? "恢复查看重复行" : "取消显示重复行"
              }}
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
        ><span class="legend-color legend-color--duplicate" />黄色背景：已识别的重复数据，已自动跳过，可手动勾选保留</span
      >
      <span v-if="blockedCount > 0" class="legend-item"
        ><span class="legend-color legend-color--blocked" />红色左边框：信息缺失，需补全数量或价格后可导入</span
      >
    </div>

    <div v-show="showFullTable" class="table-wrapper">
      <el-table
        :data="filteredPagedData"
        row-key="_rowKey"
        :tree-props="{
          children: 'children',
          hasChildren: 'hasChildren'
        }"
        default-expand-all
        stripe
        size="default"
        :row-class-name="getRowClassName"
        :cell-class-name="getCellClassName"
        @selection-change="handleSelectionChange"
      >
        <el-table-column width="80" fixed="left">
          <template #header>
            <el-checkbox
              v-model="isAllSelected"
              :indeterminate="isIndeterminate"
              @change="handleHeaderCheckboxChange"
            />
          </template>
          <template #default="{ row }">
            <el-tooltip
              v-if="row.is_cash_transfer"
              content="资金划转暂不支持导入"
              placement="top"
            >
              <el-checkbox :model-value="false" disabled />
            </el-tooltip>
            <el-checkbox
              v-else
              :model-value="isRowSelected(row)"
              :disabled="row.is_duplicate || row.error || isRowBlocked(row)"
              @change="(val: boolean) => handleRowCheckboxChange(row, val)"
            />

            <el-tag
              v-if="row.is_calculated"
              size="small"
              type="warning"
              class="ml-1"
              >待确认</el-tag
            >
          </template>
        </el-table-column>
        <el-table-column
          v-for="col in tableColumns"
          :key="col.prop"
          v-bind="col"
        >
          <template v-if="col.slot === 'status'" #default="{ row }">
            <el-tooltip
              v-if="row.is_duplicate"
              content="该交易已存在于系统中，默认跳过。如需强制导入，请手动勾选"
              placement="top"
            >
              <el-tag type="warning" size="small">重复</el-tag>
            </el-tooltip>
            <el-tag v-else-if="row.error" type="danger" size="small">错误</el-tag>
            <el-tag
              v-else-if="isRowBlocked(row)"
              type="info"
              size="small"
              >待补全</el-tag
            >
            <el-tag v-else type="success" size="small">正常</el-tag>
          </template>
          <template v-else-if="col.slot === 'product'" #default="{ row }">
            <div class="product-cell">
              <span class="product-name">{{
                row.name || row.symbol || "--"
              }}</span>
              <div class="product-code-row">
                <span class="product-code"># {{ row.symbol || "--" }}</span>
                <el-tag
                  v-if="row.display_type"
                  size="small"
                  :color="getFundTypeColor(row.display_type)"
                  class="type-tag-inline"
                  >{{ row.display_type }}
                </el-tag>
              </div>
            </div>
          </template>
          <template v-else-if="col.slot === 'opType'" #default="{ row }">
            <div class="op-type-cell">
              <span class="op-type-label">{{ row.op_type_label || "--" }}</span>
              <el-tag
                v-if="!row.is_merged && row.type !== 'fund'"
                :color="getTypeColor(row.type)"
                size="small"
                class="type-tag-inline"
                >{{ typeLabels[row.type] || row.type || "未知" }}
              </el-tag>
            </div>
          </template>
          <template v-else-if="col.slot === 'quantity'" #default="{ row }">
            <el-popover
              :visible="row.isEditingQty"
              placement="bottom-start"
              :width="200"
              :trigger="'manual' as any"
              :hide-after="0"
              :persistent="true"
              teleported
            >
              <div class="flex flex-col gap-2" @mousedown.stop>
                <div class="text-xs text-gray-500">
                  {{ row.symbol }} {{ row.name }} -
                  <span class="font-semibold">数量</span>
                </div>
                <el-input-number
                  ref="inputRef"
                  v-model="row.quantity"
                  size="default"
                  :precision="4"
                  :min="0"
                  class="w-full"
                  controls-position="right"
                  @vue:mounted="(el: any) => el?.input?.focus()"
                />
                <div class="flex justify-end gap-2">
                  <el-button
                    type="primary"
                    size="small"
                    @click.stop="finishEdit(row, 'quantity', true)"
                    >确认</el-button
                  >
                  <el-button
                    size="small"
                    @click.stop="cancelEdit(row, 'quantity')"
                    >取消</el-button
                  >
                </div>
              </div>
              <template #reference>
                <span
                  class="cursor-pointer hover:text-blue-500 select-none"
                  @click.stop="startEdit(row, 'quantity')"
                  @mousedown.prevent
                >
                  {{ row.quantity }}
                  <el-tag
                    v-if="row.is_calculated"
                    size="small"
                    type="warning"
                    class="ml-1"
                    >待确认</el-tag
                  >
                </span>
              </template>
            </el-popover>
          </template>
          <template v-else-if="col.slot === 'price'" #default="{ row }">
            <el-popover
              :visible="row.isEditingPrice"
              placement="bottom-start"
              :width="200"
              :trigger="'manual' as any"
              :hide-after="0"
              :persistent="true"
              teleported
            >
              <div class="flex flex-col gap-2" @mousedown.stop>
                <div class="text-xs text-gray-500">
                  {{ row.symbol }} {{ row.name }} -
                  <span class="font-semibold">价格</span>
                </div>
                <el-input-number
                  ref="inputRef"
                  v-model="row.price"
                  size="default"
                  :precision="4"
                  :min="0"
                  class="w-full"
                  controls-position="right"
                  @vue:mounted="(el: any) => el?.input?.focus()"
                />
                <div class="flex justify-end gap-2">
                  <el-button
                    type="primary"
                    size="small"
                    @click.stop="finishEdit(row, 'price', true)"
                    >确认</el-button
                  >
                  <el-button
                    size="small"
                    @click.stop="cancelEdit(row, 'price')"
                    >取消</el-button
                  >
                </div>
              </div>
              <template #reference>
                <span
                  class="cursor-pointer hover:text-blue-500 select-none"
                  @click.stop="startEdit(row, 'price')"
                  @mousedown.prevent
                >
                  {{ row.price }}
                  <el-tag
                    v-if="row.is_calculated"
                    size="small"
                    type="warning"
                    class="ml-1"
                    >待确认</el-tag
                  >
                </span>
              </template>
            </el-popover>
          </template>
          <template v-else-if="col.slot === 'allocation'" #default="{ row }">
            <el-select
              v-model="row.allocation"
              size="small"
              :disabled="row.is_cash_transfer || row.is_duplicate || row.error"
              @change="onRowAllocationChange(row)"
            >
              <el-option
                v-for="opt in ALLOCATION_OPTIONS"
                :key="opt.value"
                :label="opt.label"
                :value="opt.value"
              />
            </el-select>
          </template>
        </el-table-column>
      </el-table>

      <div
        class="pagination-bar flex items-center justify-between mt-3"
      >
        <span class="text-xs text-gray-400">共 {{ filteredTotal }} 条</span>
        <el-pagination
          v-model:current-page="currentPage"
          v-model:page-size="pageSize"
          :total="totalRows"
          :page-sizes="[10, 20, 50, 100]"
          layout="sizes, prev, pager, next"
          @size-change="handleSizeChange"
          @current-change="handlePageChange"
        />
      </div>
    </div>
  </div>
</template>

<style scoped>
.step3-right {
  flex: 1;
  min-width: 0;
  padding: 16px;
  overflow: auto;
}

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

.table-wrapper {
  width: 100%;
  overflow-x: auto;
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
  background: #fff;
  border-left: 3px solid var(--color-danger);
}

:deep(.el-table .cell) {
  padding-left: 10px;
  padding-right: 10px;
}
</style>
