<template>
  <!-- ===== 第一排：核心资产看板（#1812 后扩为满宽 12） ===== -->
  <div class="grid grid-cols-1 xl:grid-cols-12 gap-8 mb-8">
    <!-- 左侧：家庭资产看板 -->
    <div class="xl:col-span-12 flex flex-col gap-3 card-hover card-enter">
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
              <span
                class="text-[10px]"
                :style="{ color: 'var(--text-tertiary-ink)' }"
                >按资产大类</span
              >
            </div>
            <AssetAllocationDonut
              :data="distributionData"
              class="h-[220px]"
              :color-map="CATEGORY_COLOR_MAP"
              :legend-font-size="10"
              :show-legend-percent="true"
            />
          </div>
        </div>
      </CardBlock>
    </div>

    <!-- #1812：原「收益趋势」空占位已移除。
         该栏自 2026-08 起一直是「即将上线」文字占位（无 ECharts 实例、无数据请求），
         而它的承诺口径（累计收益 / 净资产随时间走势）是**净值曲线**，
         与 #1812 的「逐日盈亏日历」不是同一形态，硬塞进日历组件属口径混淆。
         逐日盈亏已由welcome 第三排的 PnlCalendar 承担；净值曲线归复盘页
         （docs/features/asset-review.md 组件 3）规划。
         左栏因此从 xl:col-span-8 扩为满宽 12，避免右侧留 4 列空洞
         （design.md MetricGrid 条：禁止右侧大片空白）。 -->
  </div>
</template>

<script setup lang="ts">
import { computed } from "vue";
import type { SummaryData } from "@/api/types";
import type { DistributionsData } from "@/api/summary";
import MoneyDisplay from "@/components/MoneyDisplay/index.vue";
import SectionHeader from "@/components/SectionHeader/index.vue";
import CardBlock from "@/components/CardBlock/index.vue";
import AssetAllocationDonut from "@/components/Charts/AssetAllocationDonut.vue";
import {
  buildDistributionData,
  CATEGORY_COLOR_MAP
} from "../composables/distributionLogic";

defineOptions({ name: "WelcomeAssetBoard" });

const props = withDefaults(
  defineProps<{
    summary: SummaryData | null;
    /** 汇总请求失败（#1832）：为 true 时渲染「加载失败 + 重试」，不显示 ¥0 */
    error?: boolean;
    /** 多维分布（`/api/summary/distributions/`）；环形图的数据源 */
    distributions?: DistributionsData | null;
  }>(),
  { distributions: null }
);

const emit = defineEmits<{ retry: [] }>();

/**
 * 资产分布：走 `distributionLogic` 的统一口径（#1955）。
 *
 * **不再用 `summary.market_distribution`**（#1902 遗留）：那份按持仓 `market`
 * 分组，实测本机 154 笔持仓全为 `CN_A`，只回一个扇区，环上画成整圈单色；
 * 且只覆盖持仓市值（65.9 万），与左侧「家庭总资产」（390.4 万）不同口径。
 * 详见 distributionLogic.ts 顶部的缺陷背景。
 */
const distributionData = computed(() =>
  buildDistributionData(props.distributions)
);
</script>
