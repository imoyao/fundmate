<script setup lang="ts">
import { computed, ref, watch } from "vue";
import CardBlock from "@/components/CardBlock/index.vue";
import MoneyDisplay from "@/components/MoneyDisplay/index.vue";
import RiseFallText from "@/components/RiseFallText/index.vue";
import SectionHeader from "@/components/SectionHeader/index.vue";
import { getPositions } from "@/api/positions";
import { getSymbolXirr } from "@/api/performance";
import type { Position } from "@/api/types";
import { formatQuantity } from "@/utils/format";

/**
 * 详情页「我的持仓」区块（#1966 · 设计 §4.2；持有年化由 #1972 补齐）。
 *
 * 数据来自 `GET /api/positions/?symbol=&market=`，过滤在**后端下推到 SQL**
 * （本卡同期新增的过滤参数），不在前端拉全量再筛——后者是数据策略硬约束 §6 明令禁止的。
 *
 * 口径：
 * - 按渠道（账户）分块；`ledger_id` 为空的是**未归档持仓**，单列一组，不并进任何账户；
 * - 盈亏率 = 盈亏 ÷ 持仓成本（成本单价 × 持有数量），与持仓列表页同一口径；
 * - 持有年化 = 跨账户按 symbol 汇总现金流的 XIRR（`scope=symbol`，#1972），与上面的
 *   持仓行**同一套 symbol 归一口径**（后端 `services/symbol_scope.py` 收口），
 *   所以「列表有几行、年化就算几个账户」不会打架；
 * - 涨跌颜色交给 `RiseFallText`（涨红跌绿语义变量），此处不自己拼颜色。
 */

const props = defineProps<{
  symbol: string;
  /** 市场消歧：同码跨市场时由详情页 resolve 结果带下来 */
  market?: string;
}>();

const loading = ref(false);
const rows = ref<Position[]>([]);
/** 产品级持有年化（XIRR，小数）；`null` = 无数据 / 拉取失败，模板显示 `—` */
const xirr = ref<number | null>(null);

interface ChannelGroup {
  key: string;
  label: string;
  items: Position[];
}

/** 按渠道分组；未归档持仓单列，不假装属于某个账户 */
const grouped = computed<ChannelGroup[]>(() => {
  const map = new Map<string, ChannelGroup>();
  for (const p of rows.value) {
    const key = p.ledger_id != null ? `ledger-${p.ledger_id}` : "unarchived";
    const group = map.get(key) ?? {
      key,
      label: p.account_name || "未归档持仓",
      items: []
    };
    group.items.push(p);
    map.set(key, group);
  }
  return [...map.values()];
});

function costOf(p: Position): number {
  return (p.avg_price ?? 0) * (p.quantity ?? 0);
}

function pnlRatio(p: Position): number {
  const cost = costOf(p);
  return cost ? (p.pnl ?? 0) / cost : 0;
}

const totalCost = computed(() =>
  rows.value.reduce((sum, p) => sum + costOf(p), 0)
);
const totalPnl = computed(() =>
  rows.value.reduce((sum, p) => sum + (p.pnl ?? 0), 0)
);
const totalMarketValue = computed(() =>
  rows.value.reduce((sum, p) => sum + (p.market_value ?? 0), 0)
);
const totalPnlRatio = computed(() =>
  totalCost.value ? totalPnl.value / totalCost.value : 0
);

async function load() {
  if (!props.symbol) return;
  loading.value = true;
  xirr.value = null;
  try {
    const res = await getPositions({
      symbol: props.symbol,
      market: props.market,
      per_page: 100
    });
    rows.value = res.data ?? [];
  } catch {
    // 拉不到就当作「暂无持仓」，不显示错误态更不该显示假数据
    rows.value = [];
  } finally {
    loading.value = false;
  }
  // 持有年化跟着同一次刷新走；没有持仓行时不发请求（区块本身就空着）
  if (rows.value.length) void loadXirr();
}

async function loadXirr() {
  try {
    const res = await getSymbolXirr(props.symbol);
    // cashflow_count = 0 表示该产品无成交：后端给的是全 0 结构，按「无数据」显示 `—`
    const data = res.data;
    xirr.value = data && data.cashflow_count > 0 ? data.xirr : null;
  } catch {
    // 持有年化是锦上添花的指标，拉不到就降级 `—`，不惊动整块持仓列表
    xirr.value = null;
  }
}

watch(() => [props.symbol, props.market], load, { immediate: true });
</script>

<template>
  <CardBlock class="position-section">
    <SectionHeader
      title="我的持仓"
      info="按渠道（账户）分列；盈亏率 = 盈亏 ÷ 持仓成本。未归档持仓单独一组。持有年化为跨账户合并现金流后的 XIRR。"
      info-label="关于持仓口径"
    >
      <template #action>
        <p v-if="rows.length" class="position-section__xirr">
          <span class="position-section__xirr-label">持有年化</span>
          <RiseFallText
            v-if="xirr !== null"
            :value="xirr"
            size="sm"
            :precision="2"
          />
          <span v-else class="position-section__xirr-empty">—</span>
        </p>
      </template>
    </SectionHeader>

    <p v-if="loading" class="position-section__hint">正在读取持仓…</p>
    <p v-else-if="!rows.length" class="position-section__hint">
      当前产品暂无持仓记录。
    </p>

    <template v-else>
      <section
        v-for="group in grouped"
        :key="group.key"
        class="position-section__channel"
      >
        <p class="position-section__channel-name">{{ group.label }}</p>
        <div class="position-section__row position-section__row--head">
          <span>产品</span>
          <span class="position-section__num">持有</span>
          <span class="position-section__num">市值</span>
          <span class="position-section__num">盈亏率</span>
        </div>
        <div v-for="p in group.items" :key="p.id" class="position-section__row">
          <span class="position-section__label">{{ p.name || p.symbol }}</span>
          <span class="position-section__num">{{
            formatQuantity(p.quantity)
          }}</span>
          <MoneyDisplay
            class="position-section__num"
            :value="p.market_value ?? 0"
            size="sm"
            :show-sign="false"
            :auto-color="false"
          />
          <RiseFallText
            class="position-section__num"
            :value="pnlRatio(p)"
            size="sm"
            :precision="2"
          />
        </div>
      </section>

      <div class="position-section__row position-section__row--total">
        <span>合计</span>
        <span class="position-section__num" />
        <MoneyDisplay
          class="position-section__num"
          :value="totalMarketValue"
          size="sm"
          :show-sign="false"
          :auto-color="false"
        />
        <RiseFallText
          class="position-section__num"
          :value="totalPnlRatio"
          size="sm"
          :precision="2"
        />
      </div>
    </template>
  </CardBlock>
</template>

<style scoped>
.position-section {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}

.position-section__hint {
  margin: 0;
  font-size: 13px;
  color: var(--text-tertiary-ink);
}

.position-section__channel {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}

.position-section__channel-name {
  margin: 0;
  font-size: 13px;
  color: var(--text-secondary);
}

.position-section__row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto auto auto;
  gap: var(--space-3);
  align-items: center;
  padding: var(--space-2) 0;
  border-bottom: 1px solid var(--border-light);
}

.position-section__row--head {
  font-size: 12px;
  color: var(--text-tertiary-ink);
}

.position-section__row--total {
  font-weight: 600;
  border-top: 1px solid var(--border-light);
  border-bottom: none;
}

.position-section__label {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.position-section__num {
  font-variant-numeric: tabular-nums;
  text-align: right;
}

/* 产品级持有年化（#1972）：挂在区块标题右侧，不占表格列 */
.position-section__xirr {
  display: flex;
  gap: var(--space-2);
  align-items: baseline;
  margin: 0;
  font-variant-numeric: tabular-nums;
}

.position-section__xirr-label {
  font-size: 12px;
  color: var(--text-tertiary-ink);
}

.position-section__xirr-empty {
  color: var(--text-tertiary-ink);
}
</style>
