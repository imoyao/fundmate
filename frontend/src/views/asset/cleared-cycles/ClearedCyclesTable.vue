<!--
  ClearedCyclesTable · 清仓周期明细表（2026-11-27 从 ClearedCyclesSection 拆出）

  为什么拆：334 行一次性铺开会把页面顶到 17 000px，净值曲线被压到 20 屏之外；
  同时「按哪一列排」「点产品进详情」这两件事让原文件逼近 400 行门槛。

  两件事都在**前端**做（口径见 clearedCyclesTable.ts 文件头）：
  分页只决定「看到哪几行」，排序只决定「按哪一列」，都不改任何汇总数字。

  列序按「先看赚了多少，再看是在哪买的、什么时候买的」排 —— 收益 / 收益率紧接着产品，
  账户随后（同一只产品可能在多个账户买过，周期不拆），日期收成一列「持有区间」：
  首买日 / 末卖日 是解释项，不是结论。
-->
<template>
  <CardBlock>
    <!-- table-col-allow: 7 列合计 804（产品 168 为弹性下限），1280 视口下表宽仅 692 ⇒ 窄屏必横滚；金额与百分比列固定宽才好竖着比大小（#3210） -->
    <el-table
      :data="pageRows"
      size="small"
      empty-text="暂无已清仓周期（标的卖出且份额归零后自动归档）"
      :default-sort="{ prop: DEFAULT_SORT_KEY, order: 'descending' }"
      @sort-change="onSortChange"
    >
      <el-table-column
        prop="name"
        label="产品"
        min-width="168"
        sortable="custom"
      >
        <template #default="{ row }">
          <div class="cleared-table__product">
            <!-- 产品名是按钮而不是 div + @click：键盘可达、读屏可聚焦，
                 跳转目标由后端 resolve 判定品类（前端不按代码形态猜） -->
            <el-button
              link
              class="cleared-table__name"
              :loading="openingSymbol === row.symbol"
              @click="openProduct(asCycle(row))"
            >
              {{ row.name || row.symbol || "--" }}
            </el-button>
            <span v-if="row.symbol" class="cleared-table__code">
              # {{ row.symbol }}
            </span>
          </div>
        </template>
      </el-table-column>

      <el-table-column
        prop="realized_pnl"
        label="已实现盈亏"
        width="124"
        align="right"
        sortable="custom"
      >
        <template #default="{ row }">
          <MoneyDisplay
            :value="row.realized_pnl"
            show-sign
            auto-color
            size="sm"
          />
        </template>
      </el-table-column>

      <el-table-column
        prop="pnl_pct"
        label="收益率"
        width="88"
        align="right"
        sortable="custom"
      >
        <template #default="{ row }">
          <RiseFallText
            v-if="row.pnl_pct !== null"
            :value="row.pnl_pct"
            size="sm"
          />
          <span v-else class="cleared-table__na">--</span>
        </template>
      </el-table-column>

      <!-- 账户：周期不按账户拆分（同一只产品多账户买入仍是一轮），故这里可能多个。
           展示首个 + 其余数量，悬浮看全名——列里塞全名会把日期列挤出去。
           120px 是实测下限：再窄「同花顺（银河证券）」只剩两个字 + 省略号。 -->
      <el-table-column
        prop="ledger_names"
        label="账户"
        width="120"
        sortable="custom"
      >
        <template #default="{ row }">
          <span
            v-if="row.ledger_names?.length"
            class="cleared-table__ledger"
            :title="ledgerTitle(row)"
          >
            <span class="cleared-table__ledger-name">
              {{ row.ledger_names[0] }}
            </span>
            <span
              v-if="row.ledger_names.length > 1"
              class="cleared-table__ledger-more"
            >
              +{{ row.ledger_names.length - 1 }}
            </span>
          </span>
          <span v-else class="cleared-table__na">--</span>
        </template>
      </el-table-column>

      <!-- 首买日 / 末卖日 合并成一列「持有区间」：两列各 104px 只为了读一个时间段，
           而用户要的是「赚了多少」不是「哪天买的」（#第 5 条）。合并后腾出的宽度
           正好给账户列。
           日期**分两行**而不是 `起 → 止` 一行：实测单行 23 字符要 206px，而 1440
           视口表宽只有 852，给了 206 就得再砍别的列；两行各 10 字符 120px 就够，
           且起止上下对齐、比一行中间夹个箭头更好扫。 -->
      <el-table-column
        prop="first_buy_date"
        label="持有区间"
        width="120"
        sortable="custom"
      >
        <template #default="{ row }">
          <div
            v-if="row.first_buy_date || row.last_sell_date"
            class="cleared-table__range"
          >
            <span>{{ row.first_buy_date || "--" }}</span>
            <span class="cleared-table__range-end">
              → {{ row.last_sell_date || "--" }}
            </span>
          </div>
          <span v-else class="cleared-table__na">--</span>
        </template>
      </el-table-column>

      <el-table-column
        prop="avg_holding_days"
        label="持有天数"
        width="88"
        align="right"
        sortable="custom"
      >
        <template #default="{ row }">
          {{ fmtHoldingDays(row.avg_holding_days) }}
        </template>
      </el-table-column>

      <!-- 清仓后（#2773）：回答「这笔卖得对不对」。算不出时给 -- + title 说明原因，
           绝不回 0——0 的含义是「卖掉之后不涨不跌」 -->
      <el-table-column
        prop="post_clear_pct"
        label="清仓后"
        width="96"
        align="right"
        sortable="custom"
      >
        <template #default="{ row }">
          <ClearedPostClearCell :cycle="asCycle(row)" />
        </template>
      </el-table-column>
    </el-table>

    <div class="cleared-table__footer">
      <span class="cleared-table__total">共 {{ total }} 个周期</span>
      <el-pagination
        v-model:current-page="page"
        v-model:page-size="pageSize"
        :page-sizes="PAGE_SIZES"
        :total="total"
        layout="sizes, prev, pager, next"
        size="small"
        background
        @size-change="onSizeChange"
      />
    </div>
  </CardBlock>
</template>

<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { useRouter } from "vue-router";
import { ElMessage } from "element-plus";
import CardBlock from "@/components/CardBlock/index.vue";
import MoneyDisplay from "@/components/MoneyDisplay/index.vue";
import RiseFallText from "@/components/RiseFallText/index.vue";
import { resolveDetailPath } from "@/utils/productDetailNav";
import type { ClearedCycle } from "@/api/summary";
import { fmtHoldingDays } from "./helpers";
import ClearedPostClearCell from "./ClearedPostClearCell.vue";
import {
  DEFAULT_PAGE_SIZE,
  DEFAULT_SORT_KEY,
  DEFAULT_SORT_ORDER,
  PAGE_SIZES,
  paginate,
  sortCycles,
  type ClearedSortKey,
  type ClearedSortOrder
} from "./clearedCyclesTable";

defineOptions({ name: "ClearedCyclesTable" });

const props = defineProps<{
  rows: ClearedCycle[];
}>();

const router = useRouter();

const sortKey = ref<ClearedSortKey>(DEFAULT_SORT_KEY);
const sortOrder = ref<ClearedSortOrder>(DEFAULT_SORT_ORDER);
const page = ref(1);
const pageSize = ref<number>(DEFAULT_PAGE_SIZE);

const sorted = computed(() =>
  sortCycles(props.rows, sortKey.value, sortOrder.value)
);

const paged = computed(() =>
  paginate(sorted.value, page.value, pageSize.value)
);
const pageRows = computed(() => paged.value.rows);
const total = computed(() => paged.value.total);

/** 切时间范围后行数变少：页码夹回有效区间，不留一张「第 9 页 / 共 3 页」的空表 */
watch(
  () => [props.rows, pageSize.value] as const,
  () => {
    page.value = paged.value.current;
    if (props.rows.length === 0) page.value = 1;
  }
);

/**
 * el-table 的三态排序（升 → 降 → 清空）。清空时退回默认序而不是「保持原样」：
 * 保持原样会让表头箭头消失、行序却是上次的排序，看起来像没生效。
 */
const onSortChange = (payload: {
  prop: string | null;
  order: "ascending" | "descending" | null;
}) => {
  if (!payload.prop || !payload.order) {
    sortKey.value = DEFAULT_SORT_KEY;
    sortOrder.value = DEFAULT_SORT_ORDER;
    page.value = 1;
    return;
  }
  sortKey.value = payload.prop as ClearedSortKey;
  sortOrder.value = payload.order === "ascending" ? "asc" : "desc";
  page.value = 1;
};

const onSizeChange = () => {
  page.value = 1;
};

/**
 * 详情页跳转：品类由后端 resolve 判定（`resolveDetailPath` 的唯一出口）。
 * 未识别 / 品类未开放都要说清楚，不能点了没反应——那比不给点更糟。
 */
const openingSymbol = ref<string | null>(null);
const openProduct = async (row: ClearedCycle) => {
  if (openingSymbol.value) return;
  openingSymbol.value = row.symbol || null;
  try {
    const path = await resolveDetailPath({ symbol: row.symbol || "" });
    if (!path) {
      ElMessage.info("该品类暂未开放详情页");
      return;
    }
    await router.push(path);
  } catch {
    ElMessage.warning("未识别这个产品，暂时打不开详情");
  } finally {
    openingSymbol.value = null;
  }
};

/**
 * el-table 的插槽 `row` 只被标注成 `DefaultRow`（`Record<string, any>`），
 * 传给类型化子组件时 tsc 会报「缺 15 个属性」。显式断言，而不是把子组件 props
 * 放宽成 any —— 放宽等于放弃「字段名写错能报错」。
 */
const asCycle = (row: unknown) => row as ClearedCycle;

/** 账户列的悬浮全文：多账户时列里只显示首个 + 数量，全名在这里给 */
const ledgerTitle = (row: unknown) =>
  (asCycle(row).ledger_names || []).join("、");
</script>

<style scoped lang="scss">
.cleared-table__product {
  display: flex;
  flex-direction: column;
  gap: 0;
  min-width: 0;
}

.cleared-table__name {
  height: auto;
  padding: 0;
  font-size: var(--el-font-size-base);
  font-weight: 500;
  color: var(--text-primary);

  &:hover {
    color: var(--brand-ink);
    text-decoration: underline;
  }
}

.cleared-table__code {
  font-family: var(--font-mono);
  font-size: var(--text-label);
  color: var(--text-tertiary-ink);
}

.cleared-table__na {
  color: var(--text-tertiary-ink);
}

/* 账户列：首个名字可以省略（账户名长度无上限），"+N" 必须完整显示 */
.cleared-table__ledger {
  display: inline-flex;
  gap: 4px;
  align-items: baseline;
  max-width: 100%;
  font-size: var(--el-font-size-small);
  color: var(--text-secondary);
}

.cleared-table__ledger-name {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.cleared-table__ledger-more {
  flex: none;
  font-size: var(--text-label);
  color: var(--text-tertiary-ink);
}

/* 持有区间：起止分两行，日期定宽（tabular-nums）才上下对齐、能竖着扫 */
.cleared-table__range {
  display: flex;
  flex-direction: column;
  font-size: var(--text-label);
  font-variant-numeric: tabular-nums;
  line-height: 1.45;
  color: var(--text-secondary);
}

.cleared-table__range-end {
  color: var(--text-tertiary-ink);
}

.cleared-table__footer {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-compact);
  align-items: center;
  justify-content: space-between;
  margin-top: var(--space-3);
}

.cleared-table__total {
  font-size: var(--el-font-size-small);
  color: var(--text-tertiary-ink);
}
</style>
