<!-- 关联 ETF 对比表主体（12 列宽表 + 指数基准行 + 右缘渐隐） -->
<script setup lang="ts">
import { nextTick, watch } from "vue";
import { RouterLink } from "vue-router";
import type {
  IndexEtfCompareRow,
  IndexEtfCompareWindows
} from "@/api/products";
import {
  DASH,
  FEE_TITLE,
  SCALE_TITLE,
  TRACKING_TITLE,
  WINDOWS,
  amountText,
  etfRouteOf,
  feeText,
  navText,
  pctClass,
  pctText,
  scaleText,
  trackingText
} from "./etfCompareModel";
import { useScrollFade } from "./useScrollFade";

const props = defineProps<{
  rows: IndexEtfCompareRow[];
  /** 指数基准行的数据；`null` = 全窗口缺失，不画基准行 */
  baseline: IndexEtfCompareWindows | null;
  indexCode: string;
}>();

const { scroller, showFade, measure } = useScrollFade();

// 行挂载后表格宽度才确定，此时再测一次能否横滚
watch(
  () => props.rows,
  () => nextTick(measure)
);
</script>

<template>
  <div class="etf-cmp__scroll-wrap">
    <div ref="scroller" class="etf-cmp__scroll" @scroll="measure">
      <!-- 表口径见 `_detail-table.scss`（#553）：`--fixed` + 下面的 min-width 一起管横滚；
           涨跌色仍由 `etf-cmp__num--rise/fall` 按语义令牌给，共享类只管对齐与字宽。 -->
      <table class="detail-table detail-table--fixed etf-cmp__table">
        <thead>
          <tr>
            <th class="etf-cmp__th">代码</th>
            <th class="etf-cmp__th">名称</th>
            <th class="detail-table__num etf-cmp__th">最新净值</th>
            <th class="detail-table__num etf-cmp__th">当日涨幅</th>
            <th class="detail-table__num etf-cmp__th">成交额</th>
            <th class="detail-table__num etf-cmp__th" :title="SCALE_TITLE">
              规模
            </th>
            <th class="detail-table__num etf-cmp__th" :title="FEE_TITLE">
              费率（年）
            </th>
            <th
              v-for="w in WINDOWS"
              :key="w.key"
              class="detail-table__num etf-cmp__th"
            >
              {{ w.label }}
            </th>
            <th class="detail-table__num etf-cmp__th" :title="TRACKING_TITLE">
              跟踪差（近1年）
            </th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in props.rows" :key="row.code">
            <td class="detail-table__num etf-cmp__td etf-cmp__td--mono">
              {{ row.code }}
            </td>
            <td class="detail-table__product etf-cmp__td">
              <RouterLink
                v-if="etfRouteOf(row.code)"
                class="etf-cmp__link"
                :to="etfRouteOf(row.code)"
              >
                {{ row.name || row.code }}
              </RouterLink>
              <span v-else>{{ row.name || row.code }}</span>
            </td>
            <td class="detail-table__num etf-cmp__td">
              {{ navText(row) }}
            </td>
            <td
              class="detail-table__num etf-cmp__td"
              :class="pctClass(row.change_pct)"
            >
              {{ pctText(row.change_pct) }}
            </td>
            <td class="detail-table__num etf-cmp__td">
              {{ amountText(row) }}
            </td>
            <td class="detail-table__num etf-cmp__td" :title="SCALE_TITLE">
              {{ scaleText(row) }}
            </td>
            <td class="detail-table__num etf-cmp__td" :title="FEE_TITLE">
              {{ feeText(row) }}
            </td>
            <td
              v-for="w in WINDOWS"
              :key="w.key"
              class="detail-table__num etf-cmp__td"
              :class="pctClass(row.returns[w.key])"
            >
              {{ pctText(row.returns[w.key]) }}
            </td>
            <td
              class="detail-table__num etf-cmp__td"
              :class="pctClass(row.tracking_diff_y1)"
              :title="TRACKING_TITLE"
            >
              {{ trackingText(row.tracking_diff_y1) }}
            </td>
          </tr>
        </tbody>
        <!-- 指数基准行：跟踪差的比较基准同列摆放，让「差」可逐行验算 -->
        <tfoot v-if="props.baseline">
          <tr>
            <td class="detail-table__num etf-cmp__td etf-cmp__td--mono">
              {{ props.indexCode }}
            </td>
            <td class="etf-cmp__td">指数</td>
            <td class="detail-table__num etf-cmp__td">{{ DASH }}</td>
            <td class="detail-table__num etf-cmp__td">{{ DASH }}</td>
            <td class="detail-table__num etf-cmp__td">{{ DASH }}</td>
            <td class="detail-table__num etf-cmp__td">{{ DASH }}</td>
            <td class="detail-table__num etf-cmp__td">{{ DASH }}</td>
            <td
              v-for="w in WINDOWS"
              :key="w.key"
              class="detail-table__num etf-cmp__td"
              :class="pctClass(props.baseline[w.key])"
            >
              {{ pctText(props.baseline[w.key]) }}
            </td>
            <td class="detail-table__num etf-cmp__td">{{ DASH }}</td>
          </tr>
        </tfoot>
      </table>
    </div>
    <span v-if="showFade" class="etf-cmp__fade" aria-hidden="true" />
  </div>
</template>

<style scoped>
/* 12 列宽表（#2333 补规模/费率两列）：窄屏横向滚动（不压缩列宽逐字竖排），滚动条贴卡内边缘 */
.etf-cmp__scroll-wrap {
  position: relative;
  min-width: 0;
}

.etf-cmp__scroll {
  min-width: 0;
  overflow-x: auto;
}

/* 宽度 / 字号 / padding / 分隔线 / 表头 / 表尾 / 数字列来自 `.detail-table`（#553）。
   本组件只剩两件这张表独有的：最小宽度（决定何时开始横滚）与代码列的弱色。 */
.etf-cmp__table {
  min-width: 760px;
}

.etf-cmp__td {
  color: var(--text-primary);
}

.etf-cmp__td--mono {
  color: var(--text-secondary);
}

.etf-cmp__num--rise {
  /* #2314：文字色统一 -ink 文字级令牌（图形级 --color-rise 禁作前景文字，design.md:131） */
  color: var(--color-rise-ink);
}

.etf-cmp__num--fall {
  color: var(--color-fall-ink);
}

.etf-cmp__link {
  color: var(--text-primary);
  text-decoration: none;

  &:hover,
  &:focus-visible {
    color: var(--brand-ink); /* #2314：前景文字用品牌文字级 */
  }

  &:focus-visible {
    outline: 2px solid var(--brand-700);
    outline-offset: 2px;
  }
}

/* 右缘渐隐：固定在可视区右缘，不随内容滚动；pointer-events:none 不挡点击 */
.etf-cmp__fade {
  position: absolute;
  top: 0;
  right: 0;
  bottom: 0;
  width: 28px;
  pointer-events: none;
  background: linear-gradient(to right, transparent, var(--bg-card));
}

/* 基准行不是「又一只 ETF」：弱化底色区分，避免被当成可买标的。
   字号 / 上边线已由 `.detail-table tfoot` 给，这里只补底色与更弱的文字色。 */
.etf-cmp__table tfoot .etf-cmp__td {
  color: var(--text-secondary);
  background: var(--bg-muted);
}
</style>
