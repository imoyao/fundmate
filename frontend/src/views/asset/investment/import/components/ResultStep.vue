<script setup lang="ts">
import { computed } from "vue";
import ImportErrorSummary from "./ImportErrorSummary.vue";
import ResultSupplements from "./ResultSupplements.vue";
import { useImportWizardContext } from "../composables/useImportWizardContext";
import {
  hasAnomalies as calcHasAnomalies,
  hasSupplements as calcHasSupplements,
  type ImportResultState
} from "../importResultModel";

const ctx = useImportWizardContext();

// 解构出的均为 composable 返回的 ref。Vue 运行时经 proxyRefs 自动解包，
// 但 vue-tsc 对「从函数返回值解构的 ref」无法静态识别为 setup-ref，
// 不会在模板类型层解包，导致 Ref 与 number 比较报错（dev 基线预存 CI 红）。
// 故在此用 computed 包一层，使模板绑定被识别为 setup-ref 而正确解包。
const nothingImported = computed(() => ctx.nothingImported.value);
const importedCount = computed(() => ctx.importedCount.value);
const skippedCount = computed(() => ctx.skippedCount.value);
// #1882：勾选保留的疑似重复行——入库 / 拦截计数
const keptCount = computed(() => ctx.keptCount.value);
const keptBlockedCount = computed(() => ctx.keptBlockedCount.value);
const duplicateCount = computed(() => ctx.duplicateCount.value);
const errorCount = computed(() => ctx.errorCount.value);
const orphanCount = computed(() => ctx.orphanCount.value);
const cashTransfersCreated = computed(() => ctx.cashTransfersCreated.value);
const importErrors = computed(() => ctx.importErrors.value);
const showPriceUpdateTip = computed(() => ctx.showPriceUpdateTip.value);

const goToTransactions = ctx.goToTransactions;
const continueImport = ctx.continueImport;
const reimport = ctx.reimport;
const goToImportGuide = ctx.goToImportGuide;

/**
 * 结果页全部计数收成一个对象喂给纯函数（#980 批 B3）：
 * 两条显隐规则（副文案走干净分支 / 补充信息区块是否出现）已搬到
 * ../importResultModel.ts 并由单测钉住边界，这里只负责取值。
 */
const resultState = computed<ImportResultState>(() => ({
  skipped: skippedCount.value,
  duplicate: duplicateCount.value,
  error: errorCount.value,
  orphan: orphanCount.value,
  kept: keptCount.value,
  keptBlocked: keptBlockedCount.value,
  cashTransfers: cashTransfersCreated.value,
  hasImportErrors: importErrors.value.length > 0,
  showPriceUpdateTip: showPriceUpdateTip.value
}));

/** 是否有跳过/异常记录（用于决定是否展示统计明细行） */
const hasAnomalies = computed(() => calcHasAnomalies(resultState.value));

/** 是否有补充信息区块（转账 / 保留 / 孤儿 / 错误 / 价格提示任一存在） */
const hasSupplements = computed(() => calcHasSupplements(resultState.value));
</script>

<template>
  <div class="import-result">
    <!-- ═════════════════ 有数据导入成功 ═════════════════ -->
    <template v-if="!nothingImported">
      <!-- 主结果区：居中、克制、有呼吸感 -->
      <div class="result-hero">
        <!-- 成功图标：品牌超椭圆容器 + SVG 勾选 -->
        <div class="result-icon">
          <svg
            viewBox="0 0 48 48"
            fill="none"
            xmlns="http://www.w3.org/2000/svg"
          >
            <circle
              cx="24"
              cy="24"
              r="23"
              stroke="currentColor"
              stroke-width="2"
            />
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

      <!-- 补充信息卡片（拆分见 ResultSupplements；是否有内容由本级的
           hasSupplements 总控，避免子组件再判一次空、渲染出只有上边框的空块） -->
      <ResultSupplements
        v-if="hasSupplements"
        :cash-transfers-created="cashTransfersCreated"
        :kept-count="keptCount"
        :kept-blocked-count="keptBlockedCount"
        :orphan-count="orphanCount"
        :show-price-update-tip="showPriceUpdateTip"
        :has-import-errors="importErrors.length > 0"
      />

      <!-- 操作按钮 -->
      <div class="result-actions">
        <el-button
          v-if="
            importedCount > 0 || orphanCount > 0 || cashTransfersCreated > 0
          "
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
          <svg
            viewBox="0 0 48 48"
            fill="none"
            xmlns="http://www.w3.org/2000/svg"
          >
            <circle
              cx="24"
              cy="24"
              r="23"
              stroke="currentColor"
              stroke-width="2"
            />
            <path
              d="M24 16v12m0 6v.01"
              stroke="currentColor"
              stroke-width="2.5"
              stroke-linecap="round"
            />
          </svg>
        </div>
        <h2 class="result-title">处理完成</h2>
        <p class="result-caption">
          本次无新增交易，共跳过 {{ skippedCount }} 条记录
        </p>
        <p v-if="keptBlockedCount > 0" class="result-caption">
          勾选保留的 {{ keptBlockedCount }} 条此前已入库，本次未重复叠加
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
/* 补充信息卡片列表容器与 ResultSupplements 共用一份源 */
@use "./result-supplements";

/* ── 容器 ── */
.import-result {
  max-width: 520px;
  padding: var(--space-loose) var(--space-standard) var(--space-loose);
  margin: 0 auto;
}

/* ── 主结果区（居中英雄区）── */
.result-hero {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding-bottom: var(--space-loose);
  text-align: center;
}

/* 成功图标：品牌色圆环 + 勾选 */
.result-icon {
  width: 56px;
  height: 56px;
  margin-bottom: var(--space-compact);
  color: var(--color-success-ink);
}

.result-icon svg {
  width: 100%;
  height: 100%;
}

/* 信息态图标（无新增数据时） */
.result-icon.info-tone {
  color: var(--color-info-ink);
}

/* 标题 */
.result-title {
  margin: 0 0 var(--space-compact);
  font-size: var(--text-title);
  font-weight: 600;
  color: var(--text-primary);
  letter-spacing: -0.01em;
}

/* 核心指标：数字 + 单位 */
.result-metric {
  display: inline-flex;
  gap: 6px;
  align-items: baseline;
  margin-bottom: var(--space-compact);
}

.metric-value {
  font-size: var(--text-display-lg);
  font-weight: 700;
  font-variant-numeric: tabular-nums;
  line-height: 1;
  color: var(--color-success-ink);
  letter-spacing: -0.02em;
}

.metric-unit {
  font-size: var(--text-body);
  font-weight: 500;
  color: var(--text-secondary);
}

/* 副文案 */
.result-caption {
  max-width: 380px;
  margin: 0;
  font-size: var(--text-small);
  line-height: 1.6;
  color: var(--text-tertiary-ink);
}

/* 全部通过时的「干净」状态：稍亮一点表示正向反馈 */
.result-caption.clean {
  color: var(--color-success-ink);
  opacity: 0.85;
}

/* ── 操作按钮 ── */
.result-actions {
  display: flex;
  gap: var(--space-compact);
  justify-content: center;
  padding-top: var(--space-loose);
  margin-top: var(--space-loose);
  border-top: 1px solid var(--border-light);
}
</style>
