<template>
  <!-- 横向滚动容器：左侧「排名 + 基金」两列 sticky，滚到右侧指标时
               始终知道这行是哪只基金（design.md 冻结列规范） -->
  <div class="table-scroll">
    <table class="ranking-table w-full text-sm">
      <thead>
        <!-- 双层表头（2026-10-17 第二轮）：10 个数值列平铺时，用户分不清
                     「窗口列是什么」「近1月是涨幅还是夏普」。分组行给结构——
                     组内同口径、组间不同口径；分组行不可点，hover 讲组口径。 -->
        <tr class="th-group-row">
          <th rowspan="2" class="col-rank">#</th>
          <th rowspan="2" class="col-fund">基金</th>
          <th
            v-for="g in columnGroups"
            :key="g.label"
            class="th-group"
            :colspan="g.keys.length"
            :aria-label="g.tip"
          >
            <el-tooltip placement="top" :content="g.tip">
              <span class="th-group__label">{{ g.label }}</span>
            </el-tooltip>
          </th>
        </tr>
        <tr class="th-metric-row">
          <!-- 指标列即排序入口（#2298）：整块可点，当前排序列加粗高亮 + 实心箭头。
                       表头 hover 弹指标说明（2026-10-17 去常驻 i 图标降噪），
                       说明里带「越高/越低越好」——术语不解释，用户读不懂数字。 -->
          <th
            v-for="col in tableColumns"
            :key="col.key"
            class="col-sortable"
            :class="{ 'col-active': col.key === metric }"
            :aria-sort="ariaSort(col.key)"
            @click="emit('sort', col.key)"
          >
            <el-tooltip placement="top" :content="col.hint">
              <span class="th-with-tip">
                <span class="th-label">{{ col.label }}</span>
                <span class="th-sort">
                  <IconifyIconOffline
                    v-if="col.key === metric"
                    :icon="
                      order === 'desc' ? 'ep:caret-top' : 'ep:caret-bottom'
                    "
                    class="th-sort__caret th-sort__caret--active"
                  />
                  <template v-else>
                    <IconifyIconOffline
                      icon="ep:caret-top"
                      class="th-sort__caret"
                    />
                    <IconifyIconOffline
                      icon="ep:caret-bottom"
                      class="th-sort__caret"
                    />
                  </template>
                </span>
              </span>
            </el-tooltip>
          </th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="(row, index) in rows" :key="row.fund_code">
          <td class="col-rank">{{ index + 1 }}</td>
          <td class="col-fund">
            <FundRankingNameCell :row="row" @open="emit('open', $event)" />
          </td>
          <td
            v-for="col in tableColumns"
            :key="col.key"
            :class="[
              'col-num',
              { 'col-active': col.key === metric },
              col.kind === 'return' ? numClass(row, col) : ''
            ]"
          >
            <span
              v-if="col.bar"
              class="data-bar"
              :style="{ width: barWidth(row, col.key, barRanges) }"
              aria-hidden="true"
            />
            <span class="num-text">{{ formatCell(row, col) }}</span>
          </td>
        </tr>
      </tbody>
    </table>
  </div>
</template>

<script setup lang="ts">
// 同类优选表格（#980 拆分自 index.vue）：结构 / sticky 列 / 双层表头 / 排序入口。
//
// 只管「怎么摆」：取值与配色是 ../rankingCells 的纯函数，列定义是 ../rankingColumns
// 的数据，状态与取数在 ../composables/useFundRanking。「基金」列再拆一层到
// ./FundRankingNameCell.vue。排序与跳转一律回抛父层——指标与方向是页面级状态。
import { computed } from "vue";
import { Icon as IconifyIconOffline } from "@iconify/vue";
import type { FundRiskRankingRow } from "@/api/products";
import {
  barWidth,
  buildBarRanges,
  formatCell,
  numClass
} from "../rankingCells";
import type { ColumnGroup, RankingColumn } from "../rankingColumns";
import FundRankingNameCell from "./FundRankingNameCell.vue";

const props = defineProps<{
  rows: FundRiskRankingRow[];
  tableColumns: RankingColumn[];
  columnGroups: ColumnGroup[];
  /** 当前排序指标键：高亮列 + 实心箭头 */
  metric: string;
  /** 当前排序方向 */
  order: "asc" | "desc";
}>();
const emit = defineEmits<{
  /** 点表头：父层改 metric / order 并重取 */
  sort: [key: string];
  /** 点基金名：父层跳详情 */
  open: [code: string];
}>();

/** 数据条长度基准 = 当前榜单内该列的 min / max（换类型或换列即重算） */
const barRanges = computed(() =>
  buildBarRanges(props.rows, props.tableColumns)
);

/** aria-sort：给屏幕阅读器说明当前列的排序状态（未参与排序的列 = none） */
function ariaSort(key: string): "none" | "ascending" | "descending" {
  if (key !== props.metric) return "none";
  return props.order === "desc" ? "descending" : "ascending";
}
</script>

<style lang="scss" scoped>
/* ── 表格（2026-10-17 重构）──────────────────────────────────────────────
   - border-collapse: separate：sticky 列在 collapse 下边框会随滚动「漂移」；
   - thead sticky top:0（滚动祖先是布局层 .el-scrollbar__wrap，#1528 同款）；
   - 左两列（排名 / 基金）sticky：横向滚到右侧指标时始终知道在看哪只；
   - 所有 th/td 不透明底色：sticky 单元格透明会透出滚动过的内容；
   - 行 hover / 持仓行底色：覆盖含 sticky 列在内的整行。 */
.table-scroll {
  overflow-x: auto;
}

.ranking-table {
  border-spacing: 0;
  border-collapse: separate;

  th,
  td {
    padding: 14px var(--space-4); /* 行高 ≈ 44px（design.md 表格行高基线） */
    text-align: right;
    white-space: nowrap;
    background: var(--bg-card);
    border-bottom: 1px solid var(--border-subtle, var(--border-light));
  }

  th {
    position: sticky;
    z-index: 2;
    font-size: var(--text-label);
    font-weight: 600;
    color: var(--text-tertiary-ink);

    /* 表头底色对齐 el-table 基线（design.md Table 节：--bg-muted）——
       页面自建表头不另起炉灶；sticky 单元格必须不透明，--bg-muted 是实色 ✓ */
    background: var(--bg-muted);
  }

  /* 双层表头（2026-10-17 第二轮）：分组行吸顶 top:0，指标行下移一行高度。
     两行都 sticky——纵向滚到长列表底部时，指标名与所属组始终在场。 */
  .th-group-row th {
    top: 0;
    height: 30px;
    padding: 5px var(--space-3);
    font-size: var(--text-label);
    font-weight: 500;
  }

  .th-metric-row th {
    top: 30px; /* = 分组行高度 */
  }

  .th-group {
    text-align: center;
    cursor: help;
  }

  td {
    font-variant-numeric: tabular-nums; /* 小数点纵向绝对对齐（design.md） */
    color: var(--text-primary);
  }

  .col-rank,
  .col-fund {
    text-align: left;
  }

  .col-rank {
    position: sticky;
    left: 0;
    z-index: 1;
    width: 48px;
    color: var(--text-tertiary-ink);
  }

  .col-fund {
    position: sticky;
    left: 48px; /* = 排名列宽 */
    z-index: 1;
    min-width: 220px;
    max-width: 260px;
  }

  /* 表头左两列同时参与两个方向 sticky，z-index 需压过普通表头与左列 */
  thead .col-rank,
  thead .col-fund {
    z-index: 3;
  }

  /* 行悬停：整行（含 sticky 列）轻微底色，对齐 el-table 基线（--bg-soft） */
  tbody tr:hover td {
    background: var(--bg-soft);
  }

  /* 持仓行底纹已删（2026-10-17 第二轮）：快照池里持仓占多数，常驻底纹没有
     「找我的那只」的信号价值，唯一一只自选行反而被读成 bug（用户实测反馈）。
     「持仓 / 自选」徽章在基金名旁，已承载该信息；行视觉回归统一。 */

  /* 当前排序指标高亮（2026-10-17 第二轮，对齐 el-table 基线）：
     EP 惯例 = 加粗 + 文字提主色 + 箭头变主题色。不用红字——金融表里红字
     读作警告；不用灰底——全站表头底是 --bg-muted，另起一档灰底即语言分裂。
     排序列辨识度靠加粗 + 箭头 + 卡片标题的「按X排序」说明，三处互证。 */
  .col-active {
    font-weight: 600;
    color: var(--text-primary);
  }

  /* 收益列涨跌色（-ink 级：白底 AA 达标；符号同色，见 formatCell） */
  .num--rise {
    color: var(--color-rise-ink);
  }

  .num--fall {
    color: var(--color-fall-ink);
  }

  /* 数据条（夏普 / 卡玛）：极浅品牌色底条衬在数字背后，
     长度 = 当前榜单内相对位置；纯装饰，读屏隐藏。 */
  .col-num {
    position: relative;
  }

  .data-bar {
    position: absolute;
    top: 50%;
    right: var(--space-4);
    left: auto;
    height: 22px;
    pointer-events: none;
    background: var(--brand-100);
    border-radius: var(--radius-xs);
    transform: translateY(-50%);
  }

  .num-text {
    position: relative;
    z-index: 1;
  }
}

/* 表头（去常驻 i 图标，2026-10-17）：整块 hover 弹 tooltip 讲指标含义，
   文字下方浅虚线下划线作「有说明」暗示；箭头区与文字同组不进 tooltip 也行——
   整组包进 tooltip，悬停即讲。 */
.col-sortable {
  cursor: pointer;
  user-select: none;

  /* 当前排序列的 brand 高亮优先，hover 不改它 */
  &:not(.col-active):hover {
    color: var(--text-primary);
    background: var(--bg-hover);
  }
}

.th-with-tip {
  display: inline-flex;
  gap: 4px;
  align-items: center;
}

.th-label {
  border-bottom: 1px dashed var(--border-default);
}

.th-sort {
  display: inline-flex;
  flex-direction: column;
  line-height: 1;
  vertical-align: middle;

  &__caret {
    font-size: var(--text-label);
    color: var(--text-tertiary-ink);
    opacity: 0.3;
    transition: opacity 0.15s ease;

    &--active {
      color: var(--brand-700);
      opacity: 1;
    }
  }
}

.col-sortable:hover .th-sort__caret:not(.th-sort__caret--active) {
  opacity: 0.75;
}
</style>
