<template>
  <!-- ===== 第一排：核心资产看板 + 收益趋势 ===== -->
  <div class="grid grid-cols-1 xl:grid-cols-12 gap-8 mb-8">
    <!-- 左侧：家庭资产看板 -->
    <div class="xl:col-span-8 flex flex-col gap-3 card-hover card-enter">
      <SectionHeader title="家庭资产看板">
        <template #action>
          <router-link
            to="/panorama"
            class="p-2 rounded-full transition-all shadow-sm hover-card-btn"
            :style="{
              backgroundColor: 'var(--bg-soft)',
              color: 'var(--text-tertiary-ink)'
            }"
            title="查看资产详情"
          >
            <IconifyIconOffline icon="ep:full-screen" class="text-lg" />
          </router-link>
        </template>
      </SectionHeader>
      <CardBlock class="flex-1">
        <!-- 失败态（#1832）：汇总请求失败时**不显示 ¥0**。
             「0」在资产语境里是结论（我确实没资产），不是「不知道」——
             过去 `summary?.total_assets_cny ?? 0` 把两者混为一谈，首屏看着像数据被清空了。 -->
        <div
          v-if="error"
          class="flex flex-col items-center justify-center gap-3 py-10"
          role="alert"
        >
          <p class="text-sm" :style="{ color: 'var(--text-secondary)' }">
            家庭总资产加载失败，请检查网络后重试
          </p>
          <el-button size="small" type="primary" @click="emit('retry')">
            重新加载
          </el-button>
        </div>

        <div
          v-else
          class="grid grid-cols-1 lg:grid-cols-12 gap-6 items-center h-full"
        >
          <div class="lg:col-span-7 flex flex-col gap-6">
            <div>
              <p
                class="text-sm mb-2"
                :style="{ color: 'var(--text-tertiary-ink)' }"
              >
                家庭总资产
              </p>
              <div class="flex items-baseline gap-2">
                <MoneyDisplay
                  :value="summary?.total_assets_cny ?? 0"
                  size="hero"
                  :show-sign="false"
                />
                <span
                  class="text-xl font-medium"
                  :style="{ color: 'var(--text-secondary)' }"
                  >元</span
                >
              </div>
            </div>
            <div class="flex gap-6">
              <div class="flex flex-col">
                <span
                  class="text-xs mb-1"
                  :style="{ color: 'var(--text-tertiary-ink)' }"
                  >总盈亏（人民币）</span
                >
                <MoneyDisplay :value="summary?.total_pnl_cny ?? 0" size="xl" />
              </div>
            </div>
            <div
              class="grid grid-cols-2 gap-4 pt-6"
              :style="{ borderTop: '1px solid var(--border-light)' }"
            >
              <div class="flex flex-col">
                <span
                  class="text-xs mb-1"
                  :style="{ color: 'var(--text-tertiary-ink)' }"
                  >本月资产增加</span
                >
                <!-- 后端暂无此口径数据，不展示编造数值 -->
                <span
                  class="text-lg font-semibold"
                  :style="{ color: 'var(--text-tertiary-ink)' }"
                  >—</span
                >
                <span
                  class="text-[10px] mt-1"
                  :style="{ color: 'var(--text-tertiary-ink)' }"
                  >即将上线</span
                >
              </div>
              <div class="flex flex-col">
                <span
                  class="text-xs mb-1"
                  :style="{ color: 'var(--text-tertiary-ink)' }"
                  >本月负债减少</span
                >
                <!-- 后端暂无此口径数据，不展示编造数值 -->
                <span
                  class="text-lg font-semibold"
                  :style="{ color: 'var(--text-tertiary-ink)' }"
                  >—</span
                >
                <span
                  class="text-[10px] mt-1"
                  :style="{ color: 'var(--text-tertiary-ink)' }"
                  >即将上线</span
                >
              </div>
            </div>
          </div>
          <div
            class="lg:col-span-5 flex flex-col items-center justify-center h-full"
            :style="{ borderLeft: '1px solid var(--border-light)' }"
          >
            <div class="w-full flex justify-between items-center mb-4">
              <span
                class="font-bold text-sm"
                :style="{ color: 'var(--text-secondary)' }"
                >资产构成分布</span
              >
            </div>
            <AssetAllocationDonut
              :data="distributionData"
              class="h-[220px]"
              :legend-font-size="10"
              :show-legend-percent="false"
            />
          </div>
        </div>
      </CardBlock>
    </div>

    <!-- 右侧：收益趋势 -->
    <div class="xl:col-span-4 flex flex-col gap-3 card-hover card-enter">
      <SectionHeader title="收益趋势" info="累计收益 / 净资产随时间走势" />
      <CardBlock
        class="flex-1 flex flex-col items-center justify-center text-center gap-2"
      >
        <span
          class="text-sm font-medium"
          :style="{ color: 'var(--text-secondary)' }"
          >收益趋势 · 即将上线</span
        >
        <span
          class="text-[11px] max-w-xs"
          :style="{ color: 'var(--text-tertiary-ink)' }"
        >
          接入收益历史后，在此展示累计收益与净资产随时间的走势，并支持月度 /
          季度切换。
        </span>
      </CardBlock>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from "vue";
import type { SummaryData } from "@/api/types";
import MoneyDisplay from "@/components/MoneyDisplay/index.vue";
import SectionHeader from "@/components/SectionHeader/index.vue";
import CardBlock from "@/components/CardBlock/index.vue";
import AssetAllocationDonut from "@/components/Charts/AssetAllocationDonut.vue";

defineOptions({ name: "WelcomeAssetBoard" });

const props = defineProps<{
  summary: SummaryData | null;
  /** 汇总请求失败（#1832）：为 true 时渲染「加载失败 + 重试」，不显示 ¥0 */
  error?: boolean;
}>();

const emit = defineEmits<{ retry: [] }>();

/** 资产分布：后端给的是 Record<string, number>，组件要的是 [{ name, value }]
 *  （#1902 收敛到 AssetAllocationDonut 后，这里不再自己维护 echarts option） */
const distributionData = computed(() =>
  Object.entries(props.summary?.market_distribution ?? {}).map(
    ([name, value]) => ({ name, value })
  )
);
</script>
