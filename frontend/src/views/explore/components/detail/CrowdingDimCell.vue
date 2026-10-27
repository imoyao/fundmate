<!--
  CrowdingDimCell · 「当期值 + 历史分位」的双数字单元格
  从 CrowdingTable 抽出（#980 批 B5）：60 线上占比 / 新高占比 / 融资买入占比三列同构。

  左侧是当期值（中性色，只有粗细差异），右侧是历史分位（按 val-* 档位上色）。
  这个分工是有意的：**同一列里两个数字，只有一个带情绪**。若两边都染色，
  用户会以为「占比」本身也有高低好坏之分，而「60 日线上占比 40%」是中性的。
-->
<template>
  <div class="dim-cell">
    <span class="dim-value">{{ fmtPct(value) }}</span>
    <span class="dim-rank" :class="crowdingColorClass(rank)">
      {{ fmtPct(rank) }}
    </span>
  </div>
</template>

<script setup lang="ts">
import { crowdingColorClass } from "@/utils/temperatureFormat";
import { fmtPct } from "./crowdingCells";

defineOptions({ name: "CrowdingDimCell" });

defineProps<{
  /** 当期值（百分比数值，如 40 表示 40%）；缺数据显示「--」 */
  value: number | null | undefined;
  /** 该值的历史分位（0–100），决定右侧数字的配色档位 */
  rank: number | null | undefined;
}>();
</script>

<style lang="scss" scoped>
/* ===== 外部源维度单元格（当期值 + 历史分位，分位沿用 val-* 档位配色） ===== */
.dim-cell {
  display: flex;
  gap: 8px;
  align-items: baseline;
  justify-content: flex-end;
}

.dim-value {
  font-weight: 600;
  font-variant-numeric: tabular-nums;
}

.dim-rank {
  min-width: 42px;
  font-size: var(--text-label);
  font-variant-numeric: tabular-nums;
  text-align: right;
}

.dim-rank.val-low {
  color: var(--temp-low-ink);
}

.dim-rank.val-mid {
  color: var(--temp-mid-ink);
}

.dim-rank.val-high {
  color: var(--temp-high-ink);
}
</style>
