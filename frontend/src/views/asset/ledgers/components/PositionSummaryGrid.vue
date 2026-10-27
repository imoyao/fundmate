<template>
  <div class="grid grid-cols-3 gap-3 mb-5">
    <div
      v-for="cell in cells"
      :key="cell.key"
      class="p-3 rounded-lg border"
      :style="{ borderColor: 'var(--border-default)' }"
    >
      <div class="text-xs" :style="{ color: 'var(--text-tertiary-ink)' }">
        {{ cell.label
        }}<span v-if="cell.labelHint" class="ml-1 opacity-60">{{
          cell.labelHint
        }}</span>
      </div>
      <div
        class="text-base font-semibold mt-1"
        :style="{ color: cell.color || 'var(--text-primary)' }"
      >
        <span
          v-if="cell.pending"
          class="text-sm font-normal"
          :style="{ color: 'var(--text-tertiary-ink)' }"
          >{{ cell.pending }}</span
        >
        <template v-else>
          <MoneyDisplay
            v-if="cell.money != null"
            :value="cell.money"
            :precision="cell.precision"
            :show-sign="cell.showSign"
            :auto-color="cell.autoColor"
            size="md"
          />
          <span v-else>{{ cell.text }}</span>
          <span
            v-if="cell.unit"
            class="text-sm font-normal"
            :style="{ color: 'var(--text-tertiary-ink)' }"
          >
            {{ cell.unit }}
          </span>
        </template>
      </div>
      <div
        v-if="cell.hint"
        class="text-[11px] mt-0.5"
        :style="{ color: 'var(--text-tertiary-ink)' }"
      >
        {{ cell.hint }}
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from "vue";
import MoneyDisplay from "@/components/MoneyDisplay/index.vue";
import { buildSummaryCells, type PositionLike } from "./positionSummaryModel";

/**
 * 持仓抽屉的核心摘要卡（#980 拆分自 `PositionTransactionsDrawer.vue`）。
 *
 * 8 张卡片改由 `buildSummaryCells` 产出数据、模板统一渲染：
 * 标签（持有份额 / 持有数量）、单位（份 / 股/张）、精度（基金 4 位 / 股票 2 位）、
 * 涨跌色三条规则都收在模型层，模板不再逐个手写。
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

const cells = computed(() =>
  buildSummaryCells(props.positionData, props.xirr ?? null, props.loadingXirr)
);
</script>
