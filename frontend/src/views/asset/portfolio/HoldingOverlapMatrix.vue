<template>
  <!--
    组合内基金两两重叠矩阵（#2686）。与列表视图的分工：
    列表回答「哪几对重复、值多少钱」，矩阵回答「我这 8 只基金里，到底哪几只像同一只」。

    格子六态见 `holdingOverlapMatrix.ts` 模块头：自比 / 0% / 低 / 中 / 高 / 不可比。
    **不可比绝不能画成 0%**——那是 #2604 明确要挡的错误安心。
  -->
  <div class="overlap-matrix">
    <table class="overlap-matrix__table">
      <caption class="overlap-matrix__caption">
        行与列是同一批基金（按持仓市值降序），格子是该对的重叠加权比例（百分点）。
        对角线是自比；「不可比」= 两只基金的披露口径不同（半年报全量 vs
        季报前十大），混算会低估重叠。
      </caption>
      <thead>
        <tr>
          <th scope="col" class="overlap-matrix__corner">基金</th>
          <th
            v-for="(fund, index) in matrix.funds"
            :key="fund.fund_code"
            scope="col"
            class="overlap-matrix__head"
            :title="`${fund.name}（${fund.fund_code}）`"
          >
            {{ index + 1 }}
          </th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="(row, rowIndex) in matrix.rows" :key="row.fund.fund_code">
          <th
            scope="row"
            class="overlap-matrix__row-head"
            :title="`${row.fund.name}（${row.fund.fund_code}）`"
          >
            <span class="overlap-matrix__index">{{ rowIndex + 1 }}</span>
            <span class="overlap-matrix__name">{{ row.fund.name }}</span>
          </th>
          <td
            v-for="(cell, colIndex) in row.cells"
            :key="colIndex"
            class="overlap-matrix__cell"
            :class="`is-${cell.tone}`"
            :title="cell.title"
          >
            {{ cell.text }}
          </td>
        </tr>
      </tbody>
    </table>

    <ul class="overlap-matrix__legend">
      <li class="overlap-matrix__legend-item is-none">0%（确实不重叠）</li>
      <li class="overlap-matrix__legend-item is-low">低（弱提醒档）</li>
      <li class="overlap-matrix__legend-item is-mid">中（需留意）</li>
      <li class="overlap-matrix__legend-item is-high">高（配置重复）</li>
      <li class="overlap-matrix__legend-item is-incomparable">
        不可比（口径不同）
      </li>
    </ul>

    <p v-if="matrix.truncated > 0" class="overlap-matrix__hint">
      仅显示持仓市值前 {{ matrix.funds.length }} 只，另有
      {{ matrix.truncated }} 只未展开（列表视图可看全量）。
    </p>
  </div>
</template>

<script setup lang="ts">
import type { OverlapMatrix } from "./holdingOverlapMatrix";

defineOptions({ name: "HoldingOverlapMatrix" });

defineProps<{ matrix: OverlapMatrix }>();
</script>

<style scoped lang="scss">
.overlap-matrix {
  overflow-x: auto;

  &__table {
    width: 100%;
    border-collapse: collapse;
    font-variant-numeric: tabular-nums;
  }

  &__caption {
    padding: 0 0 var(--space-standard);
    font-size: var(--text-small);
    line-height: 1.6;
    color: var(--text-tertiary-ink);
    text-align: left;
  }

  &__corner,
  &__head {
    padding: 6px 4px;
    font-size: var(--text-small);
    font-weight: 600;
    color: var(--text-secondary);
    text-align: center;
    border-bottom: 1px solid var(--border-default);
  }

  &__corner {
    text-align: left;
  }

  &__row-head {
    display: flex;
    gap: 6px;
    align-items: baseline;
    padding: 6px 8px 6px 0;
    font-size: var(--text-small);
    font-weight: 500;
    color: var(--text-secondary);
    text-align: left;
    white-space: nowrap;
  }

  &__index {
    color: var(--text-tertiary-ink);
  }

  /* 名字可能很长：截断靠 title 兜底，避免一行把矩阵撑出屏幕 */
  &__name {
    max-width: 12em;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  &__cell {
    min-width: 56px;
    padding: 6px 4px;
    font-size: var(--text-small);
    font-weight: 600;
    text-align: center;
    border: 1px solid var(--border-subtle);
    border-radius: 4px;

    &.is-self {
      color: var(--text-disabled);
      background: var(--bg-soft);
    }

    &.is-none {
      font-weight: 500;
      color: var(--text-tertiary-ink);
    }

    &.is-low {
      color: var(--text-secondary);
    }

    &.is-mid {
      color: var(--color-warning-ink);
      background: color-mix(in srgb, var(--color-warning) 22%, var(--bg-card));
    }

    &.is-high {
      color: var(--color-danger-ink);
      background: color-mix(in srgb, var(--color-danger) 12%, var(--bg-card));
    }

    /* 不可比用斜纹而不是纯色：它既不是 0，也不是一个「量」 */
    &.is-incomparable {
      font-weight: 500;
      font-size: var(--text-label);
      color: var(--text-tertiary-ink);
      background: repeating-linear-gradient(
        45deg,
        var(--bg-soft) 0 4px,
        transparent 4px 8px
      );
    }
  }

  &__legend {
    display: flex;
    flex-wrap: wrap;
    gap: 12px;
    padding: 0;
    margin: var(--space-standard) 0 0;
    font-size: var(--text-small);
    list-style: none;
    color: var(--text-tertiary-ink);
  }

  &__legend-item.is-mid {
    color: var(--color-warning-ink);
  }

  &__legend-item.is-high {
    color: var(--color-danger-ink);
  }

  &__hint {
    margin: 4px 0 0;
    font-size: var(--text-small);
    color: var(--text-tertiary-ink);
  }
}
</style>
