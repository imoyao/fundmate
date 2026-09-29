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
        <div class="grid grid-cols-1 lg:grid-cols-12 gap-6 items-center h-full">
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
            <div ref="distributionChartRef" class="h-[220px] w-full" />
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
import { ref } from "vue";
import echarts from "@/plugins/echarts";
import type { SummaryData } from "@/api/types";
import MoneyDisplay from "@/components/MoneyDisplay/index.vue";
import SectionHeader from "@/components/SectionHeader/index.vue";
import CardBlock from "@/components/CardBlock/index.vue";
import { getCssVar } from "@/composables/echarts/theme";
import { useEchartsLifecycle } from "@/composables/echarts/useEchartsLifecycle";

defineOptions({ name: "WelcomeAssetBoard" });

const props = defineProps<{ summary: SummaryData | null }>();

const distributionChartRef = ref<HTMLDivElement | null>(null);

// 资产分布饼图：统一走 useEchartsLifecycle（异步数据页，autoRenderOnMount: false，
// 数据就绪后由页面级 onMounted 经 fetchSummary().then → nextTick 调用 expose 的 render 首绘）
const { render: renderDistributionChart } = useEchartsLifecycle(
  [
    {
      ref: distributionChartRef,
      build: el => {
        const chart = echarts.init(el);
        const chartColors = [
          getCssVar("--chart-01"),
          getCssVar("--chart-02"),
          getCssVar("--chart-03"),
          getCssVar("--chart-04")
        ];
        const hasData =
          !!props.summary?.market_distribution &&
          Object.keys(props.summary.market_distribution).length > 0;
        chart.setOption({
          tooltip: { trigger: "item" },
          title: hasData
            ? undefined
            : {
                text: "暂无资产数据",
                left: "center",
                top: "middle",
                textStyle: {
                  color: getCssVar("--text-tertiary"),
                  fontSize: 12,
                  fontWeight: "normal"
                }
              },
          legend: {
            bottom: "0%",
            left: "center",
            icon: "circle",
            itemWidth: 8,
            textStyle: {
              fontSize: 10,
              color: getCssVar("--text-tertiary")
            }
          },
          series: [
            {
              type: "pie",
              radius: ["45%", "70%"],
              avoidLabelOverlap: false,
              itemStyle: {
                borderRadius: 6,
                borderColor: getCssVar("--bg-card"),
                borderWidth: 2
              },
              label: { show: false },
              animationDuration: 1000,
              data: hasData
                ? Object.entries(props.summary.market_distribution!).map(
                    ([name, value], index) => ({
                      name,
                      value,
                      itemStyle: {
                        color: chartColors[index % chartColors.length]
                      }
                    })
                  )
                : []
            }
          ]
        });
        return chart;
      }
    }
  ],
  { autoRenderOnMount: false }
);

defineExpose({ render: renderDistributionChart });
</script>
