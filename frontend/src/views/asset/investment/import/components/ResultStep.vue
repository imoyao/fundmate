<script setup lang="ts">
import ImportErrorSummary from "./ImportErrorSummary.vue";
import { useImportWizardContext } from "../composables/useImportWizardContext";

const {
  nothingImported,
  importedCount,
  skippedCount,
  duplicateCount,
  errorCount,
  orphanCount,
  importErrors,
  showPriceUpdateTip,
  goToTransactions,
  continueImport,
  reimport,
  goToImportGuide
} = useImportWizardContext();
</script>

<template>
  <div class="import-result">
    <template v-if="!nothingImported">
      <el-result icon="success" title="导入完成">
        <template #sub-title>
          <div class="result-summary">
            <div class="result-headline">
              <span class="result-count">{{ importedCount }}</span>
              <span class="result-count-label">笔导入成功</span>
            </div>
            <p
              v-if="
                skippedCount === 0 && duplicateCount === 0 && errorCount === 0
              "
              class="result-subtitle"
            >
              全部数据已校验通过，无重复或异常记录。
            </p>
            <p v-else class="result-subtitle">
              {{ skippedCount }} 笔跳过（重复 {{ duplicateCount }} 条 / 错误
              {{ errorCount }} 条）
            </p>

            <div
              v-if="
                orphanCount > 0 || importErrors.length > 0 || showPriceUpdateTip
              "
              class="result-detail"
            >
              <el-alert
                v-if="orphanCount > 0"
                title="部分交易数据不完整"
                type="warning"
                :closable="false"
                show-icon
              >
                <template #default>
                  <p>
                    {{ orphanCount }}
                    笔交易因缺少对应持仓记录，已作为待处理数据保存。
                  </p>
                  <p class="text-xs mt-1">
                    这些交易不会影响当前资产计算，你可以在交易流水中手动关联持仓。
                  </p>
                </template>
              </el-alert>

              <ImportErrorSummary
                v-if="importErrors.length > 0"
                title="导入过程中部分记录因以下原因被跳过"
              />

              <el-alert
                v-if="showPriceUpdateTip"
                type="info"
                :closable="false"
                :show-icon="false"
              >
                <template #default>
                  <p>你刚导入了交易记录，持仓数据已更新。</p>
                  <p class="text-xs mt-1">
                    建议现在去
                    <router-link
                      :to="{ name: 'AssetStocks' }"
                      class="text-primary"
                      >检查持仓市价</router-link
                    >
                    ，以确保资产计算准确。
                  </p>
                </template>
              </el-alert>
            </div>
          </div>
          <div class="result-actions">
            <el-button
              v-if="importedCount > 0 || orphanCount > 0"
              type="primary"
              @click="goToTransactions"
            >
              查看交易流水
            </el-button>
            <el-button @click="continueImport">继续导入</el-button>
          </div>
        </template>
      </el-result>
    </template>
    <template v-else>
      <el-result icon="info" title="导入处理完成">
        <template #sub-title>
          <p>本次无新增交易，共跳过 {{ skippedCount }} 条记录。</p>
          <ImportErrorSummary v-if="importErrors.length > 0" title="跳过原因" />
          <div class="flex gap-2 justify-center mt-6">
            <el-button type="primary" @click="reimport">重新导入</el-button>
            <el-button @click="goToImportGuide">查看导入规则</el-button>
          </div>
        </template>
      </el-result>
    </template>
  </div>
</template>

<style scoped>
.result-summary {
  display: flex;
  flex-direction: column;
  align-items: center;
  text-align: center;
}

.result-headline {
  display: flex;
  align-items: baseline;
  gap: 8px;
}

.result-count {
  font-size: 40px;
  font-weight: 700;
  line-height: 1;
  color: var(--color-success);
  font-variant-numeric: tabular-nums;
}

.result-count-label {
  font-size: var(--text-body);
  color: var(--text-secondary);
}

.result-subtitle {
  margin-top: 20px;
  font-size: var(--text-small);
  color: var(--text-secondary);
}

.result-detail {
  margin-top: var(--space-loose);
  display: flex;
  flex-direction: column;
  gap: var(--space-loose);
  width: 100%;
  max-width: 440px;
  text-align: left;
}

.result-actions {
  margin-top: var(--space-loose);
  display: flex;
  justify-content: center;
  gap: 8px;
}
</style>
