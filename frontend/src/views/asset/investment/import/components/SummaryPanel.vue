<script setup lang="ts">
import { ALLOCATION_OPTIONS } from "@/constants";
import { useImportWizardContext } from "../composables/useImportWizardContext";

const {
  showLeftPanel,
  validRowsCount,
  duplicateCount,
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
  skipCategory,
  selectedCount,
  batchSetAllocation,
  currentAllocationGroups,
  applyAllocationGroupSetting,
  showAllocationGroupPanel,
} = useImportWizardContext();
</script>

<template>
  <div class="step3-left" :class="{ collapsed: !showLeftPanel }">
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
        <div
          v-if="duplicateCount > 0"
          class="summary-card summary-card--warning"
        >
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
                      {{
                        getMissingRowsByType(cat.rows, "stock").length
                      }}
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

    <div v-if="showAllocationGroupPanel" class="allocation-group-panel">
      <div class="allocation-group-header">
        <span class="font-weight-500">按产品类型设置配置目标</span>
        <div class="flex items-center gap-3">
          <el-button
            size="small"
            text
            @click="showAllocationGroupPanel = false"
            >取消</el-button
          >
        </div>
      </div>
      <div v-if="selectedCount > 0" class="allocation-group-item">
        <div class="allocation-group-info">
          <span class="allocation-group-label">已选行批量设置</span>
          <el-tag size="small" type="primary">{{ selectedCount }} 条已选</el-tag>
        </div>
        <el-select
          model-value=""
          placeholder="选择配置目标"
          size="small"
          style="width: 140px"
          @change="(val: string) => batchSetAllocation(val)"
        >
          <el-option
            v-for="opt in ALLOCATION_OPTIONS"
            :key="opt.value"
            :label="opt.label"
            :value="opt.value"
          />
        </el-select>
      </div>
      <div class="allocation-group-list">
        <div
          v-for="(group, key) in currentAllocationGroups"
          :key="key"
          class="allocation-group-item"
        >
          <div class="allocation-group-info">
            <span class="allocation-group-label">{{ group.label }}</span>
            <el-tag size="small" type="info">{{ group.count }} 条</el-tag>
          </div>
          <el-select
            :model-value="group.currentAllocation"
            size="small"
            style="width: 140px"
            @change="(val: string) => applyAllocationGroupSetting(group, val)"
          >
            <el-option
              v-for="opt in ALLOCATION_OPTIONS"
              :key="opt.value"
              :label="opt.label"
              :value="opt.value"
            />
          </el-select>
        </div>
        <div
          v-if="Object.keys(currentAllocationGroups).length === 0"
          class="text-center text-gray-400 py-4"
        >
          所有数据已手动设置配置目标，无需分组调整
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.step3-left {
  flex-shrink: 0;
  width: 320px;
  padding: 16px;
  overflow-y: auto;
  background: var(--bg-card);
  border-right: 1px solid var(--border-default);
}

.step3-left.collapsed {
  display: none;
}

.summary-panel {
  margin-bottom: 16px;
}

.summary-cards {
  display: flex;
  flex-direction: column;
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
  color: #fff;
}

.batch-fix-btn--secondary {
  margin-left: auto;
}

.allocation-group-panel {
  padding: 12px;
  margin-top: 12px;
  border: 1px solid var(--border-default);
  border-radius: 8px;
}

.allocation-group-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 10px;
  font-size: 13px;
  color: var(--text-primary);
}

.allocation-group-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.allocation-group-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 8px;
  border: 1px solid var(--border-default);
  border-radius: 6px;
  transition: border-color 0.2s;
}

.allocation-group-item:hover {
  border-color: var(--color-primary);
}

.allocation-group-info {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.allocation-group-label {
  font-size: 12px;
  font-weight: 500;
  color: var(--text-primary);
}
</style>
