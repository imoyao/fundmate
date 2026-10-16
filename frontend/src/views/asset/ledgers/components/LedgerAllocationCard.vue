<script setup lang="ts">
import { computed } from "vue";
import { IconifyIconOffline } from "@/components/ReIcon";
import MoneyDisplay from "@/components/MoneyDisplay/index.vue";
import AssetAllocationDonut from "@/components/Charts/AssetAllocationDonut.vue";

/**
 * 资产配置环形图卡（#984 ledgers/index.vue 拆分）。
 * 从 index.vue 原样迁移：数据源 overview.groups（过滤已删除账户）。
 *
 * #2164：图表部分原先是本文件手写的一整套 pie option（约 65 行：tooltip / legend /
 * series / 主题重算 / 减动效）。现已收编到统一组件 `AssetAllocationDonut`——
 * `components.md` §「AssetAllocationDonut · 资产配置环形图（强制复用）」明文要求如此，
 * 且有 `scripts/guard_no_duplicate_pie.py` 在 CI 拦新增。
 *
 * 保留在本文件的是**卡片壳**能力（donut 不提供、也不该提供）：
 * 圆心的「总资产」金额覆盖层、以及整卡空态（图标 + 文案）。圆心覆盖层继续用
 * HTML 绝对定位叠在 donut 之上——donut 的 center 只用于空态文字，不设 center 插槽。
 */
const props = defineProps<{
  /** overview.groups 原始分组 */
  groups: any[];
  /** 总资产（中心覆盖层展示） */
  totalAssets: number;
}>();

// 环形图数据源：overview groups（过滤已删除账户），value 用 group.total（元）。
// 按 ledger_type 聚合，集合固定（bank/stock/fund/e_account/property）→ ≤5 类，
// 命中 components.md 的「≤6 类用环形」判据。
const allocationGroups = computed(() =>
  (props.groups ?? []).filter(
    (g: any) => g.type !== "deleted" && (g.total || 0) > 0
  )
);

// 空态判定：无分组或全部 total=0 时不渲染图表
const hasAllocationData = computed(() => allocationGroups.value.length > 0);

// 喂给统一组件的数据：name/value 与 donut 的 DonutDatum 同构，零转换。
// 颜色不传 colorMap —— 原实现就是 --chart-01~08 循环，与 donut 缺失时的回退一致。
const donutData = computed(() =>
  allocationGroups.value.map((g: any) => ({
    name: g.label,
    value: g.total
  }))
);
</script>

<template>
  <div class="overview-card allocation-card">
    <p class="text-sm mb-2" :style="{ color: 'var(--text-tertiary-ink)' }">
      资产配置
    </p>
    <div v-if="hasAllocationData" class="allocation-chart-wrap">
      <!-- 中心覆盖层：总资产金额（HTML 层，复用 MoneyDisplay 样式锚点） -->
      <div class="allocation-center">
        <span
          class="allocation-center-label"
          :style="{ color: 'var(--text-tertiary-ink)' }"
          >总资产</span
        >
        <MoneyDisplay
          :value="totalAssets"
          :show-sign="false"
          :auto-color="false"
          size="sm"
        />
      </div>
      <AssetAllocationDonut
        :data="donutData"
        :show-legend-percent="true"
        :legend-font-size="12"
        empty-text="暂无资产配置数据"
        class="allocation-chart"
      />
    </div>
    <div v-else class="allocation-empty">
      <IconifyIconOffline
        icon="ep:pie-chart"
        class="text-4xl mb-2 opacity-30"
      />
      <p class="text-sm" :style="{ color: 'var(--text-tertiary-ink)' }">
        暂无资产配置数据
      </p>
    </div>
  </div>
</template>

<style scoped>
@media (prefers-reduced-motion: reduce) {
  .allocation-card {
    transition: none;
  }
}

.allocation-card {
  display: flex;
  flex-direction: column;
}

.allocation-chart-wrap {
  position: relative;
  flex: 1;
  min-height: 220px;
}

/* 图表绝对定位填满容器：避免 echarts 在 flex 高度解析下拿到 0 高度 */
.allocation-chart {
  position: absolute;
  inset: 0;
}

/* 环形图中心覆盖层：总资产金额（HTML 层，与 series center: 42% 对齐） */
.allocation-center {
  position: absolute;
  top: 42%;
  left: 50%;
  z-index: 1;
  display: flex;
  flex-direction: column;
  gap: 2px;
  align-items: center;
  pointer-events: none;
  transform: translate(-50%, -50%);
}

.allocation-center-label {
  font-size: var(--text-label, 13px);
  line-height: 18px;
}

.allocation-empty {
  display: flex;
  flex: 1;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  min-height: 220px;
  color: var(--text-tertiary-ink);
}
</style>
