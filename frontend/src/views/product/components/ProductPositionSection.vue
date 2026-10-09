<script setup lang="ts">
import { computed, ref, watch } from "vue";
import CardBlock from "@/components/CardBlock/index.vue";
import MoneyDisplay from "@/components/MoneyDisplay/index.vue";
import RiseFallText from "@/components/RiseFallText/index.vue";
import SectionHeader from "@/components/SectionHeader/index.vue";
import { getPositions } from "@/api/positions";
import type { Position } from "@/api/types";
import { formatQuantity } from "@/utils/format";

/**
 * 详情页「我的持仓」区块（#1966 · 设计 §4.2）。
 *
 * 数据来自 `GET /api/positions/?symbol=&market=`，过滤在**后端下推到 SQL**
 * （本卡同期新增的过滤参数），不在前端拉全量再筛——后者是数据策略硬约束 §6 明令禁止的。
 *
 * 口径：
 * - 按渠道（账户）分块；`ledger_id` 为空的是**未归档持仓**，单列一组，不并进任何账户；
 * - 盈亏率 = 盈亏 ÷ 持仓成本（成本单价 × 持有数量），与持仓列表页同一口径；
 * - 涨跌颜色交给 `RiseFallText`（涨红跌绿语义变量），此处不自己拼颜色。
 */

const props = defineProps<{
  symbol: string;
  /** 市场消歧：同码跨市场时由详情页 resolve 结果带下来 */
  market?: string;
}>();

const loading = ref(false);
const rows = ref<Position[]>([]);

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
}

watch(() => [props.symbol, props.market], load, { immediate: true });
</script>

<template>
  <CardBlock class="position-section">
    <SectionHeader
      title="我的持仓"
      info="按渠道（账户）分列；盈亏率 = 盈亏 ÷ 持仓成本。未归档持仓单独一组。"
      info-label="关于持仓口径"
    />

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

      <!-- 产品级 XIRR 占位：后端只有 scope=position / portfolio，按 symbol 跨账户汇总
           属 B1 卡。此处**显示「—」而不是编一个数**（设计 G1：不用 mock / 演示数据占位）。 -->
      <p class="position-section__hint">
        持有年化 XIRR：— （待按产品跨账户汇总后展示）
      </p>
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
</style>
