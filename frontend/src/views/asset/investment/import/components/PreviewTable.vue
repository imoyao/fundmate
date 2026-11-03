<script setup lang="ts">
import { nextTick, ref, watch } from "vue";
import { useImportWizardContext } from "../composables/useImportWizardContext";
import TableControls from "./TableControls.vue";
import RowSelectionCell from "./RowSelectionCell.vue";
import StatusCell from "./StatusCell.vue";
import ProductCell from "./ProductCell.vue";
import OpTypeCell from "./OpTypeCell.vue";
import EditableCell from "./EditableCell.vue";
import AllocationSelect from "./AllocationSelect.vue";

const {
  filteredPagedData,
  getRowClassName,
  getCellClassName,
  handleSelectionChange,
  isAllSelected,
  isIndeterminate,
  handleHeaderCheckboxChange,
  tableColumns,
  showFullTable,
  currentPage,
  pageSize,
  filteredTotal,
  handleSizeChange,
  handlePageChange,
  toggleIgnoreRow,
  startEdit,
  isFundMode,
  // 费用容差口径（2026-11-02）：差额被手续费解释时给提示，不判错
  isFeeExplained,
  feeDiffOf
} = useImportWizardContext();

/**
 * 表格滚动宿主的 DOM 引用。
 * 折叠（showFullTable=false）只会 v-show 内层表格，宿主自身仍在——但内容高度塌陷后
 * 浏览器会把 scrollTop clamp 回 0，靠 CSS 保不住位置，必须显式记录/还原（#783 §6.5）。
 */
const scrollHostRef = ref<HTMLElement | null>(null);
/** 折叠那一刻的滚动位置，展开时还原 */
let savedScrollTop = 0;

watch(showFullTable, (visible, wasVisible) => {
  if (wasVisible && !visible) {
    savedScrollTop = scrollHostRef.value?.scrollTop ?? 0;
    return;
  }
  if (!wasVisible && visible) {
    void nextTick(() => {
      if (scrollHostRef.value) scrollHostRef.value.scrollTop = savedScrollTop;
    });
  }
});

/**
 * 金额列提示文案（#1790 列收敛下不新增手续费列，解释线索挂 tooltip）。
 * 明说三件事：交割单发生额、其中的手续费、入库采用的成交额——避免用户
 * 看到两个数字不一致时误点「修正金额」把线索改掉。
 */
function amountHint(row: any): string {
  const diff = feeDiffOf(row);
  const gross = Number(row.quantity) * Number(row.price);
  return (
    `发生金额 ${Number(row.amount).toFixed(2)}（含手续费 ${diff.toFixed(2)}）；` +
    `成交额 ${gross.toFixed(2)} = 数量×单价。入库按成交额记、手续费单独一列`
  );
}

/** 缺数量或价格时返回对应字段名，供操作列「补全」一键定位编辑（基金模式暂不提供该捷径，修正走智能修正面板） */
function missingField(row: any): "quantity" | "price" | null {
  if (isFundMode.value) return null;
  const qtyEmpty =
    row.quantity === null || row.quantity === undefined || row.quantity === "";
  const priceEmpty =
    row.price === null || row.price === undefined || row.price === "";
  if (qtyEmpty && priceEmpty) return "quantity";
  if (qtyEmpty) return "quantity";
  if (priceEmpty) return "price";
  return null;
}
</script>

<template>
  <div ref="scrollHostRef" class="step3-right">
    <TableControls />

    <div v-show="showFullTable" class="table-wrapper">
      <el-table
        :data="filteredPagedData"
        row-key="_rowKey"
        :tree-props="{
          children: 'children',
          hasChildren: 'hasChildren'
        }"
        stripe
        size="default"
        :row-class-name="getRowClassName"
        :cell-class-name="getCellClassName"
        @selection-change="handleSelectionChange"
      >
        <el-table-column width="50" fixed="left">
          <template #header>
            <el-checkbox
              v-model="isAllSelected"
              :indeterminate="isIndeterminate"
              @change="handleHeaderCheckboxChange"
            />
          </template>
          <template #default="{ row }">
            <RowSelectionCell :row="row" />
          </template>
        </el-table-column>
        <el-table-column
          v-for="col in tableColumns"
          :key="col.prop"
          v-bind="col"
        >
          <template v-if="col.slot === 'status'" #default="{ row }">
            <StatusCell :row="row" />
          </template>
          <template v-else-if="col.slot === 'product'" #default="{ row }">
            <ProductCell :row="row" />
          </template>
          <template v-else-if="col.slot === 'opType'" #default="{ row }">
            <OpTypeCell :row="row" />
          </template>
          <template v-else-if="col.slot === 'quantity'" #default="{ row }">
            <EditableCell :row="row" field="quantity" />
          </template>
          <template v-else-if="col.slot === 'price'" #default="{ row }">
            <EditableCell :row="row" field="price" />
          </template>
          <template v-else-if="col.slot === 'amount'" #default="{ row }">
            <el-tooltip
              v-if="isFeeExplained(row)"
              :content="amountHint(row)"
              placement="top"
            >
              <EditableCell :row="row" field="amount" />
            </el-tooltip>
            <EditableCell v-else :row="row" field="amount" />
          </template>
          <template v-else-if="col.slot === 'fee'" #default="{ row }">
            <EditableCell :row="row" field="fee" />
          </template>
          <template v-else-if="col.slot === 'allocation'" #default="{ row }">
            <AllocationSelect :row="row" />
          </template>
        </el-table-column>
        <el-table-column label="操作" width="120" fixed="right">
          <template #default="{ row }">
            <div class="row-actions">
              <el-button
                v-if="missingField(row)"
                link
                type="primary"
                size="small"
                @click="startEdit(row, missingField(row)!)"
                >补全</el-button
              >
              <el-button
                v-if="!row._ignored"
                link
                type="danger"
                size="small"
                @click="toggleIgnoreRow(row)"
                >忽略</el-button
              >
              <el-button
                v-else
                link
                type="primary"
                size="small"
                @click="toggleIgnoreRow(row)"
                >恢复</el-button
              >
            </div>
          </template>
        </el-table-column>
      </el-table>

      <div class="pagination-bar flex items-center justify-between mt-3">
        <span class="text-xs text-gray-400">共 {{ filteredTotal }} 条</span>
        <!-- total 必须与左侧「共 N 条」同源（filteredTotal）：绑全量 totalRows 会让
               筛选态下 pager 显示 7 页、实际只有 2 条，点后面页码得到空表 -->
        <el-pagination
          v-model:current-page="currentPage"
          v-model:page-size="pageSize"
          :total="filteredTotal"
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

.table-wrapper {
  width: 100%;
  overflow-x: auto;
}

:deep(.el-table .cell) {
  padding-right: 10px;
  padding-left: 10px;
  font-variant-numeric: tabular-nums;
}

/* 日期列不折行：定长 10 字符加制表数字，一旦折成「2026-09- / 01」，
   视觉上会被读成两条记录（2026-11-02 截图核对发现） */
:deep(.col-date .cell) {
  white-space: nowrap;
}

/* 操作列：默认低存在感，hover 整行时浮现（design.md「表格禁止每行常驻操作按钮」例外操作列） */
.row-actions {
  display: flex;
  gap: 8px;
  justify-content: center;
  opacity: 0;
  transition: opacity 0.15s;
}

.el-table__row:hover .row-actions,
.el-table__row.row-blocked .row-actions,
/* 触屏 / 键盘也要能看到行操作（#1834） */
.el-table__row:focus-within .row-actions,
.row-actions:focus-visible {
  opacity: 1;
}

@media (hover: none) {
  .row-actions {
    opacity: 1;
  }
}
</style>
