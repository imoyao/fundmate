<script setup lang="ts">
import type { OcrTxnRow } from "@/api/ocr";
import type { PreviewRow } from "./recognizerImportModel";

defineProps<{
  rows: PreviewRow[];
  scenario: "txn_import" | "holding_import";
}>();
</script>

<template>
  <!-- 识别结果预览（逐行核对，不自动入库，见 #935 必带兜底） -->
  <div class="result-section">
    <div class="result-head">
      识别到 {{ rows.length }} 条，核对无误后「确认进草稿」
    </div>
    <div class="preview-scroll">
      <el-table :data="rows" size="small" stripe class="preview-table">
        <el-table-column label="代码" prop="symbol" width="110" />
        <el-table-column label="名称" prop="name" min-width="120" />
        <template v-if="scenario === 'txn_import'">
          <el-table-column label="操作" width="90">
            <template #default="{ row }">
              {{ (row as OcrTxnRow).op_type_label || row.op_type }}
            </template>
          </el-table-column>
          <el-table-column
            label="数量"
            prop="quantity"
            width="100"
            align="right"
          />
          <el-table-column
            label="金额"
            prop="amount"
            width="110"
            align="right"
          />
          <el-table-column label="日期" prop="trade_date" width="120" />
        </template>
        <template v-else>
          <el-table-column
            label="份额"
            prop="quantity"
            width="110"
            align="right"
          />
          <el-table-column
            label="成本"
            prop="price"
            width="100"
            align="right"
          />
          <el-table-column label="快照日" prop="snapshot_date" width="120" />
        </template>
        <el-table-column label="状态" width="90">
          <template #default="{ row }">
            <el-tag v-if="row.is_duplicate" size="small" type="warning"
              >重复</el-tag
            >
            <el-tag v-else-if="row.error" size="small" type="danger"
              >错误</el-tag
            >
            <el-tag v-else size="small" type="success">可入库</el-tag>
          </template>
        </el-table-column>
      </el-table>
    </div>
  </div>
</template>

<style scoped lang="scss">
.result-section {
  margin-top: var(--space-5);
}

.result-head {
  margin-bottom: var(--space-3);
  font-size: var(--text-small);
  font-weight: 500;
  color: var(--text-primary);
}

.preview-scroll {
  max-height: 280px;
  overflow-y: auto;
}
</style>
