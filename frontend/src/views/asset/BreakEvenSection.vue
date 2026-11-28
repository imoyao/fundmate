<!--
  浮亏回本（2026-11-27）—— 复盘页的「现在」视角，补第 6 条「回本涨幅」

  为什么单开一块：本页原有三块都是**已实现 / 时间维度**（收益概览、净值走势、
  清仓复盘），而「现在还亏着的，要涨多少才回本」是点位事实，没有任何一块回答它。
  收益率也不回答：−20% 要涨 25%、−50% 要涨 100%，亏损与回本不对称。

  数据源：`/api/positions/`（分页接口）。**不用** `group_by=account`：那条路径不产出
  `pnl` / `market_value`（实测 166 条全为 null，只有 `avg_price` / `current_price`），
  而本块两个数都依赖它们。用 `pnl` 与 `market_value` 现算回本需涨（口径与边界见
  `./breakEven.ts` 文件头），**不新增端点**。

  与清仓区块的关系：清仓区块的 `unrealized_count` 只给「有几个浮亏标的」，
  本块给「这些标的加起来还要涨多少」以及「最该先处理的几个」。
  两块不是同一份数据的第二次展示：一个是计数，一个是金额与幅度。

  无浮亏持仓时整块不渲染（`v-if="rows.length"`）—— 空表比隐藏更吓人，
  而「没有浮亏」本身就是一条让人放心的信息，由清仓区块的「另有 0 只浮亏」承担。
-->
<template>
  <section v-if="rows.length" id="nav-break-even">
    <SectionHeader
      title="浮亏回本"
      info="回本需涨 = 浮亏 ÷ 当前市值，只统计当前浮亏的持仓；盈利标的计入会把「要涨多少」稀释。整体值按合计浮亏 ÷ 合计市值加权，不是各标的百分比的简单平均。"
    />
    <CardBlock>
      <MetricGrid>
        <MetricCard
          title="浮亏标的"
          :value="summary.lossCount"
          unit="个"
          :caption="countCaption"
        />
        <MetricCard
          title="合计浮亏"
          :value="totalLossLabel"
          value-color="var(--color-fall)"
          :caption="`占持仓市值 ${marketValueShare}`"
        />
        <!-- 「回本需涨」不是涨跌，不套涨跌色：红（涨色）会被读成「赚了」，
             绿（跌色）更错。用默认文字色 + featured 大小来强调它是核心结论。 -->
        <MetricCard
          title="整体回本需涨"
          :value="summary.overallGainPct"
          unit="%"
          :caption="overallCaption"
          featured
        />
      </MetricGrid>

      <ul class="break-even__list">
        <li v-for="row in visibleRows" :key="row.key" class="break-even__row">
          <div class="break-even__identity">
            <span class="break-even__name" :title="row.name">{{
              row.name
            }}</span>
            <span class="break-even__sub"># {{ row.symbol }}</span>
          </div>
          <MoneyDisplay
            class="break-even__pnl"
            :value="row.pnl"
            show-sign
            auto-color
            size="sm"
          />
          <span class="break-even__gain">
            回本需涨
            <strong>{{ row.gainPct?.toFixed(2) }}%</strong>
          </span>
        </li>
      </ul>

      <button
        v-if="rows.length > PREVIEW_SIZE"
        type="button"
        class="break-even__more"
        :aria-expanded="expanded"
        @click="expanded = !expanded"
      >
        {{
          expanded
            ? "收起"
            : `展开全部 ${rows.length} 个浮亏持仓（按浮亏额降序）`
        }}
      </button>
    </CardBlock>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import SectionHeader from "@/components/SectionHeader/index.vue";
import CardBlock from "@/components/CardBlock/index.vue";
import MetricGrid from "@/components/MetricGrid/index.vue";
import MetricCard from "@/components/MetricCard/index.vue";
import MoneyDisplay from "@/components/MoneyDisplay/index.vue";
import { getPositions } from "@/api/positions";
import type { Position } from "@/api/types";
import { formatAmount } from "@/utils/currency";
import { buildBreakEven } from "./breakEven";

/** 账户 / 组合级口径（2026-11-28，复盘页口径切换器）：都不传 = 家庭级 */
const props = defineProps<{
  ledgerId?: number;
  portfolioId?: number;
}>();

/** 列表首屏行数：够看出「最该先处理的是哪几个」，又不把区块顶成一屏半 */
const PREVIEW_SIZE = 6;

const positions = ref<Position[]>([]);
const expanded = ref(false);

/** 一次算完（rows + summary 共用一趟遍历，不各算一遍） */
const model = computed(() => buildBreakEven(positions.value));
const rows = computed(() => model.value.rows);
const summary = computed(() => model.value.summary);
const visibleRows = computed(() =>
  expanded.value ? rows.value : rows.value.slice(0, PREVIEW_SIZE)
);

const totalLossLabel = computed(
  () => `¥${formatAmount(summary.value.totalLoss, 2)}`
);
const countCaption = computed(() => `共 ${positions.value.length} 个持仓`);
/** 浮亏市值占全仓市值的比例：告诉用户「这块坑占我多大盘子」 */
const marketValueShare = computed(() => {
  const total = positions.value.reduce(
    (sum, p) => sum + (typeof p.market_value === "number" ? p.market_value : 0),
    0
  );
  if (total <= 0) return "--";
  const share = (summary.value.totalMarketValue / total) * 100;
  return `${share.toFixed(1)}%`;
});
const overallCaption = computed(() =>
  summary.value.totalMarketValue > 0
    ? `这些标的市值 ¥${formatAmount(summary.value.totalMarketValue, 0)}`
    : ""
);

/**
 * 一次拿全量持仓：先取一页 500 条，`total` 更大就继续取（当前实测 166 条，一页够，
 * 但不写死「肯定装得下」——持仓数会随使用增长，静默截断会让汇总数字悄悄变小）。
 * 空页即停，避免后端 `total` 与实际不一致时死循环。
 *
 * 失败时保持空数组 ⇒ 整块不渲染。失败不显示「¥0」——那会被读成「没有浮亏」，
 * 比不显示更糟。
 */
const PAGE_SIZE = 500;
const load = async () => {
  try {
    const first = await getPositions({
      page: 1,
      per_page: PAGE_SIZE,
      ledger_id: props.ledgerId,
      portfolio_id: props.portfolioId
    });
    let all = first?.data ?? [];
    const total = first?.total ?? all.length;
    for (let page = 2; all.length < total; page += 1) {
      const next = await getPositions({
        page,
        per_page: PAGE_SIZE,
        ledger_id: props.ledgerId,
        portfolio_id: props.portfolioId
      });
      const rows = next?.data ?? [];
      if (rows.length === 0) break;
      all = all.concat(rows);
    }
    positions.value = all;
  } catch {
    positions.value = [];
  }
};

onMounted(load);

// 切档：清空再取（失败时的空数组同理——留着旧口径的浮亏列表等于报错数）
watch(
  () => [props.ledgerId, props.portfolioId],
  () => {
    positions.value = [];
    expanded.value = false;
    void load();
  }
);

/** 父页「刷新数据」：真刷新，不摆样子 */
defineExpose({ refresh: load });
</script>

<style scoped lang="scss">
.break-even__list {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 0;
  margin: var(--space-4) 0 0;
  list-style: none;
}

.break-even__row {
  display: grid;
  grid-template-columns: minmax(0, 2fr) minmax(96px, 1fr) minmax(120px, 1fr);
  gap: var(--space-3);
  align-items: center;
}

.break-even__identity {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}

.break-even__name {
  overflow: hidden;
  text-overflow: ellipsis;
  font-size: var(--text-label);
  color: var(--text-primary);
  white-space: nowrap;
}

.break-even__sub {
  overflow: hidden;
  text-overflow: ellipsis;
  font-size: var(--text-label);
  color: var(--text-tertiary-ink);
  white-space: nowrap;
}

.break-even__pnl {
  justify-self: end;
}

.break-even__gain {
  font-size: var(--text-label);
  color: var(--text-secondary);
  text-align: right;

  strong {
    font-variant-numeric: tabular-nums;
    color: var(--text-primary);
  }
}

.break-even__more {
  display: block;
  margin-top: var(--space-3);
  font-size: var(--text-label);
  color: var(--brand-ink);
  cursor: pointer;
  background: none;
  border: 0;
}
</style>
