<template>
  <!--
    组合内基金两两相关性矩阵（#2686 第二交付）。

    与重叠度矩阵对照着看：重叠度回答「重仓股是否重复」，相关性回答「涨跌是否同步」。
    两者成员一致（后端同一份裁剪结果），切换视图时行列不变。

    格子五态见 `holdingCorrelationMatrix.ts` 模块头：自比 / 高 / 中 / 低 / 负相关 /
    算不出（无净值 / 样本不足 / 无波动）。**算不出绝不能画成 0.00**——那是「不相关」，
    而真相是「没有信息」。
  -->
  <div class="correlation-matrix">
    <table class="detail-table">
      <caption class="correlation-matrix__caption">
        行与列是同一批基金（按持仓市值降序），格子是近 {{ matrix.window }} 日收益的
        皮尔逊相关系数（同期交易日不少于 {{ matrix.minOverlap }} 天）。对角线是自比；
        ρ 越高说明「一起涨一起跌」——分散效果越差。
      </caption>
      <thead>
        <tr>
          <th scope="col">基金（市值权重）</th>
          <th
            v-for="(fund, index) in matrix.funds"
            :key="fund.fund_code"
            scope="col"
            class="detail-table__num correlation-matrix__head"
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
            class="correlation-matrix__row-head"
            :title="`${row.fund.name}（${row.fund.fund_code}）`"
          >
            <span class="correlation-matrix__index">{{ rowIndex + 1 }}</span>
            <span class="correlation-matrix__name">{{ row.fund.name }}</span>
            <span class="correlation-matrix__weight">
              {{ row.fund.market_value_pct.toFixed(1) }}%
            </span>
          </th>
          <td
            v-for="(cell, colIndex) in row.cells"
            :key="colIndex"
            class="detail-table__num correlation-matrix__cell"
            :class="`is-${cell.tone}`"
            :title="cell.title"
          >
            {{ cell.text }}
          </td>
        </tr>
      </tbody>
    </table>

    <ul class="correlation-matrix__legend">
      <li class="correlation-matrix__legend-item is-high">ρ ≥ 0.8（几乎同步）</li>
      <li class="correlation-matrix__legend-item is-mid">0.5 ≤ ρ &lt; 0.8</li>
      <li class="correlation-matrix__legend-item is-low">−0.3 ≤ ρ &lt; 0.5</li>
      <li class="correlation-matrix__legend-item is-negative">
        ρ &lt; −0.3（反向）
      </li>
      <li class="correlation-matrix__legend-item is-unavailable">
        算不出（无净值 / 样本不足 / 无波动）
      </li>
    </ul>

    <!-- 可算出比例与覆盖范围必须与矩阵同屏：前者说「这堆数可信到什么程度」，
         后者说「这堆数代表多少仓位」，缺一个都会被读成「整体结论」 -->
    <p class="correlation-matrix__meta">
      可算出 {{ ratioText }}；{{ matrix.coverageText }}
    </p>
  </div>
</template>

<script setup lang="ts">
import { computed } from "vue";
import {
  computedRatioText,
  type CorrelationMatrix
} from "./holdingCorrelationMatrix";

defineOptions({ name: "HoldingCorrelationMatrix" });

const props = defineProps<{ matrix: CorrelationMatrix }>();

const ratioText = computed(() => computedRatioText(props.matrix));
</script>

<style scoped lang="scss">
.correlation-matrix {
  overflow-x: auto;

  &__caption {
    padding: 0 0 var(--space-standard);
    font-size: var(--text-small);
    line-height: 1.6;
    color: var(--text-tertiary-ink);
    text-align: left;
  }

  /* 列头只放序号：名字太长会把格子撑变形，完整名字走 title */
  &__head {
    text-align: center;
  }

  &__row-head {
    font-size: var(--text-label);
    font-weight: 500;
    color: var(--text-secondary);
    white-space: nowrap;
  }

  &__index,
  &__weight {
    color: var(--text-tertiary-ink);
    font-variant-numeric: tabular-nums;
  }

  &__weight {
    margin-left: 6px;
    font-size: var(--text-small);
  }

  &__name {
    max-width: 10em;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  &__cell {
    font-weight: 600;
    text-align: center;
    font-variant-numeric: tabular-nums;

    &.is-self {
      color: var(--text-disabled);
      background: var(--bg-soft);
    }

    &.is-low {
      color: var(--text-secondary);
    }

    &.is-mid {
      color: var(--color-warning-ink);
      background: color-mix(in srgb, var(--color-warning) 18%, var(--bg-card));
    }

    &.is-high {
      color: var(--color-danger-ink);
      background: color-mix(in srgb, var(--color-danger) 14%, var(--bg-card));
    }

    /* 负相关是「分散有效」，与警示色相反 */
    &.is-negative {
      color: var(--color-success-ink);
      background: color-mix(in srgb, var(--color-success) 12%, var(--bg-card));
    }

    /* 算不出用斜纹：既不是一个「量」，也不该被读成 0 */
    &.is-unavailable {
      font-size: var(--text-label);
      font-weight: 500;
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
    color: var(--text-tertiary-ink);
    list-style: none;
  }

  &__legend-item.is-high {
    color: var(--color-danger-ink);
  }

  &__legend-item.is-mid {
    color: var(--color-warning-ink);
  }

  &__legend-item.is-negative {
    color: var(--color-success-ink);
  }

  &__meta {
    margin: 4px 0 0;
    font-size: var(--text-small);
    line-height: 1.6;
    color: var(--text-tertiary-ink);
  }
}
</style>
