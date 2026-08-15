<script setup lang="ts">
import { useImportWizardContext } from "../composables/useImportWizardContext";
import TableControls from "./TableControls.vue";
import RowSelectionCell from "./RowSelectionCell.vue";
import StatusCell from "./StatusCell.vue";
import ProductCell from "./ProductCell.vue";
import OpTypeCell from "./OpTypeCell.vue";
import QuantityEditCell from "./QuantityEditCell.vue";
import PriceEditCell from "./PriceEditCell.vue";
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
  totalRows,
  filteredTotal,
  handleSizeChange,
  handlePageChange
} = useImportWizardContext();
</script>

<template>
  <div class="step3-right">
    <TableControls />

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
            <QuantityEditCell :row="row" />
          </template>
          <template v-else-if="col.slot === 'price'" #default="{ row }">
            <PriceEditCell :row="row" />
          </template>
          <template v-else-if="col.slot === 'allocation'" #default="{ row }">
            <AllocationSelect :row="row" />
          </template>
        </el-table-column>
      </el-table>

      <div class="pagination-bar flex items-center justify-between mt-3">
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

.table-wrapper {
  width: 100%;
  overflow-x: auto;
}

:deep(.el-table .cell) {
  padding-left: 10px;
  padding-right: 10px;
}
</style>
