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

    <!-- 心理账户（与财务晴雨表同宽右栏 4 列，外层已统一白底卡片容器） -->
    <div class="lg:col-span-4 flex flex-col gap-3 h-full">
      <SectionHeader title="心理账户" />
      <CardBlock class="flex-1 h-full flex flex-col card-hover card-enter">
        <div class="flex flex-col gap-4 flex-1 justify-between">
          <!-- TODO: 心理账户数据应接入 API，当前为静态示例 -->
          <div
            v-for="account in mentalAccounts"
            :key="account.name"
            class="mental-account-item p-3 rounded-xl cursor-pointer group"
            :style="{ border: '1px solid var(--border-light)' }"
          >
            <div class="flex justify-between items-center mb-1">
              <span
                class="text-xs font-bold"
                :style="{ color: 'var(--text-primary)' }"
                >{{ account.name }}</span
              >
              <span
                class="text-[10px] font-bold"
                :style="{ color: account.color }"
                >{{ account.percent }}%</span
              >
            </div>
            <div
              class="w-full h-1.5 rounded-full overflow-hidden"
              :style="{ backgroundColor: 'var(--bg-soft)' }"
            >
              <div
                class="h-full rounded-full transition-all"
                :style="{
                  backgroundColor: account.color,
                  width: account.percent + '%'
                }"
              />
            </div>
            <MoneyDisplay
              :value="account.amount"
              size="xs"
              :show-sign="false"
              :show-currency="true"
            />
          </div>
        </div>
      </CardBlock>
    </div>
  </div>
</template>

<script setup lang="ts">
import MoneyDisplay from "@/components/MoneyDisplay/index.vue";
import SectionHeader from "@/components/SectionHeader/index.vue";
import CardBlock from "@/components/CardBlock/index.vue";
import type {
  HomeFeedItem,
  MentalAccountItem
} from "../composables/useWelcomeData";

defineOptions({ name: "WelcomeFinanceFeed" });

defineProps<{
  homeFeed: HomeFeedItem[];
  mentalAccounts: MentalAccountItem[];
}>();
</script>
