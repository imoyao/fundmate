<!--
  CrowdingMetricCell · 拥挤度类指标的单元格（数值 + 进度条）
  从 CrowdingTable 抽出（#980 批 B5）：拥挤度 / 成交额占比 / 换手率三列除字段名外
  完全同构，原先在同一个模板里各写一遍（每份 38 行），改一处必须记得改另外两处。

  ⚠️ 缺数据必须显示「--」且进度条为 0 宽，**不能画成 0%**：
  这三个指标都是「历史分位」，0 分位是一个真实的极冷读数，与「没取到数」完全不同。
-->
<template>
  <div class="crowding-cell">
    <span class="crowding-value" :class="crowdingColorClass(value)">
      {{ value != null ? value.toFixed(1) + "%" : "--" }}
    </span>
    <div class="crowding-cell-bar">
      <div class="crowding-cell-track">
        <div
          class="crowding-cell-fill"
          :class="crowdingColorClass(value)"
          :style="crowdingBarStyle(value)"
        />
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import {
  crowdingBarStyle,
  crowdingColorClass
} from "@/utils/temperatureFormat";

defineOptions({ name: "CrowdingMetricCell" });

defineProps<{
  /** 历史分位（0–100）；null / undefined = 缺数据，显示「--」且条宽为 0 */
  value: number | null | undefined;
}>();
</script>

<style lang="scss" scoped>
/* ===== 拥挤度单元格（数值 + 进度条） ===== */
.crowding-cell {
  display: flex;
  gap: 10px;
  align-items: center;
  justify-content: flex-end;
}

.crowding-value {
  min-width: 52px;
  font-weight: 600;
  font-variant-numeric: tabular-nums;
  text-align: right;
}

.crowding-cell-bar {
  flex: 1;
  max-width: 96px;
}

.crowding-cell-track {
  position: relative;
  height: 8px;
  overflow: hidden;
  background: var(--border-default);
  border-radius: 4px;
}

.crowding-cell-fill {
  position: absolute;
  top: 0;
  left: 0;
  height: 100%;
  border-radius: 4px;
  transition: width 0.4s ease;
}

.crowding-cell-fill.val-low {
  background: var(--temp-low);
}

.crowding-cell-fill.val-mid {
  background: var(--temp-mid);
}

.crowding-cell-fill.val-high {
  background: var(--temp-high);
}
</style>
