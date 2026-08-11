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
              {{ greetingText }} 👋 你已记账
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
        <div
          class="rounded-2xl p-8 relative h-full"
          :style="{
            backgroundColor: 'var(--bg-card)',
            boxShadow: 'var(--shadow-raised)',
            border: '1px solid var(--border-light)'
          }"
        >
          <div class="grid grid-cols-1 lg:grid-cols-12 gap-6 items-center">
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
                  <!-- TODO: 接入真实 API 数据 -->
                  <MoneyDisplay
                    :value="28973.83"
                    size="lg"
                    :show-currency="true"
                  />
                </div>
                <div class="flex flex-col">
                  <span
                    class="text-xs mb-1"
                    :style="{ color: 'var(--text-tertiary)' }"
                    >本月负债减少</span
                  >
                  <!-- TODO: 接入真实 API 数据 -->
                  <MoneyDisplay
                    :value="-20406.12"
                    size="lg"
                    :show-currency="true"
                  />
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
                  class="px-2 py-0.5 rounded text-[10px] font-bold"
                  :style="{
                    backgroundColor: 'var(--brand-100)',
                    color: 'var(--brand-700)'
                  }"
                  >中等风险</span
                >
              </div>
              <div ref="distributionChartRef" class="h-[220px] w-full" />
            </div>
          </div>
        </div>
      </div>

      <!-- 右侧：收益趋势 -->
      <div class="xl:col-span-4 flex flex-col gap-3 card-hover card-enter">
        <div class="flex justify-between items-center h-8">
          <h3
            class="font-bold text-lg"
            :style="{ color: 'var(--text-primary)' }"
          >
            收益趋势
          </h3>
          <el-button-group size="small">
            <el-button
              :type="trendMode === 'month' ? 'primary' : 'default'"
              @click="trendMode = 'month'"
              >月度</el-button
            >
            <el-button
              :type="trendMode === 'quarter' ? 'primary' : 'default'"
              @click="trendMode = 'quarter'"
              >季度</el-button
            >
          </el-button-group>
        </div>
        <div
          class="rounded-2xl p-6 h-full flex flex-col"
          :style="{
            backgroundColor: 'var(--bg-card)',
            boxShadow: 'var(--shadow-raised)',
            border: '1px solid var(--border-light)'
          }"
        >
          <div ref="trendChartRef" class="flex-1 min-h-[180px] w-full" />
          <div
            class="mt-4 pt-4 flex flex-col gap-0.5"
            :style="{ borderTop: '1px solid var(--border-light)' }"
          >
            <p
              class="text-[10px] mb-1"
              :style="{ color: 'var(--text-tertiary)' }"
            >
              风险评分建议
            </p>
            <div class="flex items-center justify-between">
              <span
                class="text-xl font-bold"
                :style="{ color: 'var(--text-primary)' }"
                >65/100</span
              >
            </div>
            <span class="text-[10px]" :style="{ color: 'var(--brand-700)' }"
              >建议增加稳健型配置</span
            >
          </div>
        </div>
      </div>
    </div>

    <!-- ===== 第二排：年化收益追踪 + 市场温度（同一层级） ===== -->
    <div class="grid grid-cols-1 lg:grid-cols-2 gap-8 mb-8">
      <!-- 左：年化收益追踪 -->
      <div class="flex flex-col gap-3 card-hover card-enter h-full">
        <SectionHeader title="年化收益追踪" />
        <div
          class="rounded-2xl p-6 h-full flex flex-col justify-center gap-4"
          :style="{
            backgroundColor: 'var(--bg-card)',
            boxShadow: 'var(--shadow-raised)',
            border: '1px solid var(--border-light)'
          }"
        >
          <div class="flex flex-col">
            <span
              class="text-xs mb-1"
              :style="{ color: 'var(--text-tertiary)' }"
              >年化收益率（XIRR）</span
            >
            <RiseFallText
              :value="portfolioXirr?.xirr ?? 0"
              size="lg"
              :precision="2"
            />
            <span
              class="text-[10px] mt-1"
              :style="{ color: 'var(--text-tertiary)' }"
              >基于所有主动投资交易，不含货币基金</span
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
        </div>
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

    <!-- ===== 第三排：持仓市值最大资产 + 风险热力图 ===== -->
    <div class="grid grid-cols-1 lg:grid-cols-12 gap-8 mb-8">
      <!-- 左侧：持仓市值最大资产 -->
      <div
        class="lg:col-span-8 flex flex-col gap-3 card-hover card-enter h-full"
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

      <!-- 右侧：风险热力图 -->
      <div class="lg:col-span-4 flex flex-col gap-3 card-hover card-enter">
        <SectionHeader title="风险热力图" />
        <div
          class="rounded-2xl p-6 h-full flex flex-col"
          :style="{
            backgroundColor: 'var(--bg-card)',
            boxShadow: 'var(--shadow-raised)',
            border: '1px solid var(--border-light)'
          }"
        >
          <div class="flex-1 flex items-center justify-center w-full pb-4">
            <div ref="riskHeatmapRef" class="w-full h-full max-h-[240px]" />
          </div>
          <!-- 🆕 图例颜色改为 CSS 变量 -->
          <div class="flex justify-center gap-4 mt-3 text-[8px]">
            <div
              class="flex items-center gap-1"
              :style="{ color: 'var(--text-tertiary)' }"
            >
              <span
                class="w-2 h-2 rounded-sm"
                :style="{ backgroundColor: 'var(--color-fall)' }"
              />低风险
            </div>
            <div
              class="flex items-center gap-1"
              :style="{ color: 'var(--text-tertiary)' }"
            >
              <span
                class="w-2 h-2 rounded-sm"
                :style="{ backgroundColor: 'var(--color-warning)' }"
              />中风险
            </div>
            <div
              class="flex items-center gap-1"
              :style="{ color: 'var(--text-tertiary)' }"
            >
              <span
                class="w-2 h-2 rounded-sm"
                :style="{ backgroundColor: 'var(--color-danger)' }"
              />高风险
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- ===== 第四排：财务晴雨表 + 心理账户（统一 12 列栅格 + 等宽右栏） ===== -->
    <div class="grid grid-cols-1 lg:grid-cols-12 gap-8 mb-8">
      <!-- 财务晴雨表 -->
      <div class="lg:col-span-8 flex flex-col gap-3">
        <SectionHeader
          title="财务晴雨表"
          info="基于你的资产负债表与现金流测算的四项关键财务健康度指标"
        />
        <div class="grid grid-cols-2 md:grid-cols-4 gap-4">
          <div
            v-for="metric in financialMetrics"
            :key="metric.label"
            class="rounded-2xl p-6 card-hover"
            :style="{
              backgroundColor: 'var(--bg-card)',
              boxShadow: 'var(--shadow-raised)',
              border: '1px solid var(--border-light)'
            }"
          >
            <p
              class="text-[10px] mb-2"
              :style="{ color: 'var(--text-tertiary)' }"
            >
              {{ metric.label }}
            </p>
            <p
              class="text-xl font-bold"
              :style="{ color: 'var(--text-primary)' }"
            >
              {{ metric.value
              }}<span
                class="text-[10px] font-normal ml-0.5"
                :style="{ color: 'var(--text-tertiary)' }"
                >%</span
              >
            </p>
            <p
              class="text-[8px] mt-2 font-medium"
              :style="{ color: 'var(--text-tertiary)' }"
            >
              {{ metric.subLabel }}
            </p>
          </div>
        </div>
        <div
          class="rounded-2xl p-6 card-hover"
          :style="{
            backgroundColor: 'var(--bg-card)',
            boxShadow: 'var(--shadow-raised)',
            border: '1px solid var(--border-light)'
          }"
        >
          <div class="flex justify-between items-center mb-4">
            <span
              class="font-bold text-sm"
              :style="{ color: 'var(--text-secondary)' }"
              >资产变动趋势</span
            >
            <div ref="miniAssetChartRef" class="w-48 h-12" />
          </div>
          <div
            class="mt-6 pt-4"
            :style="{ borderTop: '1px solid var(--border-light)' }"
          >
            <div class="flex items-center justify-between mb-3">
              <span
                class="text-sm font-medium"
                :style="{ color: 'var(--text-secondary)' }"
                >近期动态</span
              >
              <span
                class="text-[10px]"
                :style="{ color: 'var(--text-tertiary)' }"
                >暂无记录</span
              >
            </div>
            <div class="space-y-2 opacity-60">
              <div
                class="h-2 rounded-full w-3/4"
                :style="{ backgroundColor: 'var(--bg-soft)' }"
              />
              <div
                class="h-2 rounded-full w-1/2"
                :style="{ backgroundColor: 'var(--bg-soft)' }"
              />
            </div>
          </div>
        </div>
      </div>

      <!-- 心理账户（与财务晴雨表同宽右栏 4 列，外层已统一白底卡片容器） -->
      <div class="lg:col-span-4 flex flex-col gap-3 h-full">
        <SectionHeader title="心理账户" />
        <div
          class="rounded-2xl p-6 h-full flex flex-col flex-1 card-hover card-enter"
          :style="{
            backgroundColor: 'var(--bg-card)',
            boxShadow: 'var(--shadow-raised)',
            border: '1px solid var(--border-light)'
          }"
        >
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
        </div>
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
import { getPortfolioXirr } from "@/api/performance";
import { getTemperatureOverview } from "@/api/temperature";
import { getRecordStats } from "@/api/users";
import type { SummaryData } from "@/api/types";
import WatchlistWidget from "@/components/WatchlistWidget.vue";
import AddToWatchlistModal from "@/components/QuickEntry/AddToWatchlistModal.vue";

import MoneyDisplay from "@/components/MoneyDisplay/index.vue";
import RiseFallText from "@/components/RiseFallText/index.vue";
import TemperatureGaugeCard from "@/components/TemperatureGaugeCard/index.vue";
import SectionHeader from "@/components/SectionHeader/index.vue";
import { useOverviewStore } from "@/store/modules/overview";

defineOptions({
  name: "Welcome"
});

// ===== 数据 =====
const summary = ref<SummaryData | null>(null);
const portfolioXirr = ref<any>(null);
const trendMode = ref<"month" | "quarter">("month");

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
const trendChartRef = ref<HTMLDivElement | null>(null);
const riskHeatmapRef = ref<HTMLDivElement | null>(null);
const miniAssetChartRef = ref<HTMLDivElement | null>(null);
const showAddWatchlistModal = ref(false);
const watchlistWidgetKey = ref(0);

let charts: echarts.ECharts[] = [];

// ===== 静态数据（待接入 API） =====
const financialMetrics = [
  { label: "资产负债率", value: "49.03", subLabel: "偿债能力" }, // TODO: 接入 API
  { label: "预估储蓄率", value: "46.06", subLabel: "储蓄能力" },
  { label: "财务自由度", value: "22.83", subLabel: "自由指标" },
  { label: "躺平度", value: "12.31", subLabel: "2026年" }
];

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
    safe: "var(--c-success)",
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
  }
};

const fetchSummary = async () => {
  try {
    const res = await getSummary();
    summary.value = res.data;
  } catch (e) {
    console.error("Failed to fetch summary:", e);
  }
};

const fetchXirr = async () => {
  try {
    const res = await getPortfolioXirr("portfolio");
    portfolioXirr.value = res.data;
  } catch (e) {
    console.error("获取年化收益率失败", e);
  }
};

// 综合市场温度（首页概览级，只取综合值，轻量）
const fetchTemperature = async () => {
  try {
    const res = await getTemperatureOverview();
    const data = (res as any)?.data;
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
  }
};

// ===== 事件处理 =====
const onWatchlistSelect = (item: any) => {
  // TODO: 跳转到资产详情
};

const onWatchlistChanged = () => {
  watchlistWidgetKey.value++;
};

// ===== 工具函数：读取 CSS 变量 =====
// 工具函数：读取 CSS 变量
const getCSSColor = (varName: string): string => {
  if (typeof window === "undefined") return "";
  return getComputedStyle(document.documentElement)
    .getPropertyValue(varName)
    .trim();
};

// ===== 图表初始化 =====
const initCharts = () => {
  // 1. 资产分布饼图
  if (distributionChartRef.value) {
    const chart = echarts.init(distributionChartRef.value);

    const chartColors = [
      getCSSColor("--chart-01"),
      getCSSColor("--chart-02"),
      getCSSColor("--chart-03"),
      getCSSColor("--chart-04")
    ];

    const hasData =
      summary.value?.market_distribution &&
      Object.keys(summary.value.market_distribution).length > 0;

    chart.setOption({
      tooltip: { trigger: "item" },
      legend: {
        bottom: "0%",
        left: "center",
        icon: "circle",
        itemWidth: 8,
        textStyle: {
          fontSize: 10,
          color: getCSSColor("--text-tertiary")
        }
      },
      series: [
        {
          type: "pie",
          radius: ["45%", "70%"],
          avoidLabelOverlap: false,
          itemStyle: {
            borderRadius: 6,
            borderColor: getCSSColor("--bg-card"),
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
            : [
                {
                  value: 856240,
                  name: "股票",
                  itemStyle: { color: chartColors[0] }
                },
                {
                  value: 678950,
                  name: "基金",
                  itemStyle: { color: chartColors[1] }
                },
                {
                  value: 810488,
                  name: "房产",
                  itemStyle: { color: chartColors[2] }
                },
                {
                  value: 212400,
                  name: "贵金属",
                  itemStyle: { color: chartColors[3] }
                }
              ]
        }
      ]
    });
    charts.push(chart);
  }

  // 2. 收益趋势折线图
  if (trendChartRef.value) {
    const chart = echarts.init(trendChartRef.value);
    const riseColor = getCSSColor("--color-rise");

    chart.setOption({
      grid: {
        left: "3%",
        right: "4%",
        top: "10%",
        bottom: "3%",
        containLabel: true
      },
      xAxis: {
        type: "category",
        boundaryGap: false,
        data: ["1月", "2月", "3月", "4月", "5月", "6月", "7月"],
        axisLine: {
          lineStyle: { color: getCSSColor("--border-light") }
        },
        axisLabel: {
          color: getCSSColor("--text-tertiary"),
          fontSize: 10
        }
      },
      yAxis: {
        type: "value",
        splitLine: {
          lineStyle: { color: getCSSColor("--border-light") }
        },
        axisLabel: {
          color: getCSSColor("--text-tertiary"),
          fontSize: 10
        }
      },
      series: [
        {
          // TODO: 接入收益趋势 API 替换静态数据
          data: [120, 190, 170, 220, 280, 250, 310],
          type: "line",
          smooth: true,
          symbol: "circle",
          symbolSize: 6,
          itemStyle: { color: riseColor },
          lineStyle: { width: 3, color: riseColor },
          areaStyle: {
            color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
              { offset: 0, color: riseColor + "33" },
              { offset: 1, color: riseColor + "00" }
            ])
          },
          animationDuration: 1200
        }
      ]
    });
    charts.push(chart);
  }

  // 3. 风险热力图
  if (riskHeatmapRef.value) {
    const chart = echarts.init(riskHeatmapRef.value);
    const textColor = getCSSColor("--text-tertiary");
    const lowRiskColor = getCSSColor("--color-fall");
    const midRiskColor = getCSSColor("--color-warning");
    const highRiskColor = getCSSColor("--color-danger");

    chart.setOption({
      grid: {
        left: "3%",
        right: "4%",
        top: "10%",
        bottom: "3%",
        containLabel: true
      },
      xAxis: {
        type: "category",
        data: ["股票", "基金", "房产", "贵金属"],
        axisLine: { show: false },
        axisTick: { show: false },
        axisLabel: { color: textColor, fontSize: 10 }
      },
      yAxis: {
        type: "value",
        max: 100,
        splitLine: {
          lineStyle: { color: getCSSColor("--border-light") }
        },
        axisLabel: { color: textColor, fontSize: 10 }
      },
      series: [
        {
          data: [
            { value: 85, itemStyle: { color: highRiskColor } },
            { value: 60, itemStyle: { color: midRiskColor } },
            { value: 30, itemStyle: { color: lowRiskColor } },
            { value: 55, itemStyle: { color: midRiskColor } }
          ],
          type: "bar",
          barWidth: 20,
          itemStyle: { borderRadius: [4, 4, 0, 0] },
          animationDuration: 800
        }
      ]
    });
    charts.push(chart);
  }

  // 4. 迷你资产变动图
  if (miniAssetChartRef.value) {
    const chart = echarts.init(miniAssetChartRef.value);
    const brandColor = getCSSColor("--brand-700");
    const softColor = getCSSColor("--bg-soft");

    chart.setOption({
      grid: { left: 0, right: 0, top: 10, bottom: 0 },
      xAxis: {
        type: "category",
        data: ["1月", "2月", "3月", "4月"],
        show: false
      },
      yAxis: { show: false },
      series: [
        {
          type: "bar",
          data: [
            { value: 15, itemStyle: { color: softColor } },
            { value: 25, itemStyle: { color: softColor } },
            { value: 45, itemStyle: { color: brandColor } },
            { value: 65, itemStyle: { color: brandColor } }
          ],
          barWidth: 10,
          itemStyle: { borderRadius: [2, 2, 0, 0] }
        }
      ]
    });
    charts.push(chart);
  }
};

const handleResize = () => {
  charts.forEach(chart => chart.resize());
};

// ===== 生命周期 =====
onMounted(() => {
  fetchSummary().then(() => {
    nextTick(initCharts);
  });
  fetchXirr();
  fetchTemperature();
  fetchRecordStats();
  window.addEventListener("resize", handleResize);
});

onUnmounted(() => {
  window.removeEventListener("resize", handleResize);
  charts.forEach(chart => chart.dispose());
  charts = [];
});
</script>

<style scoped>
@keyframes fadeUp {
  from {
    opacity: 0;
    transform: translateY(24px);
  }

  to {
    opacity: 1;
    transform: translateY(0);
  }
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
  animation: fadeUp 0.6s cubic-bezier(0.4, 0, 0.2, 1) forwards;
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
  transform: translateY(-3px);
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
  border-radius: var(--radius-pill);
  background-color: var(--brand-700);
  color: #fff;
  font-size: 14px;
  font-weight: 500;
  line-height: 1;
  white-space: nowrap;
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

/* 与之前一致，保持不变 */
</style>
