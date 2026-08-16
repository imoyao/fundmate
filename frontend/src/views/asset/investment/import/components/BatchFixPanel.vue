<script setup lang="ts">
import { useImportWizardContext } from "../composables/useImportWizardContext";

const {
  blockedCount,
  errorCount,
  showBatchFix,
  toggleBatchFix,
  hasFundRecordsForNav,
  enrichingNav,
  fetchAndFillFundNav,
  fundRecordsCount,
  calculatedCount,
  confirmAllCalculated,
  problemCategories,
  isCategoryActive,
  filterByCategory,
  getCategoryDesc,
  getCategoryTagType,
  getMissingRowsByType,
  showMatchDrawer,
  batchCodeInput,
  batchFillCode,
  batchFixAmount,
  showFullTable,
  showProblemOnly,
  skipCategory
} = useImportWizardContext();
</script>

<template>
  <div v-if="blockedCount + errorCount > 0" class="batch-fix-bar">
    <el-button
      :type="showBatchFix ? '' : 'primary'"
      size="default"
      @click="toggleBatchFix"
    >
      <IconifyIconOffline icon="ep:setting" class="mr-1" />
      {{ showBatchFix ? "收起批量修正" : "批量修正问题数据" }}
    </el-button>
    <span v-if="!showBatchFix" class="batch-fix-hint"
      >{{ blockedCount + errorCount }} 条待处理</span
    >
    <el-button
      v-if="hasFundRecordsForNav"
      type="primary"
      size="default"
      :loading="enrichingNav"
      @click="fetchAndFillFundNav"
    >
      获取净值和份额（{{ fundRecordsCount }}只）
    </el-button>
    <el-button
      v-if="calculatedCount > 0"
      type="warning"
      size="default"
      @click="confirmAllCalculated"
    >
      确认所有推算数据（{{ calculatedCount }} 条）
    </el-button>
  </div>

  <div
    v-if="showBatchFix && problemCategories.length > 0"
    class="batch-fix-panel"
  >
    <div
      v-for="cat in problemCategories"
      :key="cat.key"
      class="batch-fix-group"
      :class="{
        'batch-fix-group--active': isCategoryActive(cat.key)
      }"
      @click="filterByCategory(cat.key)"
    >
      <div class="batch-fix-card">
        <div class="batch-fix-card-header">
          <div class="batch-fix-info">
            <span class="batch-fix-label">{{ cat.label }}</span>
            <span class="batch-fix-desc">{{ getCategoryDesc(cat.key) }}</span>
          </div>
          <el-tag
            size="small"
            effect="dark"
            :type="getCategoryTagType(cat.key, cat.count)"
            >{{ cat.count }} 条
          </el-tag>
        </div>
        <div class="batch-fix-actions" @click.stop>
          <template v-if="cat.key === 'missingCode'">
            <template v-for="assetType in ['fund', 'stock']" :key="assetType">
              <template
                v-if="getMissingRowsByType(cat.rows, assetType).length > 0"
              >
                <template v-if="assetType === 'fund'">
                  <template
                    v-if="getMissingRowsByType(cat.rows, 'fund').length === 1"
                  >
                    <el-input
                      v-model="batchCodeInput"
                      placeholder="输入基金代码"
                      size="small"
                      class="batch-fix-input"
                    />
                    <el-button
                      type="primary"
                      size="small"
                      class="batch-fix-btn batch-fix-btn--primary"
                      @click="
                        batchFillCode(
                          getMissingRowsByType(cat.rows, 'fund'),
                          batchCodeInput
                        )
                      "
                    >
                      应用到当前 1 条
                    </el-button>
                  </template>
                  <template v-else>
                    <el-button
                      type="primary"
                      size="small"
                      @click="showMatchDrawer = true"
                    >
                      匹配基金代码（{{
                        getMissingRowsByType(cat.rows, "fund").length
                      }}只）
                    </el-button>
                  </template>
                </template>

                <template v-if="assetType === 'stock'">
                  <el-input
                    v-model="batchCodeInput"
                    placeholder="输入股票代码"
                    size="small"
                    class="batch-fix-input"
                  />
                  <el-button
                    type="primary"
                    size="small"
                    class="batch-fix-btn batch-fix-btn--primary"
                    @click="
                      batchFillCode(
                        getMissingRowsByType(cat.rows, 'stock'),
                        batchCodeInput
                      )
                    "
                  >
                    应用到当前
                    {{ getMissingRowsByType(cat.rows, "stock").length }}
                    条
                  </el-button>
                </template>
              </template>
            </template>
          </template>
          <template v-if="cat.key === 'mismatch'">
            <el-tooltip content="以数量×价格为准修正金额" placement="top">
              <el-button
                type="primary"
                size="small"
                class="batch-fix-btn batch-fix-btn--primary"
                @click="batchFixAmount(cat.rows)"
                >修正金额
              </el-button>
            </el-tooltip>
          </template>
          <template v-if="cat.key === 'missingQtyPrice'">
            <el-button
              type="primary"
              size="small"
              class="batch-fix-btn batch-fix-btn--primary"
              @click="
                showFullTable = true;
                showProblemOnly = true;
              "
              >展开查看并手动编辑
            </el-button>
          </template>
          <el-button
            size="small"
            class="batch-fix-btn batch-fix-btn--secondary"
            @click="skipCategory(cat.rows)"
            >跳过当前
          </el-button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.batch-fix-bar {
  display: flex;
  gap: 8px;
  align-items: center;
  flex-wrap: wrap;
  margin-bottom: 12px;
}

.batch-fix-hint {
  font-size: 12px;
  color: var(--color-warning);
}

.batch-fix-panel {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.batch-fix-group {
  border: 1px solid var(--border-default);
  border-radius: 8px;
  transition: all 0.2s;
}

.batch-fix-group:hover {
  border-color: var(--color-primary);
}

.batch-fix-card {
  padding: 12px;
}

.batch-fix-card-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 8px;
}

.batch-fix-info {
  display: flex;
  flex-direction: column;
}

.batch-fix-label {
  font-size: 13px;
  font-weight: 500;
  color: var(--text-primary);
}

.batch-fix-desc {
  font-size: 11px;
  color: var(--text-tertiary);
}

.batch-fix-actions {
  display: flex;
  gap: 6px;
  align-items: center;
  flex-wrap: wrap;
  margin-top: 10px;
}

.batch-fix-input {
  width: 120px;
}

.batch-fix-input :deep(.el-input__inner) {
  padding-left: 8px;
}

.batch-fix-input :deep(.el-input__wrapper) {
  padding-left: 4px;
}

.batch-fix-btn {
  margin: 0;
}

.batch-fix-btn--primary {
  background-color: var(--color-primary);
  border-color: var(--color-primary);
  color: var(--bg-card);
}

.batch-fix-btn--secondary {
  margin-left: auto;
}
</style>
