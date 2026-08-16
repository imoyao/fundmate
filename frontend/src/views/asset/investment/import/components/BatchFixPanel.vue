<script setup lang="ts">
import { computed } from "vue";
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
  skipCategory,
  autoFix
} = useImportWizardContext();

/** 必须人工补全的条目：代码未匹配 + 数量或价格缺失，这两类程序结构性无法自动修正 */
const manualCount = computed(() => {
  const missingCode = problemCategories.value.find(
    c => c.key === "missingCode"
  );
  const missingQtyPrice = problemCategories.value.find(
    c => c.key === "missingQtyPrice"
  );
  return (missingCode?.count || 0) + (missingQtyPrice?.count || 0);
});

/** 可程序化自动处理的条目：mismatch 金额重算 + 基金净值抓取 + 已推算确认 */
const autoFixableCount = computed(() => {
  const mismatch = problemCategories.value.find(c => c.key === "mismatch");
  return (
    (mismatch?.count || 0) +
    calculatedCount.value +
    (hasFundRecordsForNav.value ? fundRecordsCount.value : 0)
  );
});
</script>

<template>
  <div class="batch-fix-panel">
    <div v-if="blockedCount + errorCount > 0" class="bf-body">
      <div class="bf-actions">
        <el-button
          type="primary"
          size="default"
          :loading="enrichingNav"
          :disabled="autoFixableCount === 0"
          @click="autoFix"
        >
          <IconifyIconOffline icon="ep:magic-stick" class="mr-1" />
          自动修复可处理项
        </el-button>
        <el-button size="default" @click="toggleBatchFix">
          {{ showBatchFix ? "收起手动修正" : "展开手动修正" }}
        </el-button>
      </div>

      <p
        class="bf-hint"
        :class="manualCount > 0 ? 'bf-hint--warn' : 'bf-hint--ok'"
      >
        <template v-if="manualCount > 0">
          还有 {{ manualCount }} 条需手动补全代码或价量，无法自动修正
        </template>
        <template v-else> 无可自动修复项，或剩余均可自动处理 </template>
      </p>

      <div
        v-if="showBatchFix && problemCategories.length > 0"
        class="batch-fix-detail"
      >
        <div
          v-for="cat in problemCategories"
          :key="cat.key"
          class="batch-fix-group"
          :class="{ 'batch-fix-group--active': isCategoryActive(cat.key) }"
          @click="filterByCategory(cat.key)"
        >
          <div class="batch-fix-card-inner">
            <div class="batch-fix-card-header">
              <div class="batch-fix-info">
                <span class="batch-fix-label">{{ cat.label }}</span>
                <span class="batch-fix-desc">{{
                  getCategoryDesc(cat.key)
                }}</span>
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
                <template
                  v-for="assetType in ['fund', 'stock']"
                  :key="assetType"
                >
                  <template
                    v-if="getMissingRowsByType(cat.rows, assetType).length > 0"
                  >
                    <template v-if="assetType === 'fund'">
                      <template
                        v-if="
                          getMissingRowsByType(cat.rows, 'fund').length === 1
                        "
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
    </div>

    <p v-else class="bf-empty">本批数据校验通过，无需修正</p>
  </div>
</template>

<style scoped>
/* 展开区形态：不再是顶部独立卡片，而是筛选栏下方可折叠的浅底面板 */
.batch-fix-panel {
  display: flex;
  flex-direction: column;
  gap: 12px;
  min-width: 0;
  padding: 0;
  margin: 0;
  background: transparent;
  border: none;
}

.bf-body {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.bf-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
}

.bf-hint {
  margin: 0;
  font-size: 12px;
}

.bf-hint--warn {
  color: var(--color-warning);
}

.bf-hint--ok {
  color: var(--text-tertiary);
}

.bf-empty {
  margin: 0;
  font-size: 12px;
  color: var(--text-tertiary);
}

.batch-fix-detail {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding-top: 10px;
  margin-top: 4px;
  border-top: 1px dashed var(--border-default);
}

.batch-fix-group {
  border: 1px solid var(--border-default);
  border-radius: 8px;
  transition: all 0.2s;
}

.batch-fix-group:hover {
  border-color: var(--color-primary);
}

.batch-fix-card-inner {
  padding: 12px;
}

.batch-fix-card-header {
  display: flex;
  gap: 8px;
  align-items: flex-start;
  justify-content: space-between;
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
  flex-wrap: wrap;
  gap: 6px;
  align-items: center;
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
  color: var(--bg-card);
  background-color: var(--color-primary);
  border-color: var(--color-primary);
}

.batch-fix-btn--secondary {
  margin-left: auto;
}
</style>
