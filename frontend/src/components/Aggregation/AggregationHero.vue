<script setup lang="ts">
import { computed } from "vue";
import CardBlock from "@/components/CardBlock/index.vue";
import MoneyDisplay from "@/components/MoneyDisplay/index.vue";
import { IconifyIconOffline } from "@/components/ReIcon";

/**
 * 聚合视图顶部汇总区（#1101 场外基金 / #1132 场内证券 共用）。
 *
 * 「数据日期」取持仓快照日（导入对账日期 / Excel「份额日期」）中**最早**的一笔，
 * 代表数据最滞后的部分——这是对用户最诚实的表达。
 * 各账户导入时间不一致时通过 `hasSnapshotGap` 温和提示，**不强制**用户做任何操作（#1133）。
 */
defineOptions({ name: "AggregationHero" });

const props = withDefaults(
  defineProps<{
    /** 汇总市值（元） */
    totalYuan: number;
    /** 数据日期 YYYY-MM-DD；全部持仓均无快照记录时为 null */
    snapshotDate?: string | null;
    /** 最近快照日；与 snapshotDate 不等表示各账户数据存在时间差 */
    snapshotDateLatest?: string | null;
    hasSnapshotGap?: boolean;
    /** 主指标名，默认「总市值」 */
    label?: string;
    /** 持仓项数（分页前的全量条数）；null 表示不展示 */
    count?: number | null;
  }>(),
  {
    snapshotDate: null,
    snapshotDateLatest: null,
    hasSnapshotGap: false,
    label: "总市值",
    count: null
  }
);

/** 数据日期释义：专业、克制，避免冷冰冰的「数据异常」式措辞 */
const tooltipText = computed(() => {
  const base = "数据日期取自账户导入时的份额日期，代表该持仓记录的时间点。";
  if (props.hasSnapshotGap && props.snapshotDateLatest) {
    return `${base}各账户导入时间不同，此处展示最早的一笔（${props.snapshotDate}），最近的一笔为 ${props.snapshotDateLatest}。`;
  }
  return base;
});
</script>

<template>
  <CardBlock class="aggregation-hero">
    <div class="hero-row">
      <div class="hero-figure">
        <p class="hero-label">{{ label }}</p>
        <MoneyDisplay
          :value="totalYuan"
          size="xl"
          :show-sign="false"
          :auto-color="false"
        />
      </div>

      <div class="hero-meta">
        <el-tooltip
          v-if="snapshotDate"
          placement="bottom-end"
          :content="tooltipText"
        >
          <span class="snapshot-pill">
            <IconifyIconOffline icon="ep:calendar" class="pill-icon" />
            数据日期 {{ snapshotDate }}
          </span>
        </el-tooltip>
        <p v-if="count != null" class="hero-count">共 {{ count }} 项</p>
      </div>
    </div>
  </CardBlock>
</template>

<style scoped>
@media (width <= 640px) {
  .hero-row {
    align-items: flex-start;
  }

  .hero-meta {
    align-items: flex-start;
  }
}

.aggregation-hero {
  /* 数字等宽对齐：消除金额宽度抖动 */
  font-variant-numeric: tabular-nums;
}

.hero-row {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-4, 16px);
  align-items: flex-end;
  justify-content: space-between;
}

.hero-label {
  margin-bottom: 4px;
  font-size: 13px;
  font-weight: 500;
  color: var(--text-secondary);
}

.hero-meta {
  display: flex;
  flex-direction: column;
  gap: 8px;
  align-items: flex-end;
}

/* 数据日期胶囊：与 PageHeaderBar 更新时间胶囊同款视觉语言 */
.snapshot-pill {
  display: inline-flex;
  gap: 6px;
  align-items: center;
  padding: 4px 10px;
  font-size: 12px;
  color: var(--text-tertiary);
  cursor: default;
  background: var(--bg-soft);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-pill);
}

.pill-icon {
  font-size: 12px;
}

.hero-count {
  font-size: 12px;
  color: var(--text-tertiary);
}
</style>
