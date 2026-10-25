<script setup lang="ts">
/**
 * 模块二：操作类型切换（#980 拆分）。
 *
 * 语义 = 表单取值（`role="radiogroup"`），按 design.md 归「D13 果冻胶囊」：
 * 每项一颗独立胶囊（透明底 + 1px 描边），选中态 brand-100 底 / brand-400 描边 /
 * brand-700 字 + 弹性回弹。**不是** iOS 那种「软底轨道 + 白色滑块」的分段控制器——
 * 那套语言归 SegmentedControl（Tab 语义，切换的是「看什么」），两者不可互替。
 *
 * 基金组有 6 项，故用 wrap 平铺而不是等分 flex-1：等分到 6 列时
 * 「红利再投 / 送股拆分」会被压成两行字。
 *
 * 两个 v-model 走 `defineModel` 而不是「收值 + emit」：父页那一侧是**带 setter 的
 * computed**（切换前要先问一次「放弃已填内容吗」，见 #1891），defineModel 的
 * 赋值会原样落到 setter 上；若改成 emit + 父页手写监听，就得把这段守卫复制一遍。
 */
import { isFundLike } from "./manualEntryModel";
import type { FundOpType, StockOpType } from "./manualEntryModel";

defineProps<{
  /** 账户 ledger_type，决定渲染证券组还是基金组；null 时整块不渲染 */
  ledgerType: string | null;
}>();

const stockOpType = defineModel<StockOpType>("stockOpType", { required: true });
const fundOpType = defineModel<FundOpType>("fundOpType", { required: true });
</script>

<template>
  <!-- 外层 div 的存在条件由父页决定（选了账户才渲染）；ledgerType 为空时
       两个 radio-group 都不命中，留一个空 div——与原结构逐字一致。 -->
  <div>
    <el-radio-group
      v-if="ledgerType === 'stock'"
      v-model="stockOpType"
      class="op-switch"
      aria-label="操作类型"
    >
      <el-radio-button label="buy">买入</el-radio-button>
      <el-radio-button label="sell">卖出</el-radio-button>
      <el-radio-button label="dividend">现金分红</el-radio-button>
      <el-radio-button label="split">送股/拆分</el-radio-button>
    </el-radio-group>
    <el-radio-group
      v-else-if="isFundLike(ledgerType)"
      v-model="fundOpType"
      class="op-switch"
      aria-label="操作类型"
    >
      <el-radio-button label="subscribe">申购</el-radio-button>
      <el-radio-button label="redeem">赎回</el-radio-button>
      <el-radio-button label="dividend_reinvest">红利再投</el-radio-button>
      <el-radio-button label="split">送股/拆分</el-radio-button>
      <el-radio-button label="convert">转换</el-radio-button>
      <el-radio-button label="drip">定投</el-radio-button>
    </el-radio-group>
  </div>
</template>

<style scoped>
/* 🔥 果冻回弹关键帧 */
@keyframes button-pop {
  0% {
    transform: scale(1);
  }

  30% {
    transform: scale(0.9);
  }

  60% {
    transform: scale(1.06);
  }

  80% {
    transform: scale(0.96);
  }

  100% {
    transform: scale(1);
  }
}

/* ── 操作类型：D13 果冻胶囊（每项一颗独立胶囊，可换行；不做等分轨道） ── */
.op-switch {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
}

.op-switch :deep(.el-radio-button) {
  flex: 0 0 auto;
}

.op-switch :deep(.el-radio-button__inner) {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 74px;
  height: 34px;
  padding: 0 16px;
  font-size: var(--text-label);
  font-weight: 500;
  line-height: 1;
  color: var(--text-secondary);
  background: transparent !important;

  /* 描边比 --border-default 再压深一档（#2348）：D13 是「透明底 + 1px 描边」，
     底色已让位给选中态，未选中项的全部可见性都压在这条线上；
     原色 #e5ddd4 落在 #fbfaf6 卡片上几乎不可见，六颗胶囊看上去是「散落的文字」。
     用 color-mix 派生而不是新写一个 hex：暗色下两个端点都会自动跟随。 */
  border: 1px solid
    color-mix(in srgb, var(--border-default) 68%, var(--text-secondary)) !important;
  border-radius: var(--radius-pill) !important;
  box-shadow: none !important;

  /* 果冻回弹：只在 transform 上弹，颜色过渡用线性缓动 */
  transform: translateZ(0);
  transform-origin: center;
  transition:
    transform 0.15s cubic-bezier(0.34, 1.56, 0.64, 1),
    background-color 0.18s ease,
    border-color 0.18s ease,
    color 0.18s ease;
  will-change: transform;
}

/* Hover：描边提到品牌色，文字提到主色 */
.op-switch :deep(.el-radio-button__inner:hover) {
  color: var(--text-primary);
  border-color: var(--brand-400) !important;
}

/* 按下时的收缩反馈 */
.op-switch :deep(.el-radio-button__inner:active) {
  transform: scale(0.92) !important;
}

/* 选中：软按钮（brand-100 底 + brand-400 描边 + brand-700 字）+ 果冻回弹 */
.op-switch :deep(.el-radio-button.is-active .el-radio-button__inner) {
  color: var(--brand-700) !important;
  background: var(--brand-100) !important;
  border-color: var(--brand-400) !important;
  box-shadow: none !important;
  animation: button-pop 0.35s cubic-bezier(0.34, 1.56, 0.64, 1);
}

.op-switch :deep(.el-radio-button.is-active .el-radio-button__inner:hover) {
  color: var(--brand-700) !important;
  background: var(--brand-200) !important;
}

/* 键盘可达性：EP 把原生 radio 藏在视觉层下，焦点环要补到可视元素上 */
.op-switch
  :deep(
    .el-radio-button__original-radio:focus-visible + .el-radio-button__inner
  ) {
  outline: none;
  box-shadow: var(--focus-ring) !important;
}
</style>
