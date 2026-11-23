<script setup lang="ts">
import type { OverviewGroupLike } from "./ledgerTypes";
import { computed } from "vue";
import { IconifyIconOffline } from "@/components/ReIcon";
import CardBlock from "@/components/CardBlock/index.vue";
import AssetAllocationDonut from "@/components/Charts/AssetAllocationDonut.vue";
import { shareOfTotal } from "./overviewShare";

/**
 * 资产配置环形图卡（#984 ledgers/index.vue 拆分）。
 * 数据源 overview.groups（过滤已删除账户）。
 *
 * #2164：图表部分原先是本文件手写的一整套 pie option（约 65 行：tooltip / legend /
 * series / 主题重算 / 减动效）。现已收编到统一组件 `AssetAllocationDonut`——
 * `components.md` §「AssetAllocationDonut · 资产配置环形图（强制复用）」明文要求如此，
 * 且有 `scripts/guard_no_duplicate_pie.py` 在 CI 拦新增。
 *
 * 保留在本文件的是**卡片壳**能力（donut 不提供、也不该提供）：
 * 圆心的覆盖层（最大的那一类占多少）与整卡空态（图标 + 文案）。
 *
 * 圆心从「总资产金额」改成「最大分类 + 占比」：总资产在净资产卡的指标行里已经
 * 说过一次（design.md：一个值只说一次），而「我大部分钱押在哪」才是环形图本身
 * 该回答的问题。覆盖层只作图形注解，`aria-hidden` —— 同一信息在底部图例里已完整可读。
 */
const props = defineProps<{
  /** overview.groups 原始分组 */
  groups: OverviewGroupLike[];
}>();

// 环形图数据源：overview groups（过滤已删除账户），value 用 group.total（元）。
// 按 ledger_type 聚合，集合固定（bank/stock/fund/e_account/property）→ ≤5 类，
// 命中 components.md 的「≤6 类用环形」判据。
const allocationGroups = computed(() =>
  (props.groups ?? []).filter(g => g.type !== "deleted" && (g.total || 0) > 0)
);

// 空态判定：无分组或全部 total=0 时不渲染图表
const hasAllocationData = computed(() => allocationGroups.value.length > 0);

const allocationTotal = computed(() =>
  allocationGroups.value.reduce((sum, g) => sum + (g.total || 0), 0)
);

// 圆心注解：占比最大的一类。占比不可算时整个覆盖层不渲染（不写「0.0%」）。
const topGroup = computed(() => {
  const groups = allocationGroups.value;
  if (!groups.length) return null;

  const top = groups.reduce((best, g) =>
    (g.total || 0) > (best.total || 0) ? g : best
  );
  const share = shareOfTotal(top.total, allocationTotal.value);
  if (!share) return null;

  return { label: top.label ?? "", share };
});

// 喂给统一组件的数据：name/value 与 donut 的 DonutDatum 同构，零转换。
// 颜色不传 colorMap —— 原实现就是 --chart-01~08 循环，与 donut 缺失时的回退一致。
const donutData = computed(() =>
  allocationGroups.value.map(g => ({
    name: g.label ?? "",
    value: g.total || 0
  }))
);
</script>

<template>
  <CardBlock class="allocation-card" data-region="allocation">
    <p class="overview-label">资产配置</p>
    <div v-if="hasAllocationData" class="allocation-chart-wrap">
      <!-- 圆心注解：顶部坐标必须与 series.center 的 45% 一致——此前写 42%，
           覆盖层整整高出圆心中线 3%（≈7px），大金额时会压到扇区上。 -->
      <div v-if="topGroup" class="allocation-center" aria-hidden="true">
        <span class="allocation-center__share">{{ topGroup.share }}</span>
        <span class="allocation-center__label">{{ topGroup.label }}</span>
      </div>
      <AssetAllocationDonut
        :data="donutData"
        :show-legend-percent="true"
        :legend-font-size="13"
        empty-text="暂无资产配置数据"
        class="allocation-chart"
      />
    </div>
    <div v-else class="allocation-empty">
      <IconifyIconOffline
        icon="ep:pie-chart"
        class="text-4xl mb-2 opacity-30"
      />
      <p class="allocation-empty__text">暂无资产配置数据</p>
    </div>
  </CardBlock>
</template>

<style lang="scss" scoped>
/* 卡片眉标（同净资产卡）：13px 辅助色，壳由 CardBlock 提供 */
.overview-label {
  margin: 0;
  font-size: var(--text-label);
  line-height: 18px;
  color: var(--text-tertiary-ink);
}

.allocation-card {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}

.allocation-chart-wrap {
  position: relative;
  flex: 1;
  min-height: 200px;
}

/* 图表绝对定位填满容器：避免 echarts 在 flex 高度解析下拿到 0 高度 */
.allocation-chart {
  position: absolute;
  inset: 0;
}

/* 圆心覆盖层：与 donut 的 series center 同坐标（50% / 45%） */
.allocation-center {
  position: absolute;
  top: 45%;
  left: 50%;
  z-index: 1;
  display: flex;
  flex-direction: column;
  gap: 2px;
  align-items: center;
  pointer-events: none;
  transform: translate(-50%, -50%);
}

.allocation-center__share {
  font-family: var(--font-sans);
  font-size: var(--text-title);
  font-weight: 600;
  font-variant-numeric: tabular-nums;
  line-height: 1.1;
  color: var(--text-primary);
}

.allocation-center__label {
  font-size: var(--text-label);
  line-height: 18px;
  color: var(--text-tertiary-ink);
}

.allocation-empty {
  display: flex;
  flex: 1;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  min-height: 200px;
  color: var(--text-tertiary-ink);
}

.allocation-empty__text {
  margin: 0;
  font-size: var(--text-small);
  color: var(--text-tertiary-ink);
}

@media (prefers-reduced-motion: reduce) {
  .allocation-card {
    transition: none;
  }
}
</style>
