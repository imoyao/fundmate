<template>
  <div
    class="welcome-container p-4 md:p-8 min-h-full"
    :style="{ backgroundColor: 'var(--bg-page)' }"
  >
    <!-- 顶部欢迎语（规范：docs/design/welcome-greeting-spec.md v1.2） -->
    <div class="flex justify-between items-center mb-6" aria-live="polite">
      <div class="flex flex-col gap-2">
        <!-- 状态三：未读站内信提示条（叠加在顶部，可选迭代功能） -->
        <div
          v-if="hasUnread"
          class="flex items-center gap-2 text-sm"
          :style="{ color: 'var(--color-warning)' }"
        >
          <span>📬 你有 {{ unreadCount }} 条未读消息</span>
          <button
            type="button"
            class="underline underline-offset-2 hover:opacity-80"
            @click="openNotice"
          >
            查看
          </button>
        </div>

        <!-- 主数据行：加载中仅展示品牌定调语；数据态展示问候+天数 -->
        <div class="flex items-center gap-2">
          <template v-if="welcomeState === 'data'">
            <span
              class="font-medium"
              :style="{
                color: 'var(--text-primary)',
                fontSize: '24px',
                fontWeight: 500
              }"
            >
              <span class="welcome-nickname">{{ userTitle }}</span>
              👋 {{ greetingText }},你已记账
              <span
                class="font-bold"
                :style="{
                  color: 'var(--color-rise)',
                  fontVariantNumeric: 'tabular-nums'
                }"
                >{{ recordDays }}</span
              >
              天
            </span>
          </template>
          <span
            v-else
            class="font-medium"
            :style="{ color: 'var(--text-secondary)', fontSize: '14px' }"
          >
            把涨跌交给市场，用复利丈量自己 🌊
          </span>
        </div>

        <!-- 首页消息播报：真实数据派生，轮动展示 -->
        <Transition name="ticker-fade" mode="out-in">
          <p
            :key="tickerIndex"
            class="flex items-center gap-2 text-sm"
            :style="{ color: 'var(--text-tertiary)' }"
          >
            <span
              class="shrink-0 font-medium"
              :style="{ color: 'var(--brand-700)' }"
              >播报</span
            >
            <span>{{ currentHomeMessage }}</span>
          </p>
        </Transition>
      </div>

      <!-- 右侧按钮：仅空状态（含未读）显示「开始记账」 -->
      <router-link
        v-if="welcomeState === 'empty'"
        to="/asset/entry"
        class="btn-welcome-cta"
        aria-label="开始记账，进入持仓录入"
      >
        开始记账
      </router-link>
    </div>

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
                color: 'var(--text-tertiary)'
              }"
              title="查看资产详情"
            >
              <IconifyIconOffline icon="ep:full-screen" class="text-lg" />
            </router-link>
          </template>
        </SectionHeader>
        <CardBlock class="flex-1">
          <div
            class="grid grid-cols-1 lg:grid-cols-12 gap-6 items-center h-full"
          >
            <div class="lg:col-span-7 flex flex-col gap-6">
              <div>
                <p
                  class="text-sm mb-2"
                  :style="{ color: 'var(--text-tertiary)' }"
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
                    :style="{ color: 'var(--text-tertiary)' }"
                    >总盈亏（人民币）</span
                  >
                  <MoneyDisplay
                    :value="summary?.total_pnl_cny ?? 0"
                    size="xl"
                  />
                </div>
              </div>
              <div
                class="grid grid-cols-2 gap-4 pt-6"
                :style="{ borderTop: '1px solid var(--border-light)' }"
              >
                <div class="flex flex-col">
                  <span
                    class="text-xs mb-1"
                    :style="{ color: 'var(--text-tertiary)' }"
                    >本月资产增加</span
                  >
                  <!-- 后端暂无此口径数据，不展示编造数值 -->
                  <span
                    class="text-lg font-semibold"
                    :style="{ color: 'var(--text-tertiary)' }"
                    >—</span
                  >
                  <span
                    class="text-[10px] mt-1"
                    :style="{ color: 'var(--text-tertiary)' }"
                    >即将上线</span
                  >
                </div>
                <div class="flex flex-col">
                  <span
                    class="text-xs mb-1"
                    :style="{ color: 'var(--text-tertiary)' }"
                    >本月负债减少</span
                  >
                  <!-- 后端暂无此口径数据，不展示编造数值 -->
                  <span
                    class="text-lg font-semibold"
                    :style="{ color: 'var(--text-tertiary)' }"
                    >—</span
                  >
                  <span
                    class="text-[10px] mt-1"
                    :style="{ color: 'var(--text-tertiary)' }"
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
            :style="{ color: 'var(--text-tertiary)' }"
          >
            接入收益历史后，在此展示累计收益与净资产随时间的走势，并支持月度 /
            季度切换。
          </span>
        </CardBlock>
      </div>
    </div>

    <!-- ===== 第二排：年化收益追踪 + 市场温度（同一层级） ===== -->
    <div class="grid grid-cols-1 lg:grid-cols-2 gap-8 mb-8">
      <!-- 左：年化收益追踪 -->
      <div class="flex flex-col gap-3 card-hover card-enter h-full">
        <SectionHeader title="年化收益追踪" />
        <CardBlock class="flex-1 flex flex-col justify-center gap-4">
          <div class="flex flex-col">
            <div class="flex items-center justify-between mb-1">
              <span
                class="text-xs"
                :style="{ color: 'var(--text-tertiary)' }"
                >年化收益率（XIRR）</span
              >
              <el-radio-group v-model="includeCashEquivalents" size="small" @change="fetchXirr">
                <el-radio-button :value="false">剔除现金</el-radio-button>
                <el-radio-button :value="true">含现金</el-radio-button>
              </el-radio-group>
            </div>
            <RiseFallText
              :value="(portfolioXirr?.xirr ?? 0) * 100"
              size="lg"
              :precision="2"
            />
            <span
              class="text-[10px] mt-1"
              :style="{ color: 'var(--text-tertiary)' }"
              >{{ includeCashEquivalents ? '含货币基金/逆回购/现金，反映账户总收益' : '基于主动投资交易，不含货币基金等现金等价物' }}</span
            >
          </div>
          <div
            class="flex gap-8 pt-4"
            :style="{ borderTop: '1px solid var(--border-light)' }"
          >
            <div class="flex flex-col">
              <span
                class="text-xs mb-1"
                :style="{ color: 'var(--text-tertiary)' }"
                >当前市值</span
              >
              <MoneyDisplay
                :value="portfolioXirr?.current_value ?? 0"
                size="md"
                :show-sign="false"
              />
            </div>
            <div class="flex flex-col">
              <span
                class="text-xs mb-1"
                :style="{ color: 'var(--text-tertiary)' }"
                >总投入</span
              >
              <MoneyDisplay
                :value="portfolioXirr?.total_invested ?? 0"
                size="md"
                :show-sign="false"
              />
            </div>
          </div>
        </CardBlock>
      </div>

      <!-- 右：市场温度 -->
      <div class="flex flex-col gap-3 card-hover card-enter h-full">
        <SectionHeader title="市场温度">
          <template #action>
            <router-link
              to="/explore"
              class="text-sm font-medium transition-colors hover:opacity-80"
              :style="{ color: 'var(--text-tertiary)' }"
              >探市 →</router-link
            >
          </template>
        </SectionHeader>
        <TemperatureGaugeCard
          size="sm"
          :value="compositeTemperature?.value ?? null"
          :level="compositeTemperature?.level || ''"
          title="综合市场温度"
          caption="市场冷热 · 点击查看详细指标"
          clickable
          @click="$router.push('/explore')"
        />
        <!-- P3: 短/中/长期温度行内三连（数据来自 temperature_bands，颜色令牌留前端） -->
        <div v-if="temperatureBands" class="temp-bands">
          <div
            v-for="band in [
              temperatureBands.short,
              temperatureBands.medium,
              temperatureBands.long
            ]"
            :key="band?.name"
            class="temp-band"
          >
            <span class="temp-band__label">{{ band?.name }}</span>
            <span class="temp-band__value">{{
              band?.value != null ? band.value.toFixed(1) + "°" : "—"
            }}</span>
            <span
              class="temp-band__pill"
              :style="bandPillStyle(band?.level || '未知')"
              >{{ band?.level || "暂无" }}</span
            >
          </div>
        </div>
        <!-- B3: 综合温度环下方结论副文案（后端 conclusion 归集，前端不写死） -->
        <div v-if="temperatureConclusion" class="temp-conclusion">
          {{ temperatureConclusion }}
        </div>
      </div>
    </div>

    <!-- ===== 第三排：持仓市值最大资产 ===== -->
    <div class="grid grid-cols-1 lg:grid-cols-12 gap-8 mb-8">
      <!-- 持仓市值最大资产（风险预警改由顶部消息播报承载，本页不再保留静态风险热力图） -->
      <div
        class="lg:col-span-12 flex flex-col gap-3 card-hover card-enter h-full"
      >
        <SectionHeader :title="watchlistTitle">
          <template #action>
            <div class="flex items-center gap-2">
              <el-button
                size="small"
                type="primary"
                plain
                @click="showAddWatchlistModal = true"
              >
                <template #icon><IconifyIconOffline icon="ep:plus" /></template
                >添加
              </el-button>
              <el-button
                size="small"
                link
                @click="$router.push('/the-road-not-taken')"
                >特别关注</el-button
              >
              <el-button size="small" link @click="$router.push('/watchlist')"
                >查看全部</el-button
              >
            </div>
          </template>
        </SectionHeader>
        <WatchlistWidget
          ref="watchlistWidgetRef"
          :key="watchlistWidgetKey"
          class="flex-1"
          @select="onWatchlistSelect"
          @add="showAddWatchlistModal = true"
        />
      </div>
    </div>

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
            :style="{ color: 'var(--text-tertiary)' }"
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
            :style="{ color: 'var(--text-tertiary)' }"
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

    <!-- 添加自选弹窗 -->
    <AddToWatchlistModal
      v-model="showAddWatchlistModal"
      @submitted="onWatchlistChanged"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, nextTick, onUnmounted, computed } from "vue";
import echarts from "@/plugins/echarts";
import { getSummary } from "@/api/summary";
import { getPortfolioXirr, type XirrData } from "@/api/performance";
import { getTemperatureOverview } from "@/api/temperature";
import { getRecordStats } from "@/api/users";
import { type HomeSummaryItem } from "@/api/watchlist";
import type { SummaryData } from "@/api/types";
import WatchlistWidget from "@/components/WatchlistWidget.vue";
import AddToWatchlistModal from "@/components/QuickEntry/AddToWatchlistModal.vue";

import MoneyDisplay from "@/components/MoneyDisplay/index.vue";
import RiseFallText from "@/components/RiseFallText/index.vue";
import TemperatureGaugeCard from "@/components/TemperatureGaugeCard/index.vue";
import SectionHeader from "@/components/SectionHeader/index.vue";
import CardBlock from "@/components/CardBlock/index.vue";
import { getCssVar } from "@/composables/echarts/theme";
import { useEchartsLifecycle } from "@/composables/echarts/useEchartsLifecycle";
import { useOverviewStore } from "@/store/modules/overview";
import { useUserStoreHook } from "@/store/modules/user";

defineOptions({
  name: "Welcome"
});

// ===== 数据 =====
const summary = ref<SummaryData | null>(null);
const portfolioXirr = ref<XirrData | null>(null);
// #1354：年化收益是否纳入现金等价物（货币基金/逆回购/现金）；默认 false=仅主动投资，反映真实投资水准
const includeCashEquivalents = ref(false);

// ===== 首页欢迎语（见 docs/design/welcome-greeting-spec.md v1.2） =====
const recordDays = ref(0);
const recordLoading = ref(true);
// 未读站内信（状态三，可选迭代；当前 lay-notice 为前端示例数据，此处预留钩子）
const hasUnread = ref(false);
const unreadCount = ref(0);

type WelcomeState = "loading" | "empty" | "data";
const welcomeState = computed<WelcomeState>(() =>
  recordLoading.value ? "loading" : recordDays.value > 0 ? "data" : "empty"
);

const greetingText = computed(() => {
  const h = new Date().getHours();
  if (h >= 5 && h < 12) return "早上好";
  if (h >= 12 && h < 18) return "下午好";
  if (h >= 18 && h < 22) return "晚上好";
  return "夜深了";
});

// 用户昵称：未设置时回退为「你」，保持原有句式，零打扰
const userTitle = computed(() => useUserStoreHook().nickname || "你");

// ===== 首页消息播报（ticker）：真实数据派生，轮动展示 =====
// 原则：能算的算真实，算不了的标「即将上线」，不展示编造数字。
const homeMessages = ref<string[]>([]);
const tickerIndex = ref(0);
let tickerTimer: ReturnType<typeof setInterval> | null = null;

const currentHomeMessage = computed(() => {
  const list = homeMessages.value;
  if (list.length === 0) return "数据加载中，稍后为你播报…";
  return list[tickerIndex.value % list.length];
});

/** 汇总各异步接口已返回的真实数据，组装播报消息（各 fetch 完成后调用） */
const buildHomeMessages = () => {
  const msgs: string[] = [];
  if (summary.value) {
    const assets = summary.value.total_assets_cny;
    msgs.push(
      `家庭总资产 ${assets.toLocaleString("zh-CN", { maximumFractionDigits: 0 })} 元`
    );
    const pnl = summary.value.total_pnl_cny;
    if (pnl !== 0) {
      msgs.push(
        `累计盈亏 ${pnl > 0 ? "+" : ""}${pnl.toLocaleString("zh-CN", { maximumFractionDigits: 0 })} 元`
      );
    }
  }
  if (portfolioXirr.value?.xirr != null) {
    const x = Number(portfolioXirr.value.xirr);
    msgs.push(`年化收益率（XIRR）${(x * 100).toFixed(2)}%`);
  }
  if (compositeTemperature.value) {
    const value = compositeTemperature.value.value;
    const level = compositeTemperature.value.level || "未知";
    msgs.push(`市场温度 ${value != null ? value.toFixed(1) : "--"}°，${level}`);
  }
  if (temperatureConclusion.value) {
    msgs.push(temperatureConclusion.value);
  }
  if (recordDays.value > 0) {
    msgs.push(`你已连续记账 ${recordDays.value} 天，坚持就是复利`);
  }
  homeMessages.value = msgs;
  tickerIndex.value = 0;
};

const startTicker = () => {
  tickerTimer = setInterval(() => {
    if (homeMessages.value.length > 1) {
      tickerIndex.value = (tickerIndex.value + 1) % homeMessages.value.length;
    }
  }, 5000);
};

const openNotice = () => {
  // TODO: 待 lay-notice 真实站内信路由接入后替换；当前无真实跳转目标
  console.debug("[welcome] 打开站内信：待 lay-notice 路由接入");
};

// 综合市场温度（第二排右卡）
const compositeTemperature = ref<{ value: number; level: string } | null>(null);

// B1/P3: 短/中/长期温度分解（概览页行内三连）。仅消费后端 value/level，颜色令牌留前端。
type TempBand = { name: string; value: number | null; level: string };
const temperatureBands = ref<{
  short?: TempBand;
  medium?: TempBand;
  long?: TempBand;
} | null>(null);

// B3: 综合温度环下方结论副文案（后端 conclusion 归集，前端不写死）
const temperatureConclusion = ref("");

// level → 温度语义色令牌（B3 边界：色令牌留前端，禁后端下发颜色码）
const levelColorVar: Record<string, string> = {
  偏低: "var(--temp-low)",
  适中: "var(--temp-mid)",
  偏高: "var(--temp-high)",
  未知: "var(--text-tertiary)"
};
const levelBgVar: Record<string, string> = {
  偏低: "var(--temp-low-bg)",
  适中: "var(--temp-mid-bg)",
  偏高: "var(--temp-high-bg)",
  未知: "var(--bg-soft)"
};
const bandPillStyle = (level: string) => ({
  color: levelColorVar[level] || levelColorVar["未知"],
  backgroundColor: levelBgVar[level] || levelBgVar["未知"]
});

const distributionChartRef = ref<HTMLDivElement | null>(null);
const showAddWatchlistModal = ref(false);
const watchlistWidgetKey = ref(0);

// 资产分布饼图：统一走 useEchartsLifecycle（异步数据页，autoRenderOnMount: false，数据就绪后手动 render）
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
          !!summary.value?.market_distribution &&
          Object.keys(summary.value.market_distribution).length > 0;
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
                ? Object.entries(summary.value!.market_distribution!).map(
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

// 心理账户：接入 overview store（store 内为示例数据，待后端提供真实接口）
const overviewStore = useOverviewStore();
const mentalAccounts = computed(() => {
  const accounts = overviewStore.psychAccount.accounts;
  const parsed = accounts.map(a => ({
    name: a.label,
    tone: a.tone,
    amount: Number(String(a.value).replace(/[^\d.]/g, "")) || 0
  }));
  const total = parsed.reduce((s, a) => s + a.amount, 0) || 1;
  const toneColor: Record<string, string> = {
    safe: "var(--color-success)",
    neutral: "var(--brand-700)",
    warning: "var(--color-warning)",
    danger: "var(--color-danger)"
  };
  return parsed.map(a => ({
    name: a.name,
    amount: a.amount, // 金额格式化交给模板中的 MoneyDisplay 组件
    percent: Math.round((a.amount / total) * 100),
    color: toneColor[a.tone] || "var(--brand-700)"
  }));
});

// ===== 近期动态 feed：真实数据派生，避免空壳（后端事件日志就绪后可替换为事件流） =====
type HomeFeedItem = { key: string; text: string; color: string };
const homeFeed = computed<HomeFeedItem[]>(() => {
  const items: HomeFeedItem[] = [];
  if (summary.value) {
    const pnl = summary.value.total_pnl_cny;
    items.push({
      key: "pnl",
      text: `累计盈亏 ${pnl >= 0 ? "+" : ""}${pnl.toLocaleString("zh-CN", { maximumFractionDigits: 0 })} 元`,
      color: pnl >= 0 ? "var(--color-rise)" : "var(--color-fall)"
    });
  }
  if (portfolioXirr.value?.xirr != null) {
    const x = Number(portfolioXirr.value.xirr);
    items.push({
      key: "xirr",
      text: `年化收益率（XIRR）${(x * 100).toFixed(2)}%`,
      color: x >= 0 ? "var(--color-rise)" : "var(--color-fall)"
    });
  }
  if (compositeTemperature.value) {
    const value = compositeTemperature.value.value;
    const level = compositeTemperature.value.level || "未知";
    items.push({
      key: "temperature",
      text: `市场温度 ${value != null ? value.toFixed(1) : "--"}°，${level}`,
      color: levelColorVar[level] || "var(--text-tertiary)"
    });
  }
  if (recordDays.value > 0) {
    items.push({
      key: "record-days",
      text: `已连续记账 ${recordDays.value} 天`,
      color: "var(--brand-700)"
    });
  }
  if (temperatureConclusion.value) {
    items.push({
      key: "conclusion",
      text: temperatureConclusion.value,
      color: "var(--text-tertiary)"
    });
  }
  return items;
});

// 新增：WatchlistWidget 的 ref，用于读取 hasPinned
const watchlistWidgetRef = ref<InstanceType<typeof WatchlistWidget> | null>(
  null
);

// 新增：动态标题
const watchlistTitle = computed(() => {
  if (!watchlistWidgetRef.value) return "自选资产";
  return watchlistWidgetRef.value.hasPinned ? "置顶资产" : "持仓市值最大资产";
});

// ===== API 请求 =====
const fetchRecordStats = async () => {
  recordLoading.value = true;
  try {
    const res = await getRecordStats();
    recordDays.value = res.data?.record_days ?? 0;
  } catch (e) {
    // 欢迎语非关键路径：失败静默降级，保持品牌定调语
    console.debug("Failed to fetch record stats:", e);
    recordDays.value = 0;
  } finally {
    recordLoading.value = false;
    buildHomeMessages();
  }
};

const fetchSummary = async () => {
  try {
    const res = await getSummary();
    summary.value = res.data;
  } catch (e) {
    console.error("Failed to fetch summary:", e);
  } finally {
    buildHomeMessages();
  }
};

const fetchXirr = async () => {
  try {
    const res = await getPortfolioXirr("portfolio", undefined, includeCashEquivalents.value);
    portfolioXirr.value = res.data;
  } catch (e) {
    console.error("获取年化收益率失败", e);
  } finally {
    buildHomeMessages();
  }
};

// 综合市场温度（首页概览级，只取综合值，轻量）
const fetchTemperature = async () => {
  try {
    const res = await getTemperatureOverview();
    const data = res.data;
    if (!data) return;
    const composite = data.composites?.composite_temperature;
    if (composite) {
      compositeTemperature.value = {
        value: composite.value,
        level: composite.level || ""
      };
    }
    const bands = data.composites?.temperature_bands;
    if (bands) {
      temperatureBands.value = {
        short: bands.short
          ? {
              name: bands.short.name,
              value: bands.short.value,
              level: bands.short.level || ""
            }
          : undefined,
        medium: bands.medium
          ? {
              name: bands.medium.name,
              value: bands.medium.value,
              level: bands.medium.level || ""
            }
          : undefined,
        long: bands.long
          ? {
              name: bands.long.name,
              value: bands.long.value,
              level: bands.long.level || ""
            }
          : undefined
      };
    }
    temperatureConclusion.value = data.conclusion || "";
  } catch (e) {
    console.error("获取市场温度失败:", e);
  } finally {
    buildHomeMessages();
  }
};

// ===== 事件处理 =====
const onWatchlistSelect = (item: HomeSummaryItem) => {
  // TODO: 跳转到资产详情
};

const onWatchlistChanged = () => {
  watchlistWidgetKey.value++;
};

// 资产分布饼图的生命周期与渲染由 useEchartsLifecycle 统一管理（见 renderDistributionChart）

// ===== 生命周期 =====
onMounted(() => {
  fetchSummary().then(() => nextTick(renderDistributionChart));
  fetchXirr();
  fetchTemperature();
  fetchRecordStats();
  startTicker();
});

onUnmounted(() => {
  if (tickerTimer) {
    clearInterval(tickerTimer);
    tickerTimer = null;
  }
});
</script>

<style scoped>
@keyframes fade-up {
  from {
    opacity: 0;
    transform: translateY(24px);
  }

  to {
    opacity: 1;
    transform: translateY(0);
  }
}

.welcome-nickname {
  padding: 0 8px;
  font-weight: 600;
  color: var(--text-primary);
  background: var(--brand-100);
  border-radius: 8px;
}

/* 顶部消息播报轮动过渡 */
.ticker-fade-enter-active,
.ticker-fade-leave-active {
  transition:
    opacity 0.3s ease,
    transform 0.3s ease;
}

.ticker-fade-enter-from {
  opacity: 0;
  transform: translateY(8px);
}

.ticker-fade-leave-to {
  opacity: 0;
  transform: translateY(-8px);
}

.welcome-container {
  font-family: var(
    --font-sans,
    "PingFang SC",
    "Hiragino Sans GB",
    "Microsoft YaHei",
    sans-serif
  );
}

.card-enter {
  opacity: 0;
  animation: fade-up 0.6s cubic-bezier(0.4, 0, 0.2, 1) forwards;
}

.card-enter:nth-child(1) {
  animation-delay: 0.05s;
}

.card-enter:nth-child(2) {
  animation-delay: 0.1s;
}

.card-enter:nth-child(3) {
  animation-delay: 0.15s;
}

.card-enter:nth-child(4) {
  animation-delay: 0.2s;
}

.card-enter:nth-child(5) {
  animation-delay: 0.25s;
}

.card-hover {
  transition: all 0.25s cubic-bezier(0.4, 0, 0.2, 1);
}

.card-hover:hover {
  box-shadow: var(--shadow-float) !important;
}

.mental-account-item {
  transition:
    background-color 0.2s ease,
    border-color 0.2s ease;
}

.mental-account-item:hover {
  background-color: var(--bg-hover);
  border-color: var(--border-default) !important;
}

.hover-card-btn {
  transition:
    background-color 0.2s ease,
    color 0.2s ease,
    transform 0.2s ease;
}

.hover-card-btn:hover {
  color: var(--bg-card) !important;
  background-color: var(--brand-700) !important;
  transform: scale(1.05);
}

.text-hero {
  font-family: var(--font-sans, Inter, -apple-system, sans-serif);
  font-weight: 600;
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
}

/* 首页欢迎语 CTA（胶囊，CTA 例外；交互态遵循 design.md 主按钮规范） */
.btn-welcome-cta {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  height: 40px;
  padding: 8px 20px;
  font-size: 14px;
  font-weight: 500;
  line-height: 1;
  color: #fff;
  white-space: nowrap;
  background-color: var(--brand-700);
  border-radius: var(--radius-pill);
  transition:
    background-color 0.2s ease,
    transform 0.1s ease;
}

.btn-welcome-cta:hover {
  background-color: var(--brand-800);
}

.btn-welcome-cta:active {
  background-color: var(--brand-900);
  transform: translateY(1px);
}

.btn-welcome-cta:focus-visible {
  outline: none;
  box-shadow: var(--focus-ring);
}

/* ===== 短/中/长期温度行内三连（P3） ===== */
.temp-bands {
  display: flex;
  flex-wrap: wrap;
  gap: 10px 14px;
  align-items: center;
  padding: 10px 12px;
  margin-top: 4px;
  background: var(--bg-soft);
  border-radius: 12px;
}

.temp-band {
  display: inline-flex;
  gap: 5px;
  align-items: center;
  font-size: 12px;
  line-height: 1.4;
}

.temp-band__label {
  color: var(--text-secondary);
  white-space: nowrap;
}

.temp-band__value {
  font-family: var(--font-mono, monospace);
  font-weight: 600;
  font-variant-numeric: tabular-nums;
  color: var(--text-primary);
}

.temp-band__pill {
  padding: 1px 7px;
  font-size: 11px;
  font-weight: 500;
  white-space: nowrap;
  border-radius: 999px;
}

/* B3: 综合温度环下方结论副文案 */
.temp-conclusion {
  padding: 8px 12px;
  margin-top: 8px;
  font-size: 13px;
  line-height: 1.5;
  color: var(--text-secondary);
  background: var(--bg-soft);
  border-radius: 10px;
}

/* 欢迎语昵称：暖色背景 chip 表达「这位用户对我们很特别、被关心」。
   文字保持主色、不用红色——避讳人名用红色（关联墓碑/断交等不吉意味）。 */

/* 与之前一致，保持不变 */
</style>
