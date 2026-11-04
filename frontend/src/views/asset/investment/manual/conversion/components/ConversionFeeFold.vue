<script setup lang="ts">
/**
 * 「费用明细，可修正」折叠区（转换确认页，#980 拆分自 ConversionForm.vue）。
 *
 * 为什么是折叠而不是常驻两个输入框：费率表算出的费用与确认单常差几分钱，
 * 所以要能改，但那是 1% 的场景；常驻会让 99% 的人以为这里必须填东西。
 *
 * 折叠区里的 `.panel-row` 与本组件的键值行是**同一个样式族**
 * （`.fee-fold__body .panel-row` 的后代选择器），所以两者必须待在同一个
 * scoped 组件里——拆开会让后代选择器失效、行距退化成默认值。
 */
import { IconifyIconOffline } from "@/components/ReIcon";
import { formatPrice } from "@/utils/pricePrecision";

defineProps<{
  showDetail: boolean;
  /** 用户是否动过费用（动过则显示「已修正」与还原入口） */
  dirty: boolean;
  redeem: number;
  compensate: number;
  /** 算法估算值（人工修正后用于提示「原估算」） */
  estimatedRedeem: number;
  estimatedCompensate: number;
  /** 份额换算行：转入份额 × 转入净值 = 金额 */
  inQuantity: number;
  inNav: number;
  inAmount: number;
}>();

const emit = defineEmits<{
  (e: "update:showDetail", value: boolean): void;
  (e: "update:redeem", value: number | undefined): void;
  (e: "update:compensate", value: number | undefined): void;
  /** 改过费用：父页标记 dirty 并按新费用重算 */
  (e: "edit"): void;
  /** 还原为算法估算值 */
  (e: "reset"): void;
}>();
</script>

<template>
  <!-- 可折叠的只有「明细与修正」，金额不折：合计已经在上面三个数里 -->
  <div class="fee-fold">
    <button
      type="button"
      class="fee-fold__head"
      :aria-expanded="showDetail"
      aria-controls="conversion-fee-detail"
      @click="emit('update:showDetail', !showDetail)"
    >
      <span>
        费用明细，可修正
        <span v-if="dirty" class="fee-fold__dirty">已修正</span>
      </span>
      <span class="fee-fold__action">
        {{ showDetail ? "收起" : "展开" }}
        <IconifyIconOffline
          :icon="showDetail ? 'ep:arrow-up' : 'ep:arrow-down'"
        />
      </span>
    </button>
    <div v-show="showDetail" id="conversion-fee-detail" class="fee-fold__body">
      <div class="panel-row">
        <span class="panel-label">赎回费</span>
        <div class="fee-cell">
          <span class="fee-sign">−¥</span>
          <el-input-number
            :model-value="redeem"
            class="fee-input"
            aria-label="赎回费（可修正）"
            :controls="false"
            :min="0"
            :step="0.01"
            :precision="2"
            @update:model-value="v => emit('update:redeem', v ?? undefined)"
            @change="emit('edit')"
          />
        </div>
      </div>
      <div class="panel-row">
        <span class="panel-label">补差费</span>
        <div class="fee-cell">
          <span class="fee-sign">−¥</span>
          <el-input-number
            :model-value="compensate"
            class="fee-input"
            aria-label="补差费（可修正）"
            :controls="false"
            :min="0"
            :step="0.01"
            :precision="2"
            @update:model-value="v => emit('update:compensate', v ?? undefined)"
            @change="emit('edit')"
          />
        </div>
      </div>
      <div v-if="dirty" class="panel-row fee-hint-row">
        <span class="fee-hint">
          已手工修正 · 原估算 赎回 {{ estimatedRedeem.toFixed(2) }} / 补差
          {{ estimatedCompensate.toFixed(2) }}
        </span>
        <el-button link type="primary" size="small" @click="emit('reset')">
          还原
        </el-button>
      </div>
      <div class="panel-row">
        <span class="panel-label">份额换算</span>
        <span class="panel-value">
          {{ inQuantity.toFixed(2) }} 份 × 净值
          {{ formatPrice(inNav, "fund") }} = ¥{{ inAmount.toFixed(2) }}
        </span>
      </div>
    </div>
  </div>
</template>

<style scoped>
/* 键值行（费用明细里的可编辑行） */
.panel-row {
  display: flex;
  gap: 16px;
  align-items: center;
  justify-content: space-between;
  font-size: var(--text-small);
}

.panel-label {
  display: inline-flex;
  gap: 6px;
  align-items: center;
  color: var(--text-secondary);
  white-space: nowrap;
}

.panel-value {
  font-variant-numeric: tabular-nums;
  color: var(--text-primary);
  text-align: right;
}

/* ── 费用可编辑（#2348） ──
   输入框贴右、与上面的金额列右对齐；tab 数字等宽避免抖动。 */
.fee-cell {
  display: inline-flex;
  gap: 2px;
  align-items: center;
}

.fee-sign {
  font-size: var(--text-label);
  font-variant-numeric: tabular-nums;
  color: var(--text-secondary);
}

.fee-input {
  width: 96px;
}

.fee-input :deep(.el-input__inner) {
  font-variant-numeric: tabular-nums;
  text-align: right;
}

/* 修正提示行：说明「已改过」并给出原估算值，不抢主信息的层级 */
.fee-hint-row {
  margin-top: -4px;
}

.fee-hint {
  font-size: var(--text-label);
  font-variant-numeric: tabular-nums;
  color: var(--text-tertiary-ink);
}

/* 费用折叠：一行可点开，主体只在展开时出现 */
.fee-fold {
  border-top: 1px solid var(--border-light);
}

.fee-fold__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  width: 100%;
  padding: 12px 2px 4px;
  font-size: var(--text-label);
  color: var(--text-secondary);
  cursor: pointer;
  background: none;
  border: 0;
  border-radius: var(--radius-xs);
}

.fee-fold__head:hover {
  color: var(--brand-ink);
}

/* 焦点环用 inset：外扩的 `--focus-ring` 会被卡片圆角裁掉一圈 */
.fee-fold__head:focus-visible {
  color: var(--brand-800);
  outline: none;
  box-shadow: inset 0 0 0 2px var(--brand-700);
}

.fee-fold__action {
  display: inline-flex;
  gap: 4px;
  align-items: center;
  color: var(--brand-ink);
}

.fee-fold__dirty {
  padding: 0 6px;
  margin-left: 6px;
  font-size: var(--text-label);
  color: var(--color-warning-ink);
  background: var(--bg-soft);
  border-radius: var(--radius-xs);
}

.fee-fold__body {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 10px 0 2px;
}

/* 展开区里的键值行不铺满整卡：958px 的宽度会把「赎回费」和它的输入框
   拉到两端，读起来像两件无关的东西。这里改成左对齐的紧凑行。 */
.fee-fold__body .panel-row {
  gap: 12px;
  justify-content: flex-start;
}

.fee-fold__body .panel-label {
  min-width: 56px;
}
</style>
