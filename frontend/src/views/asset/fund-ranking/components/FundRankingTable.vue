<template>
  <!-- 表头吸顶 + 冻结列（#3200）：旧实现是自建 <table> + `.table-scroll{overflow-x:auto}`，
       而 overflow 非 visible 的容器就是 sticky 的「最近滚动祖先」——thead 的
       position:sticky 被截断在容器内，滚出视口即失效（实测 top=494px）。
       迁 el-table 后 header-wrapper / body-wrapper 分层、横滚落在 body 内部，
       外框纵向放开即可让表头吸到页面滚动容器（见 fundRankingTable.css「吸顶链」）。
       横滚是真实需求（10 列在 1366 屏放不下），不靠删列解决。 -->
  <div class="ranking-table-wrap">
    <el-table
      class="ranking-table"
      :data="rows"
      :default-sort="defaultSort"
      :cell-class-name="cellClassName"
      @sort-change="onSortChange"
    >
      <!-- 冻结列（design.md「冻结列与横向滚动规范」）：排名 + 基金恒定在左，
           滚到右侧指标时始终知道这行是哪只基金 -->
      <el-table-column
        type="index"
        label="#"
        :width="RANK_COL_WIDTH"
        fixed="left"
        align="left"
        class-name="col-rank"
        label-class-name="col-rank"
      />
      <el-table-column
        prop="fund_code"
        label="基金"
        :width="FUND_COL_WIDTH"
        fixed="left"
        align="left"
        class-name="col-fund"
        label-class-name="col-fund"
      >
        <template #default="{ row }">
          <FundRankingNameCell :row="asRow(row)" @open="emit('open', $event)" />
        </template>
      </el-table-column>

      <!-- 双层表头：分组列（colspan 由子列数自动得出）+ 指标子列。
           10 个数值列平铺时用户分不清「窗口列是什么」「近1月是涨幅还是夏普」——
           分组行给结构：组内同口径、组间不同口径；分组行不可点，hover 讲组口径。 -->
      <el-table-column
        v-for="g in columnGroups"
        :key="g.label"
        :label="g.label"
        align="left"
        :label-class-name="groupHeaderClass(g)"
      >
        <template #header>
          <!-- th 的属性无法经 el-table-column 透传：组口径说明改挂 inner span 的 title
               （读屏与系统 tooltip 都能读到），鼠标悬停仍走 el-tooltip -->
          <el-tooltip placement="top" :content="g.tip">
            <span class="th-group__label" :title="g.tip">{{ g.label }}</span>
          </el-tooltip>
        </template>

        <!-- 指标列即排序入口（#2298）：整块可点，排序三角与 aria-sort 用 el-table 原生
             （sortable="custom" 只上抛事件，排序口径仍在服务端）。 -->
        <el-table-column
          v-for="col in columnsOf(g)"
          :key="col.key"
          :prop="col.key"
          :label="col.label"
          :min-width="col.minWidth"
          align="right"
          sortable="custom"
          :sort-orders="sortOrdersOf(col)"
          :label-class-name="metricHeaderClass(col)"
        >
          <template #header>
            <!-- 表头 hover 弹指标说明（2026-10-17 去常驻 i 图标降噪）：
                 说明里带「越高/越低越好」——术语不解释，用户读不懂数字 -->
            <el-tooltip placement="top" :content="col.hint">
              <span class="th-label" :title="col.hint">{{ col.label }}</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">
            <span
              v-if="col.bar"
              class="data-bar"
              :style="{ width: barWidth(asRow(row), col.key, barRanges) }"
              aria-hidden="true"
            />
            <span class="num-text">{{ formatCell(asRow(row), col) }}</span>
          </template>
        </el-table-column>
      </el-table-column>
    </el-table>
  </div>
</template>

<script setup lang="ts">
// 同类优选表格（#980 拆分自 index.vue；#3200 由自建 <table> 迁 el-table）。
//
// 只管「怎么摆」：取值与配色是 ../rankingCells 的纯函数，列定义是 ../rankingColumns
// 的数据，状态与取数在 ../composables/useFundRanking。「基金」列再拆一层到
// ./FundRankingNameCell.vue。排序与跳转一律回抛父层——指标与方向是页面级状态。
//
// 为什么必须 el-table 而不是自建 table：自建 table 想同时要「横向滚动 + 表头吸顶」时，
// `overflow-x:auto` 那层必然成为 sticky 的截断点，纵向 visible 与横向 auto 在同一个
// 元素上无法成立（#3200 实测：改 overflow-y:clip 也无效）。el-table 的 header / body
// 是两层 DOM，横滚落在 body 内部，两者才能同时成立。
import { computed } from "vue";
import type { TableColumnCtx } from "element-plus";
import type { FundRiskRankingRow } from "@/api/products";
import {
  barWidth,
  buildBarRanges,
  formatCell,
  numClass
} from "../rankingCells";
import {
  FUND_COL_WIDTH,
  RANK_COL_WIDTH,
  type ColumnGroup,
  type RankingColumn
} from "../rankingColumns";
import FundRankingNameCell from "./FundRankingNameCell.vue";

/** el-table 的排序档位（不含 null：取消排序后箭头消失、数据仍是上次排序，自相矛盾） */
type SortOrder = "ascending" | "descending";

const props = defineProps<{
  rows: FundRiskRankingRow[];
  tableColumns: RankingColumn[];
  columnGroups: ColumnGroup[];
  /** 当前排序指标键：表头高亮（th.col-active）+ 实心箭头 */
  metric: string;
  /** 当前排序方向 */
  order: "asc" | "desc";
}>();
const emit = defineEmits<{
  /** 点表头：父层按新指标 / 方向重取 */
  sort: [payload: { key: string; order: "asc" | "desc" }];
  /** 点基金名：父层跳详情 */
  open: [code: string];
}>();

/** 数据条长度基准 = 当前榜单内该列的 min / max（换类型或换列即重算） */
const barRanges = computed(() =>
  buildBarRanges(props.rows, props.tableColumns)
);

/** 列 key → 定义：按分组 keys 取列，保证「分组 colspan = 子列数」天然成立
 *  （分组 keys 必须与列定义同序全覆盖，由 rankingColumns.spec.ts 钉住） */
const columnByKey = computed(
  () => new Map(props.tableColumns.map(c => [c.key, c]))
);

/** 每组的首列 key 集合：用于在指标行给「组首列」画左侧分隔竖线，
 *  与分组行的组间竖线上下贯穿——组边界在双层表头里一条线连到底，不再断裂。 */
const groupFirstKeys = computed(
  () => new Set(props.columnGroups.map(g => g.keys[0]).filter(Boolean))
);

/** 首屏排序态：由页面默认值（夏普 / 降序）直接映射，箭头与 aria-sort 初始化即正确 */
const defaultSort = computed(() => ({
  prop: props.metric,
  order: (props.order === "desc" ? "descending" : "ascending") as SortOrder
}));

/** el-table 的插槽行类型是 DefaultRow（不含业务字段），渲染前收窄回榜单行类型：
 *  收窄放在一处，模板里不再散落 as 断言 */
function asRow(row: unknown): FundRiskRankingRow {
  return row as FundRiskRankingRow;
}

function columnsOf(group: ColumnGroup): RankingColumn[] {
  return group.keys
    .map(key => columnByKey.value.get(key))
    .filter((col): col is RankingColumn => Boolean(col));
}

/** 首击方向 = 指标语义方向（dir）：high（数值大者好；含以负数存储的最大回撤，
 *  -8 优于 -25）⇒ 降序；low（UI：正数、越小越不煎熬）⇒ 升序。
 *  旧版一律 desc，点 UI 列会先把「最煎熬」的排前面——从劣到优，语义错。
 *  后端 SORTABLE_METRICS 的默认方向同此规则（ulcer_index=False 升序）。 */
function sortOrdersOf(col: RankingColumn): SortOrder[] {
  return col.dir === "low"
    ? ["ascending", "descending"]
    : ["descending", "ascending"];
}

function groupHeaderClass(group: ColumnGroup): string {
  return [
    "th-group",
    group.keys.includes(props.metric) ? "th-group--active" : ""
  ]
    .filter(Boolean)
    .join(" ");
}

function metricHeaderClass(col: RankingColumn): string {
  return [
    "th-metric",
    col.key === props.metric ? "col-active" : "",
    groupFirstKeys.value.has(col.key) ? "col-group-start" : ""
  ]
    .filter(Boolean)
    .join(" ");
}

/** 数据单元格类名：数值列统一 col-num（数据条定位锚点），收益列按涨跌染色
 *  （风险列不染色，见 rankingCells 的口径红线）。排序列**不加**数据区类名——
 *  它的锚点在表头（th.col-active）：旧实现给整列铺暖色带，与夏普 / 卡玛的数据条
 *  叠在一起（条比带浅，读成「带上的白色缺口」），见 fundRankingTable.css。
 *  「#」与「基金」两列 property 为空 → 空串，不参与上述任何一档。 */
function cellClassName({
  row,
  column
}: {
  row: FundRiskRankingRow;
  column: TableColumnCtx<FundRiskRankingRow>;
}): string {
  const col = column.property
    ? columnByKey.value.get(column.property)
    : undefined;
  if (!col) return "";
  return ["col-num", col.kind === "return" ? numClass(row, col) : ""]
    .filter(Boolean)
    .join(" ");
}

/** el-table 排序事件 → 页面级状态。方向直接取 el-table 算好的档位：
 *  首击方向已由 sortOrdersOf 决定，这里再按 dir 推断一次只会多出第二份真相。 */
function onSortChange({
  prop,
  order
}: {
  prop?: string | null;
  order?: SortOrder | null;
}) {
  if (!prop || !order) return;
  emit("sort", { key: prop, order: order === "ascending" ? "asc" : "desc" });
}
</script>

<style src="./fundRankingTable.css"></style>
