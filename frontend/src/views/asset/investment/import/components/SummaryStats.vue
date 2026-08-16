<script setup lang="ts">
import { useImportWizardContext } from "../composables/useImportWizardContext";

const { validRowsCount, duplicateCount, blockedCount, errorCount } =
  useImportWizardContext();
</script>

<template>
  <div class="summary-panel">
    <div class="summary-cards">
      <div class="summary-card summary-card--success">
        <div class="summary-card-header">
          <span class="summary-card-title">
            已校验
            <el-badge
              :value="validRowsCount"
              :type="validRowsCount > 0 ? 'success' : 'info'"
              class="summary-badge"
            />
          </span>
        </div>
        <div class="summary-card-body">
          <p>代码已匹配、字段完整、无重复，可直接导入</p>
        </div>
      </div>
      <div v-if="duplicateCount > 0" class="summary-card summary-card--warning">
        <div class="summary-card-header">
          <span class="summary-card-title"
            >重复项
            <el-badge
              :value="duplicateCount"
              type="warning"
              class="summary-badge"
          /></span>
        </div>
      </div>
      <div
        v-if="blockedCount > 0 || errorCount > 0"
        class="summary-card summary-card--danger"
      >
        <div class="summary-card-header">
          <span class="summary-card-title"
            >待确认
            <el-badge
              :value="blockedCount + errorCount"
              type="danger"
              class="summary-badge"
          /></span>
        </div>
        <div class="summary-card-body">
          <p v-if="errorCount > 0">· {{ errorCount }} 条解析错误</p>
          <p>信息缺失（数量或价格为空）</p>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.summary-panel {
  display: flex;
  flex-direction: column;
}

.summary-cards {
  display: flex;
  flex-direction: row;
  flex-wrap: wrap;
  gap: 12px;
}

.summary-card {
  padding: 14px 16px;
  border: 1px solid var(--border-default);
  border-radius: 8px;
}

.summary-card--success {
  border-left: 3px solid var(--color-success);
}

.summary-card--warning {
  border-left: 3px solid var(--color-warning);
}

.summary-card--danger {
  border-left: 3px solid var(--color-danger);
}

.summary-card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 6px;
}

.summary-card-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
}

.summary-card-body p {
  margin: 0;
  font-size: 12px;
  line-height: 1.5;
  color: var(--text-tertiary);
}

.summary-badge {
  margin-left: 4px;
}
</style>
