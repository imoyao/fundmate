<template>
  <!-- ===== 第四排：财务晴雨表 + 心理账户（统一 12 列栅格 + 等宽右栏） ===== -->
  <div class="grid grid-cols-1 lg:grid-cols-12 gap-8 mb-8">
    <!-- 财务晴雨表：尚未接入测算，空态占位（不展示编造百分比） -->
    <div class="lg:col-span-8 flex flex-col gap-3">
      <SectionHeader
        title="财务晴雨表"
        info="基于你的资产负债表与现金流测算的四项关键财务健康度指标"
      />
      <CardBlock
        class="flex-1 flex flex-col items-center justify-center text-center gap-2 min-h-[120px]"
      >
        <span
          class="text-sm font-medium"
          :style="{ color: 'var(--text-secondary)' }"
          >财务晴雨表 · 即将上线</span
        >
        <span
          class="text-[11px] max-w-xs"
          :style="{ color: 'var(--text-tertiary-ink)' }"
        >
          接入资产负债表与现金流测算后，在此展示资产负债率、预估储蓄率、财务自由度等指标。
        </span>
      </CardBlock>
      <!-- 近期动态：真实数据派生的事件 feed（后端事件日志就绪后可替换为事件流） -->
      <CardBlock class="flex-1 card-hover">
        <div class="flex justify-between items-center mb-4">
          <span
            class="font-bold text-sm"
            :style="{ color: 'var(--text-secondary)' }"
            >近期动态</span
          >
        </div>
        <div v-if="homeFeed.length" class="space-y-3">
          <div
            v-for="item in homeFeed"
            :key="item.key"
            class="flex items-center gap-2.5"
          >
            <span
              class="shrink-0 w-1.5 h-1.5 rounded-full"
              :style="{ backgroundColor: item.color }"
            />
            <span
              class="text-xs leading-5"
              :style="{ color: 'var(--text-secondary)' }"
              >{{ item.text }}</span
            >
          </div>
        </div>
        <div
          v-else
          class="flex items-center justify-center py-6 text-xs"
          :style="{ color: 'var(--text-tertiary-ink)' }"
        >
          数据加载中…
        </div>
      </CardBlock>
    </div>

    <!-- 心理账户（与财务晴雨表同宽右栏 4 列，外层已统一白底卡片容器）
         数据源：`/api/summary/distributions/` 的 allocation_scope（#3115 D4）。
         此前是四条写死的假数（¥120,000 / ¥300,000 / ¥520,000 / ¥45,000）——
         那不是空态，是四个编造的数字，用户会当成自己的钱读。 -->
    <div class="lg:col-span-4 flex flex-col gap-3 h-full">
      <SectionHeader title="心理账户" :info="SCOPE_INFO" />
      <CardBlock class="flex-1 h-full flex flex-col card-hover card-enter">
        <!-- 加载：骨架行，不显示任何数字（宁可空着，也不摆占位金额） -->
        <div v-if="loading" class="flex flex-col gap-3" aria-busy="true">
          <div
            v-for="n in 5"
            :key="n"
            class="h-4 rounded animate-pulse"
            :style="{ backgroundColor: 'var(--bg-soft)' }"
          />
        </div>

        <!-- 失败：明说失败并可重试，不回落成假数 -->
        <div
          v-else-if="error"
          class="flex flex-1 flex-col items-center justify-center gap-2 text-center"
        >
          <span class="text-sm" :style="{ color: 'var(--text-secondary)' }"
            >五笔钱分布加载失败</span
          >
          <button
            type="button"
            class="text-xs underline bg-transparent border-0 cursor-pointer"
            :style="{ color: 'var(--brand-ink)' }"
            @click="emit('retry')"
          >
            重试
          </button>
        </div>

        <!-- 空：真的没有可投资资产（分母为 0），说清楚「什么钱才算进来」 -->
        <div
          v-else-if="!view || view.denominator <= 0"
          class="flex flex-1 flex-col items-center justify-center gap-2 text-center"
        >
          <span
            class="text-sm font-medium"
            :style="{ color: 'var(--text-secondary)' }"
            >还没有可投资的资产</span
          >
          <span
            class="text-[11px] max-w-[15rem] leading-5"
            :style="{ color: 'var(--text-tertiary-ink)' }"
          >
            五笔钱只算持仓与账户现金；房产、应收、负债不计入。记了第一笔就会出现。
          </span>
        </div>

        <!-- 数据：一条占比条 + 五档图例（空档保留，弱化但不隐藏） -->
        <div v-else class="flex flex-1 flex-col justify-between gap-4">
          <div>
            <div class="mental-account__bar" aria-hidden="true">
              <span
                v-for="item in nonEmptyItems"
                :key="item.key"
                class="mental-account__seg"
                :style="{
                  flexGrow: item.amount,
                  backgroundColor: item.color
                }"
              />
            </div>
            <ul class="mental-account__legend">
              <li
                v-for="item in view.items"
                :key="item.key"
                class="mental-account__row"
                :class="{ 'is-empty': item.empty }"
              >
                <span
                  class="mental-account__dot"
                  :style="{ backgroundColor: item.color }"
                  aria-hidden="true"
                />
                <span class="mental-account__name">{{ item.name }}</span>
                <MoneyDisplay
                  :value="item.amount"
                  size="xs"
                  :show-sign="false"
                  :show-currency="true"
                />
                <span class="mental-account__pct">{{ item.percentText }}</span>
              </li>
            </ul>
          </div>

          <div class="flex flex-col gap-2">
            <p class="mental-account__foot">{{ scopeFootnote(view) }}</p>
            <p v-if="view.liquidHint" class="mental-account__hint">
              {{ view.liquidHint }}
              <RouterLink class="mental-account__link" to="/asset/ledgers"
                >去账户页录入</RouterLink
              >
            </p>
          </div>
        </div>
      </CardBlock>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from "vue";
import MoneyDisplay from "@/components/MoneyDisplay/index.vue";
import SectionHeader from "@/components/SectionHeader/index.vue";
import CardBlock from "@/components/CardBlock/index.vue";
import type { HomeFeedItem } from "../composables/useWelcomeData";
import {
  scopeFootnote,
  type MentalAccountView
} from "../composables/mentalAccounts";

defineOptions({ name: "WelcomeFinanceFeed" });

const props = defineProps<{
  homeFeed: HomeFeedItem[];
  /** null = 还没有响应（加载中或失败），由 loading / error 区分 */
  mentalAccountView: MentalAccountView | null;
  loading?: boolean;
  error?: boolean;
}>();

const emit = defineEmits<{ retry: [] }>();

const view = computed(() => props.mentalAccountView);

/** 占比条只画有金额的档位——0 值段没有宽度，留在 DOM 里只是噪音 */
const nonEmptyItems = computed(() =>
  (view.value?.items ?? []).filter(item => !item.empty)
);

/**
 * 口径说明（走 SectionHeader 的 info 气泡）。
 * 三句都说清：分母是什么、谁被排除、负债为什么不在里面。
 */
const SCOPE_INFO =
  "五笔钱只统计可投资的资产端：持仓市值 + 账户里录过的现金类资产。" +
  "房产、应收款这类不变现的钱算「未纳入」，负债单独列示、不参与占比。" +
  "所以这里的合计会小于家庭总资产，差额在卡片底部逐项写明。";
</script>

<style lang="scss" scoped>
.mental-account__bar {
  display: flex;
  gap: 2px;
  width: 100%;
  height: 8px;
  margin-bottom: 14px;
  overflow: hidden;
  background-color: var(--bg-soft);
  border-radius: 999px;
}

.mental-account__seg {
  min-width: 2px;
  transition: flex-grow 0.3s ease;
}

.mental-account__legend {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 0;
  margin: 0;
  list-style: none;
}

.mental-account__row {
  /* 末列用 max-content：全角「＜0.1%」比「100%」宽得多，写死 38px 会把它折成两行
     （多档场景实测）。由该列最长内容定宽，既能容纳极小占比，又保持右对齐。 */
  display: grid;
  grid-template-columns: 8px minmax(0, 1fr) auto max-content;
  gap: 8px;
  align-items: center;
  font-size: var(--text-label);
  color: var(--text-secondary);
}

/* 空档：弱化到「还在、但是 0」，不是隐藏——「保命钱为 0」本身就是结论 */
.mental-account__row.is-empty {
  color: var(--text-tertiary-ink);
}

.mental-account__row.is-empty .mental-account__dot {
  opacity: 0.35;
}

.mental-account__dot {
  width: 8px;
  height: 8px;
  border-radius: 999px;
}

.mental-account__name {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.mental-account__pct {
  font-size: var(--text-label);
  font-variant-numeric: tabular-nums;
  text-align: right;
  white-space: nowrap;
  opacity: 0.85;
}

.mental-account__foot {
  font-size: var(--text-label);
  line-height: 1.5;
  color: var(--text-tertiary-ink);
}

.mental-account__hint {
  padding: 8px 10px;
  font-size: var(--text-label);
  line-height: 1.5;
  color: var(--text-secondary);
  background-color: var(--bg-subtle);
  border-radius: 10px;
}

.mental-account__link {
  margin-left: 4px;
  color: var(--brand-ink);
  text-decoration: underline;
}
</style>
