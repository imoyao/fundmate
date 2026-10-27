<!--
  PnlAttributionRows · 归因明细列表（#980 从 `index.vue` 抽出，纯搬运）

  一行 = 一个品种（或一个大类）：左侧名称与副标题、中间贡献条、右侧金额与占比。
  贡献条宽度按**当前视图内最大 |pnl|** 归一，纯视觉，不参与任何数值展示——
  所以归一化放在组件内部算（`computeMaxAbs`），父级只给行数据。

  为什么用 `aria-hidden` 的条：这个条是「相对大小」的视觉提示，占比数字就在右边，
  读屏把它读一遍只会变成噪音。
-->
<template>
  <ul class="pnl-attribution__list">
    <li v-for="row in rows" :key="row.key" class="pnl-attribution__row">
      <div class="pnl-attribution__identity">
        <span class="pnl-attribution__name" :title="row.name">{{
          row.name
        }}</span>
        <span class="pnl-attribution__sub">{{ row.sub }}</span>
      </div>
      <div class="pnl-attribution__bar-wrap" aria-hidden="true">
        <span
          class="pnl-attribution__bar"
          :class="row.pnl > 0 ? 'is-rise' : row.pnl < 0 ? 'is-fall' : 'is-zero'"
          :style="{ width: barWidth(row) }"
        />
      </div>
      <div class="pnl-attribution__figures">
        <MoneyDisplay :value="row.pnl" size="sm" />
        <span class="pnl-attribution__pct">
          <template v-if="row.pct !== null"
            >{{ row.pct > 0 ? "+" : "" }}{{ row.pct.toFixed(2) }}%</template
          >
          <template v-else>—</template>
        </span>
      </div>
    </li>
  </ul>
</template>

<script setup lang="ts">
import { computed } from "vue";
import MoneyDisplay from "@/components/MoneyDisplay/index.vue";
import { barWidthFor, computeMaxAbs, type ViewRow } from "./attributionModel";

defineOptions({ name: "PnlAttributionRows" });

const props = defineProps<{
  /** 当前维度的行（品种 / 大类），已按 |pnl| 降序由后端排好 */
  rows: ViewRow[];
}>();

/** 贡献条分母：本视图内最大 |pnl|，随维度切换自动跟着换 */
const maxAbs = computed(() => computeMaxAbs(props.rows));

function barWidth(row: ViewRow): string {
  return barWidthFor(row.pnl, maxAbs.value);
}
</script>

<style lang="scss" scoped>
@use "@/style/breakpoints" as bp;

.pnl-attribution__list {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 0;
  margin: 0;
  list-style: none;
}

.pnl-attribution__row {
  display: grid;
  grid-template-columns: minmax(120px, 2fr) minmax(80px, 3fr) minmax(
      120px,
      1fr
    );
  gap: 12px;
  align-items: center;
}

.pnl-attribution__identity {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}

.pnl-attribution__name {
  overflow: hidden;
  text-overflow: ellipsis;
  font-size: var(--text-label, 13px);
  color: var(--text-primary);
  white-space: nowrap;
}

.pnl-attribution__sub {
  overflow: hidden;
  text-overflow: ellipsis;
  font-size: var(--text-label);
  color: var(--text-tertiary-ink);
  white-space: nowrap;
}

.pnl-attribution__bar-wrap {
  position: relative;
  height: 8px;
  overflow: hidden;
  background: var(--bg-soft);
  border-radius: 4px;
}

.pnl-attribution__bar {
  display: block;
  height: 100%;
  border-radius: 4px;
  transition: width 0.25s ease;
}

.pnl-attribution__bar.is-rise {
  background: var(--color-rise);
}

.pnl-attribution__bar.is-fall {
  background: var(--color-fall);
}

.pnl-attribution__bar.is-zero {
  background: var(--el-border-color);
}

.pnl-attribution__figures {
  display: flex;
  gap: 8px;
  align-items: baseline;
  justify-content: flex-end;
}

.pnl-attribution__pct {
  min-width: 56px;
  font-size: var(--text-label);
  font-variant-numeric: tabular-nums;
  color: var(--text-tertiary-ink);
  text-align: right;
}

@include bp.below("sm") {
  .pnl-attribution__row {
    grid-template-columns: minmax(0, 1fr) minmax(80px, 1.5fr) auto;
  }
}
</style>
