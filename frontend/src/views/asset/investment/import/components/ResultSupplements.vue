<script setup lang="ts">
import ImportErrorSummary from "./ImportErrorSummary.vue";

/**
 * 导入结果页的「补充信息卡片」区块（#980 批 B3 拆分自 ResultStep.vue，
 * 零视觉/行为变更）：银证转账同步 / 疑似重复按勾选保留（#1882）/ 孤儿交易 /
 * 导入错误汇总 / 持仓市价自动更新。
 *
 * 为什么单独成组件：这四张卡是**同构模板**（图标槽 + 标题 + 描述），此前与
 * 主结果区（英雄区 + 指标 + 操作按钮）挤在同一个 template 里，改一张卡的
 * 间距要跨越一百多行去比对另外三张。
 *
 * 显隐仍由父级 `hasSupplements` 总控（父级要按同一组计数决定副文案，见
 * importResultModel.ts）——本组件**不自己判空**，避免出现「父级判了有内容、
 * 子组件却渲染出一个只有上边框的空块」这种两层判据打架。
 */
defineProps<{
  /** 银证转账在现金侧生成的反向记录数（#1010） */
  cashTransfersCreated: number;
  /** 勾选保留后真的入库的疑似重复笔数（#1882） */
  keptCount: number;
  /** 勾选保留但被去重规则拦截的笔数（#1882） */
  keptBlockedCount: number;
  /** 孤儿交易（缺对应持仓）笔数 */
  orphanCount: number;
  /** 是否展示「持仓市价已自动更新」提示 */
  showPriceUpdateTip: boolean;
  /** 是否存在导入错误明细（ImportErrorSummary 自带 v-if，此处仍显式判一次） */
  hasImportErrors: boolean;
}>();
</script>

<template>
  <!-- 补充信息卡片（仅在有内容时渲染；外层 v-if 在父级） -->
  <div class="result-supplements">
    <!-- 现金转账同步 -->
    <div v-if="cashTransfersCreated > 0" class="supplement-card success">
      <div class="supplement-icon success-icon">
        <svg viewBox="0 0 20 20" fill="none">
          <path
            d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 10.586l7.293-7.293a1 1 0 011.414 0z"
            fill="currentColor"
          />
        </svg>
      </div>
      <div class="supplement-body">
        <p class="supplement-title">银证转账已同步</p>
        <p class="supplement-desc">
          已为
          {{ cashTransfersCreated }}
          笔转账生成现金侧记录，可在交易流水中查看资金流向。
        </p>
      </div>
    </div>

    <!-- 疑似重复·勾选保留（#1882） -->
    <div
      v-if="keptCount > 0 || keptBlockedCount > 0"
      class="supplement-card success"
    >
      <div class="supplement-icon success-icon">
        <svg viewBox="0 0 20 20" fill="none">
          <path
            d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 10.586l7.293-7.293a1 1 0 011.414 0z"
            fill="currentColor"
          />
        </svg>
      </div>
      <div class="supplement-body">
        <p class="supplement-title">重复行已按勾选保留</p>
        <p class="supplement-desc">
          <template v-if="keptCount > 0">
            {{ keptCount }} 笔疑似重复交易已按你的勾选保留入库
          </template>
          <template v-if="keptCount > 0 && keptBlockedCount > 0"> ； </template>
          <template v-if="keptBlockedCount > 0">
            {{ keptBlockedCount }} 笔此前已保留过，自动跳过避免重复叠加
          </template>
          。
        </p>
      </div>
    </div>

    <!-- 孤儿交易提示 -->
    <div v-if="orphanCount > 0" class="supplement-card warning">
      <div class="supplement-icon warning-icon">
        <svg viewBox="0 0 20 20" fill="none">
          <path
            fill-rule="evenodd"
            d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z"
            clip-rule="evenodd"
            fill="currentColor"
          />
        </svg>
      </div>
      <div class="supplement-body">
        <p class="supplement-title">部分交易数据不完整</p>
        <p class="supplement-desc">
          {{ orphanCount }}
          笔交易因缺少对应持仓记录，已作为待处理数据保存。这些交易不会影响当前资产计算。
        </p>
      </div>
    </div>

    <!-- 导入错误汇总 -->
    <ImportErrorSummary
      v-if="hasImportErrors"
      title="导入过程中部分记录因以下原因被跳过"
    />

    <!-- 持仓价格更新提示 -->
    <div v-if="showPriceUpdateTip" class="supplement-card info">
      <div class="supplement-icon info-icon">
        <svg viewBox="0 0 20 20" fill="none">
          <path
            fill-rule="evenodd"
            d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7-4a1 1 0 11-2 0 1 1 0 012 0zM9 9a1 1 0 000 2v3a1 1 0 001 1h1a1 1 0 100-2v-3a1 1 0 00-1-1H9z"
            clip-rule="evenodd"
            fill="currentColor"
          />
        </svg>
      </div>
      <div class="supplement-body">
        <p class="supplement-title">持仓市价已自动更新</p>
        <p class="supplement-desc">
          你刚导入了交易记录，持仓数据已更新，市价也已自动刷新（场外按最近确认净值）。
          若个别标的价格仍显示为上一确认日——场外净值当天未公布、或场内收盘价待当日盘后
          补齐——可
          <router-link :to="{ name: 'AssetStocks' }" class="link-primary"
            >前往持仓页查看</router-link
          >。
        </p>
      </div>
    </div>
  </div>
</template>

<style scoped>
/* 列表容器与 ResultStep 共用一份源 */
@use "./result-supplements";

.supplement-card {
  display: flex;
  gap: var(--space-compact);
  padding: var(--space-standard);
  background: var(--bg-card);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-lg);
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

.success-icon {
  color: var(--color-success-ink);
}

.warning-icon {
  color: var(--color-warning-ink);
}

.info-icon {
  color: var(--color-info-ink);
}

/* 文字区 */
.supplement-body {
  min-width: 0;
}

.supplement-title {
  margin: 0 0 4px;
  font-size: var(--text-body);
  font-weight: 600;
  color: var(--text-primary);
}

.supplement-desc {
  margin: 0;
  font-size: var(--text-small);
  line-height: 1.6;
  color: var(--text-secondary);
}

.link-primary {
  font-weight: 500;
  color: var(--brand-700);
  text-decoration: none;
}

.link-primary:hover {
  text-decoration: underline;
}
</style>
