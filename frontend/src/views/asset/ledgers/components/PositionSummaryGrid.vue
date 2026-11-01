<template>
  <dl class="pd-facts">
    <div v-for="fact in facts" :key="fact.key" class="pd-fact">
      <dt class="pd-fact__label">{{ fact.label }}</dt>
      <dd
        class="pd-fact__value"
        :style="fact.color ? { color: fact.color } : undefined"
      >
        <span v-if="fact.pending">{{ fact.pending }}</span>
        <template v-else>
          <MoneyDisplay
            v-if="fact.money != null"
            :value="fact.money"
            :precision="fact.precision"
            :show-sign="fact.showSign"
            :auto-color="fact.autoColor"
            size="sm"
          />
          <span v-else>{{ fact.text }}</span>
          <span v-if="fact.unit" class="pd-fact__unit">{{ fact.unit }}</span>
        </template>
      </dd>
    </div>
  </dl>
</template>

<script setup lang="ts">
import { computed } from "vue";
import MoneyDisplay from "@/components/MoneyDisplay/index.vue";
import { buildFacts, type PositionLike } from "./positionSummaryModel";

/**
 * 持仓抽屉的键值网格（设计 §4：两列、单元无边框无底色，行间不画线）。
 *
 * 与旧版的差别只有「形状」：8 张描边卡 → 5 项键值，字号从三套手写 Tailwind
 * （`text-base` / `text-xs` / `text-[11px]`）收到 14/13 两档（`_pd.scss`）。
 * 文案、单位、精度、涨跌色规则仍由 `buildFacts` 单点决定。
 */
defineOptions({ name: "PositionSummaryGrid" });

const props = withDefaults(
  defineProps<{
    positionData?: PositionLike | null;
    /** 年化收益率（XIRR，小数） */
    xirr?: number | null;
    /** 年化收益率是否计算中 */
    loadingXirr?: boolean;
  }>(),
  { positionData: null, xirr: null, loadingXirr: false }
);

const facts = computed(() =>
  buildFacts(props.positionData, props.xirr ?? null, props.loadingXirr)
);
</script>
