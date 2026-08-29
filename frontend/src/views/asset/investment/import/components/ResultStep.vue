<script setup lang="ts">
import { computed } from "vue";
import ImportErrorSummary from "./ImportErrorSummary.vue";
import { useImportWizardContext } from "../composables/useImportWizardContext";

const {
  nothingImported,
  importedCount,
  skippedCount,
  cashTransfersCreated,
  duplicateCount,
  errorCount,
  orphanCount,
  importErrors,
  showPriceUpdateTip,
  goToTransactions,
  continueImport,
  reimport,
  goToImportGuide,
} = useImportWizardContext();

/** 是否有跳过/异常记录（用于决定是否展示统计明细行） */
const hasAnomalies = computed(
  () => skippedCount > 0 || duplicateCount > 0 || errorCount > 0 || orphanCount > 0
);

/** 是否有补充信息区块（转账 / 孤儿 / 错误 / 价格提示任一存在） */
const hasSupplements = computed(
  () =>
    cashTransfersCreated > 0 ||
    orphanCount > 0 ||
    importErrors.length > 0 ||
    showPriceUpdateTip
);
</script>

<template>
  <div class="import-result">
    <!-- ═════════════════ 有数据导入成功 ═════════════════ -->
    <template v-if="!nothingImported">
      <!-- 主结果区：居中、克制、有呼吸感 -->
      <div class="result-hero">
        <!-- 成功图标：品牌超椭圆容器 + SVG 勾选 -->
        <div class="result-icon">
          <svg viewBox="0 0 48 48" fill="none" xmlns="http://www.w3.org/2000/svg">
            <circle cx="24" cy="24" r="23" stroke="currentColor" stroke-width="2" />
            <path
              d="M15 25l7 7 11-13"
              stroke="currentColor"
              stroke-width="2.5"
              stroke-linecap="round"
              stroke-linejoin="round"
            />
          </svg>
        </div>

        <h2 class="result-title">导入完成</h2>

        <!-- 核心指标：大数字 + 单位标签 -->
        <div class="result-metric">
          <span class="metric-value">{{ importedCount }}</span>
          <span class="metric-unit">笔交易已入库</span>
        </div>

        <!-- 副文案：根据数据质量动态切换 -->
        <p v-if="!hasAnomalies" class="result-caption clean">
          全部数据校验通过，无重复或异常记录
        </p>
        <p v-else class="result-caption">
          {{ skippedCount }} 笔跳过
          <template v-if="duplicateCount > 0">
            （重复 {{ duplicateCount }} 条）
          </template>
          <template v-if="errorCount > 0">
            · 异常 {{ errorCount }} 条
          </template>
        </p>
      </div>

      <!-- 补充信息卡片（仅在有内容时渲染） -->
      <div v-if="hasSupplements" class="result-supplements">
        <!-- 现金转账同步 -->
        <div v-if="cashTransfersCreated > 0" class="supplement-card success">
          <div class="supplement-icon success-icon">
            <svg viewBox="0 0 20 20" fill="none"><path d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 10.586l7.293-7.293a1 1 0 011.414 0z" fill="currentColor"/></svg>
          </div>
          <div class="supplement-body">
            <p class="supplement-title">银证转账已同步</p>
            <p class="supplement-desc">
              已为 {{ cashTransfersCreated }} 笔转账生成现金侧记录，可在交易流水中查看资金流向。
            </p>
          </div>
        </div>

        <!-- 孤儿交易提示 -->
        <div v-if="orphanCount > 0" class="supplement-card warning">
          <div class="supplement-icon warning-icon">
            <svg viewBox="0 0 20 20" fill="none"><path fill-rule="evenodd" d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z" clip-rule="evenodd" fill="currentColor"/></svg>
          </div>
          <div class="supplement-body">
            <p class="supplement-title">部分交易数据不完整</p>
            <p class="supplement-desc">
              {{ orphanCount }} 笔交易因缺少对应持仓记录，已作为待处理数据保存。这些交易不会影响当前资产计算。
            </p>
          </div>
        </div>

        <!-- 导入错误汇总 -->
        <ImportErrorSummary
          v-if="importErrors.length > 0"
          title="导入过程中部分记录因以下原因被跳过"
        />

        <!-- 持仓价格更新提示 -->
        <div v-if="showPriceUpdateTip" class="supplement-card info">
          <div class="supplement-icon info-icon">
            <svg viewBox="0 0 20 20" fill="none"><path fill-rule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7-4a1 1 0 11-2 0 1 1 0 012 0zM9 9a1 1 0 000 2v3a1 1 0 001 1h1a1 1 0 100-2v-3a1 1 0 00-1-1H9z" clip-rule="evenodd" fill="currentColor"/></svg>
          </div>
          <div class="supplement-body">
            <p class="supplement-title">建议检查持仓市价</p>
            <p class="supplement-desc">
              你刚导入了交易记录，持仓数据已更新。为确保资产计算准确，
              <router-link :to="{ name: 'AssetStocks' }" class="link-primary">前往检查持仓市价</router-link>。
            </p>
          </div>
        </div>
      </div>

      <!-- 操作按钮 -->
      <div class="result-actions">
        <el-button
          v-if="importedCount > 0 || orphanCount > 0 || cashTransfersCreated > 0"
          type="primary"
          @click="goToTransactions"
        >
          查看交易流水
        </el-button>
        <el-button @click="continueImport">继续导入</el-button>
      </div>
    </template>

    <!-- ═════════════════ 无新增数据 ═════════════════ -->
    <template v-else>
      <div class="result-hero">
        <div class="result-icon info-tone">
          <svg viewBox="0 0 48 48" fill="none" xmlns="http://www.w3.org/2000/svg">
            <circle cx="24" cy="24" r="23" stroke="currentColor" stroke-width="2" />
            <path d="M24 16v12m0 6v.01" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"/>
          </svg>
        </div>
        <h2 class="result-title">处理完成</h2>
        <p class="result-caption">
          本次无新增交易，共跳过 {{ skippedCount }} 条记录
        </p>
      </div>

      <div v-if="importErrors.length > 0" class="result-supplements">
        <ImportErrorSummary title="跳过原因" />
      </div>

      <div class="result-actions">
        <el-button type="primary" @click="reimport">重新导入</el-button>
        <el-button @click="goToImportGuide">查看导入规则</el-button>
      </div>
    </template>
  </div>
</template>

<style scoped>
/* ── 容器 ── */
.import-result {
  max-width: 520px;
  margin: 0 auto;
  padding: var(--space-8) var(--space-standard) var(--space-loose);
}

/* ── 主结果区（居中英雄区）── */
.result-hero {
  display: flex;
  flex-direction: column;
  align-items: center;
  text-align: center;
  padding-bottom: var(--space-loose);
}

/* 成功图标：品牌色圆环 + 勾选 */
.result-icon {
  width: 56px;
  height: 56px;
  color: var(--color-success);
  margin-bottom: var(--space-compact);
}
.result-icon svg {
  width: 100%;
  height: 100%;
}

/* 信息态图标（无新增数据时） */
.result-icon.info-tone {
  color: var(--color-info);
}

/* 标题 */
.result-title {
  font-size: var(--text-title);
  font-weight: 600;
  color: var(--text-primary);
  margin: 0 0 var(--space-compact);
  letter-spacing: -0.01em;
}

/* 核心指标：数字 + 单位 */
.result-metric {
  display: inline-flex;
  align-items: baseline;
  gap: 6px;
  margin-bottom: var(--space-compact);
}

.metric-value {
  font-size: 40px;
  font-weight: 700;
  font-variant-numeric: tabular-nums;
  line-height: 1;
  color: var(--color-success);
  letter-spacing: -0.02em;
}

.metric-unit {
  font-size: var(--text-body);
  color: var(--text-secondary);
  font-weight: 500;
}

/* 副文案 */
.result-caption {
  font-size: var(--text-small);
  color: var(--text-tertiary);
  line-height: 1.6;
  margin: 0;
  max-width: 380px;
}

/* 全部通过时的「干净」状态：稍亮一点表示正向反馈 */
.result-caption.clean {
  color: var(--color-success);
  opacity: 0.85;
}

/* ── 补充信息卡片列表 ── */
.result-supplements {
  display: flex;
  flex-direction: column;
  gap: var(--space-compact);
  width: 100%;
  padding-top: var(--space-loose);
  border-top: 1px solid var(--border-light);
}

.supplement-card {
  display: flex;
  gap: var(--space-compact);
  padding: var(--space-standard);
  background: var(--bg-card);
  border-radius: var(--radius-lg);
  border: 1px solid var(--border-light);
  transition: box-shadow 0.2s ease;
}

.supplement-card:hover {
  box-shadow: var(--shadow-raised);
}

/* 图标槽 */
.supplement-icon {
  flex-shrink: 0;
  width: 20px;
  height: 20px;
  margin-top: 2px;
}
.supplement-icon svg {
  width: 100%;
  height: 100%;
}

.success-icon { color: var(--color-success); }
.warning-icon { color: var(--color-warning); }
.info-icon { color: var(--color-info); }

/* 文字区 */
.supplement-body {
  min-width: 0;
}

.supplement-title {
  font-size: var(--text-body);
  font-weight: 600;
  color: var(--text-primary);
  margin: 0 0 4px;
}

.supplement-desc {
  font-size: var(--text-small);
  color: var(--text-secondary);
  line-height: 1.6;
  margin: 0;
}

.link-primary {
  color: var(--brand-700);
  text-decoration: none;
  font-weight: 500;
}
.link-primary:hover {
  text-decoration: underline;
}

/* ── 操作按钮 ── */
.result-actions {
  display: flex;
  gap: var(--space-compact);
  justify-content: center;
  margin-top: var(--space-loose);
  padding-top: var(--space-loose);
  border-top: 1px solid var(--border-light);
}
</style>
