<script setup lang="ts">
import { computed, ref } from "vue";
import type {
  AdvisorComparisonFund,
  AdvisorComparisonResult
} from "@/api/funds";
import { productRoute } from "@/utils/productIdentity";

/**
 * 投顾组合 · 三集合清单与「组合外持仓」（§05 下半：具体差哪几只）。
 *
 * ## 与方向对照分开的理由
 *
 * 两者口径不同、失效也不互相关联：方向答「结构差在哪」（依赖风格箱），
 * 三集合答「具体差哪几只」（依赖基金代码级重合）。风格箱取不到时方向块整块降级，
 * 而这份清单照常展示——合在一个组件里会让降级边界变模糊。
 *
 * ## 为什么每个集合都要带比例
 *
 * 「我持有 · 组合里没有」在真实账户里有 109 只，**数量本身不说明问题**。
 * 用户的原话是「最主要的是需要有一个比例或者方向上的对比」，故每个集合都补
 * 「占我权益市值多少」；分母缺失时留空而不是写 0.00%（那会被读成「一分没有」）。
 */
const props = defineProps<{
  comparison: AdvisorComparisonResult | null;
}>();

const outsideOpen = ref(false);

const mineTotalCents = computed(
  () => props.comparison?.mine.total_market_value_cents ?? 0
);

const common = computed(() => props.comparison?.overlap.common ?? []);
const advisorOnly = computed(
  () => props.comparison?.overlap.advisor_only ?? []
);
const mineOnly = computed(() => props.comparison?.overlap.mine_only ?? []);

function sharePct(items: AdvisorComparisonFund[]): number | null {
  if (!mineTotalCents.value) return null;
  const cents = items.reduce(
    (sum, item) => sum + (item.my_market_value_cents ?? 0),
    0
  );
  return (cents / mineTotalCents.value) * 100;
}

interface Chip {
  label: string;
  count: string;
  extra: string;
}

const chips = computed<Chip[]>(() => {
  const list: Chip[] = [];
  const commonPct = sharePct(common.value);
  const outsidePct = sharePct(mineOnly.value);
  if (common.value.length) {
    list.push({
      label: "组合里有 · 我也持有",
      count: `${common.value.length} 只`,
      extra: commonPct != null ? `${commonPct.toFixed(2)}% 我的市值` : ""
    });
  }
  if (advisorOnly.value.length) {
    list.push({
      label: "组合里有 · 我没有",
      count: `${advisorOnly.value.length} 只`,
      extra: ""
    });
  }
  if (mineOnly.value.length) {
    list.push({
      label: "我持有 · 组合里没有",
      count: `${mineOnly.value.length} 只`,
      extra: outsidePct != null ? `${outsidePct.toFixed(2)}% 我的市值` : ""
    });
  }
  return list;
});

function nameOf(item: AdvisorComparisonFund): string {
  return item.fund_name || item.fund_code;
}

function weightOf(item: AdvisorComparisonFund): string {
  return item.my_market_value_cents != null && mineTotalCents.value > 0
    ? `${((item.my_market_value_cents / mineTotalCents.value) * 100).toFixed(2)}%`
    : "—";
}
</script>

<template>
  <div v-if="chips.length" class="chips">
    <span v-for="chip in chips" :key="chip.label" class="chip">
      {{ chip.label }}
      <b>{{ chip.count }}</b>
      <template v-if="chip.extra"> · {{ chip.extra }}</template>
    </span>
  </div>

  <template v-if="mineOnly.length">
    <button
      type="button"
      class="link-more"
      :aria-expanded="outsideOpen"
      @click="outsideOpen = !outsideOpen"
    >
      {{
        outsideOpen
          ? "收起组合外持仓"
          : `展开组合外持仓（${mineOnly.length} 只）`
      }}
      <span class="link-more__chev" aria-hidden="true">›</span>
    </button>

    <ul v-if="outsideOpen" class="outside">
      <li v-for="item in mineOnly" :key="item.fund_code">
        <RouterLink
          :to="productRoute({ assetType: 'fund', symbol: item.fund_code })"
          class="outside__name"
          :title="nameOf(item)"
        >
          {{ nameOf(item) }}
        </RouterLink>
        <b class="outside__weight">{{ weightOf(item) }}</b>
      </li>
    </ul>
  </template>
</template>

<style scoped lang="scss">
@use "@/style/breakpoints" as bp;
@use "./link-more";

.chips {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2);
  margin-top: var(--space-4);

  /* 窄屏逐条堆叠：三集合的三句话本来就长，挤成两列会让「10 只」和
     「0.08% 我的市值」分别落在两行，读起来像两件事 */
  @include bp.below("md") {
    flex-direction: column;
    align-items: flex-start;
  }
}

.chip {
  display: inline-flex;
  flex-wrap: wrap;
  gap: 6px;
  align-items: baseline;
  padding: 4px 12px;
  font-size: var(--text-label);
  color: var(--text-secondary);
  background: var(--bg-soft);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-pill);
}

/* 「10 只」是数量 + 单位，被拆成两行就成了两个孤立字符 */
.chip b {
  font-family: var(--font-number);
  font-size: var(--text-label);
  font-weight: 600;
  color: var(--text-primary);
  white-space: nowrap;
}

/* 组合外持仓：两栏 + 限高滚动。109 只不加限高会把这一块拉到两屏 */
.outside {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 0 var(--space-5);
  max-height: 320px;
  padding: 0 var(--space-1) 0 0;
  margin: var(--space-3) 0 0;
  overflow-y: auto;
  list-style: none;

  @include bp.below("md") {
    grid-template-columns: minmax(0, 1fr);
  }

  li {
    display: flex;
    gap: var(--space-3);
    align-items: baseline;
    justify-content: space-between;
    padding: 7px 0;
    border-bottom: 1px solid var(--border-light);
  }
}

.outside__name {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  font-size: var(--text-label);
  color: var(--text-secondary);
  white-space: nowrap;

  &:hover {
    text-decoration: underline;
  }
}

.outside__weight {
  flex: 0 0 auto;
  font-family: var(--font-number);
  font-size: var(--text-label);
  font-weight: 600;
  color: var(--text-primary);
}
</style>
