<script setup lang="ts">
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
  <div class="step3-right">
    <TableControls />

    <div class="table-wrapper">
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
        <!-- #2838：表头与行操作都靠右（align="right" + flex-end）。原先表头居中、单元格
             内容居中，行操作只有「忽略」一个按钮时会孤零零浮在 120px 列的正中；多一个
             「补全」又整体左移，扫视时像没对齐。两边钉同一条右边缘后，位置与按钮个数无关。 -->
        <el-table-column label="操作" width="120" align="right" fixed="right">
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

/* 操作列：默认低存在感，hover 整行时浮现（design.md「表格禁止每行常驻操作按钮」例外操作列）。
   右对齐而非居中（#2838）：行操作有两个（补全 / 忽略），只有「忽略」时居中会让它在
   120px 列里孤零零浮在中间、且同一列内 x 位置随按钮个数跳动——扫视时像没对齐。
   固定贴右后，忽略的位置与有没有补全无关。 */
.row-actions {
  display: flex;
  gap: 8px;
  align-items: center;
  justify-content: flex-end;
  opacity: 0;
  transition: opacity 0.15s;
}

/* Element Plus 给相邻按钮加了 margin-left: 12px，与 gap 叠加会变成 20px 的不等距；
   这里统一交给 gap 管 */
.row-actions :deep(.el-button + .el-button) {
  margin-left: 0;
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
