<!-- frontend/src/views/temperature/index.vue -->
<template>
  <div class="temperature-page">
    <!-- 顶部导航（公共组件，与探市完全一致） -->
    <MarketHeader :logo="MARKET_LOGO" badge="温度计" :navs="headerNavs" />

    <!-- 未登录引导条：温度计页为公开数据页（D4），登录态仅用于转化引导 -->
    <section v-if="!isAuthenticated" class="auth-banner">
      <div class="auth-banner__inner">
        <div class="auth-banner__text">
          登录后可使用极致自选管理（分组 / 标签 / AI 批量导入）
        </div>
        <el-button size="small" type="primary" @click="goAuth">
          登录 / 注册
        </el-button>
      </div>
    </section>

    <!-- 页面内容 -->
    <div v-loading="loading" class="page-content">
      <!-- 综合仪表盘 -->
      <section class="dashboard-section">
        <MetricGrid>
          <!-- 综合温度仪表（大） -->
          <TemperatureGaugeCard
            :value="compositeValue"
            title="综合市场温度"
            :level="compositeLevel"
            caption="基于多源市场数据计算"
            :updated-at="updatedAt"
            size="lg"
            featured
          />

          <!-- 核心指标卡片 -->
          <MetricCard
            v-for="metric in coreMetrics"
            :key="metric.key"
            :title="metric.title"
            :value="metric.value"
            :unit="metric.unit"
            :level="metric.level"
          />
        </MetricGrid>
      </section>

      <!-- 温度解读 + 市场机会：与仪表卡配套，放在趋势图上方 -->
      <section class="context-section">
        <div class="context-grid">
          <TemperatureContextCard
            :temperature="compositeValue"
            :fear-greed="fearGreedValue"
            :fear-greed-label="fearGreedLabel"
            :periods="tempPeriods"
            caption="综合 6 个市场指标与市场情绪推导"
            class="context-card"
          />

          <!-- 市场机会（来自 temperature store，由综合温度与股债性价比推导） -->
          <div v-if="tempStore.opportunityList.length" class="opportunity-card">
            <SectionHeader title="市场机会" />
            <div class="opportunity-list">
              <div
                v-for="op in tempStore.opportunityList"
                :key="op.name"
                class="opportunity-item"
                :class="`opportunity-item--${op.tone}`"
              >
                <div class="opportunity-head">
                  <span class="opportunity-name">{{ op.name }}</span>
                  <span class="opportunity-tag">{{
                    op.tone === "safe"
                      ? "机会"
                      : op.tone === "danger"
                        ? "风险"
                        : "中性"
                  }}</span>
                </div>
                <p class="opportunity-desc">{{ op.desc }}</p>
              </div>
            </div>
          </div>
        </div>
      </section>

      <!-- 温度趋势图 -->
      <section class="chart-section">
        <SectionHeader title="综合温度趋势">
          <template #action>
            <el-radio-group
              v-model="historyDays"
              size="small"
              @change="fetchHistory"
            >
              <el-radio-button :value="30">30天</el-radio-button>
              <el-radio-button :value="90">90天</el-radio-button>
              <el-radio-button :value="180">半年</el-radio-button>
            </el-radio-group>
          </template>
        </SectionHeader>
        <div class="chart-wrapper">
          <v-chart
            ref="chartRef"
            :option="chartOption"
            :autoresize="true"
            style="width: 100%; height: 300px"
          />
        </div>
      </section>

      <!-- 行业乖离度排行：表格形式，支持排序筛选 -->
      <BiasTable
        :items="biasItems"
        :date="biasDate"
        :stale="biasStale"
        :loading="biasLoading"
      />

      <!-- 行业拥挤度排行：表格形式，与乖离度并列（不同维度） -->
      <CrowdingTable
        :items="crowdingValidItems"
        :date="crowdingDate"
        :stale="crowdingStale"
        :loading="crowdingLoading"
      />

      <!-- 全部市场温度指标：紧凑表格 -->
      <MetricDetailTable :items="detailMetrics" />
    </div>

    <!-- 底部（页面级页脚，探市 / 温度计 复用） -->
    <PageFooter
      revisit-text="温度计给出的是市场冷热参考，不构成投资建议。可前往探市页查看指数快照与行业机会。"
      :revisit-items="[
        '回看温度计各指标口径，逐项核对计算方式',
        '把当前市场冷热记录下来，做纵向对比',
        '关注公众号获取更多市场温度解读'
      ]"
      :sources="footerSources"
      copyright="© 2026 多多贝 · 让投资更从容"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch } from "vue";
import { useRouter } from "vue-router";
import { ElMessage } from "element-plus";
import VChart from "vue-echarts";
import {
  getTemperatureOverview,
  getTemperatureHistory,
  getMultiItems
} from "@/api/temperature";
import MarketHeader from "@/components/MarketHeader/index.vue";
import PageFooter from "@/components/PageFooter/index.vue";
import TemperatureGaugeCard from "@/components/TemperatureGaugeCard/index.vue";
import SectionHeader from "@/components/SectionHeader/index.vue";
import TemperatureContextCard from "@/components/TemperatureContextCard/index.vue";
import { useTemperatureStore } from "@/store/modules/temperature";
import {
  MARKET_LOGO,
  useMarketHeaderNavs
} from "@/components/MarketHeader/config";
import { buildMarketFooterSources } from "@/components/MarketFooter/config";
import { useAuthState } from "@/composables/useAuthState";
import { getCssVar } from "@/composables/echarts/theme";
import { CORE_SINGLE_SOURCES } from "@/constants/temperature";
import BiasTable from "./components/BiasTable.vue";
import CrowdingTable from "./components/CrowdingTable.vue";
import MetricDetailTable from "./components/MetricDetailTable.vue";

// 登录态感知（温度计为公开数据页 D4，仅用于登录转化引导）
const { isAuthenticated } = useAuthState();
const router = useRouter();

const goAuth = () => {
  router.push("/login");
};

// 温度三色：动态读取全局 token（src/style/colors.css 的 --temp-*），
// 保持与页面其它元素单一来源、视觉一致（design.md 红线：图表颜色用 getComputedStyle 读取）
// 用 computed 实时读取：暗色切换时 CSS 变量变化可正确重读（原模块顶层一次性求值缺陷修复）
function readTempColorVar(name: string): string {
  return getCssVar(name, "#888");
}

const TEMP_COLORS = computed(() => ({
  low: readTempColorVar("--temp-low"),
  mid: readTempColorVar("--temp-mid"),
  high: readTempColorVar("--temp-high")
}));

// 图表渐变需要具体色值：把 CSS 变量读出的 hex 转 rgba（透明度按原视觉保留）。
// 原实现硬编码 rgba(227, 79, 56, ...)（= --color-rise 亮色值），现改为实时读取语义变量，
// 暗色模式（--color-rise: #d45a44）自动适配（design.md 红线：图表颜色禁止硬编码）
function hexToRgba(hex: string, alpha: number): string {
  const m = /^#?([0-9a-f]{6})$/i.exec(hex.trim());
  if (!m) return hex;
  const n = parseInt(m[1], 16);
  return `rgba(${(n >> 16) & 255}, ${(n >> 8) & 255}, ${n & 255}, ${alpha})`;
}

defineOptions({
  name: "TemperaturePage"
});

// ================================================================
// 数据状态
// ================================================================
const loading = ref(false);
const overview = ref<any>(null);
const historyData = ref<{
  dates: string[];
  values: (number | null)[];
  levels?: string[];
}>({ dates: [], values: [] });
const historyDays = ref(90);
const biasItems = ref<any[]>([]);
const biasDate = ref<string>("");
const biasStale = ref(false);
const biasLoading = ref(false);
const chartRef = ref<any>(null);

// 行业拥挤度（独立维度：行业 PB / 全A 中位 PB 历史百分位）
const crowdingItems = ref<any[]>([]);
const crowdingDate = ref<string>("");
const crowdingStale = ref(false);
const crowdingLoading = ref(false);

// ================================================================
// 计算属性
// ================================================================
const updatedAt = computed(() => overview.value?.updated_at || "");

const compositeValue = computed(() => {
  return overview.value?.composites?.composite_temperature?.value ?? null;
});

const compositeLevel = computed(() => {
  return overview.value?.composites?.composite_temperature?.level || "";
});

// 温度解读卡（TemperatureContextCard）所需数据，从 overview 推导
const fearGreedValue = computed<number | null>(() => {
  const fear = overview.value?.singles?.find(
    (s: { source?: string }) => s.source === "jiucaishuo_fear"
  );
  const v = fear?.value;
  return typeof v === "number" ? v : null;
});
const fearGreedLabel = computed(() => {
  const fear = overview.value?.singles?.find(
    (s: { source?: string }) => s.source === "jiucaishuo_fear"
  );
  return fear?.label || "";
});
const tempPeriods = computed(() => {
  const bands = overview.value?.composites?.temperature_bands;
  if (!bands) return [];
  return (["short", "medium", "long"] as const)
    .map(k => bands[k])
    .filter(Boolean)
    .map((b: { name?: string; value?: number }) => ({
      label: b.name || "",
      value: typeof b.value === "number" ? b.value : null
    }));
});

// 核心指标（从 singles 中提取）
const coreMetrics = computed(() => {
  const singles = overview.value?.singles || [];
  const map: Record<string, any> = {};
  singles.forEach((s: any) => {
    map[s.source] = s;
  });

  const result = [];

  // 恐惧贪婪
  const fear = map["jiucaishuo_fear"];
  if (fear) {
    result.push({
      key: "fear",
      title: "恐惧贪婪",
      value: fear.value,
      level: fear.label
    });
  }

  // 股债性价比
  const selfCalc = overview.value?.composites?.self_calc;
  if (selfCalc) {
    result.push({
      key: "self_calc",
      title: "股债性价比",
      value: selfCalc.percent,
      unit: "%",
      level: selfCalc.level
    });
  }

  // 可转债温度
  const cb = map["jisilu_cb"];
  if (cb) {
    result.push({
      key: "cb",
      title: "可转债",
      value: cb.value,
      unit: "°",
      level: cb.label
    });
  }

  // 成交额
  const vol = map["eastmoney_volume"];
  if (vol) {
    result.push({
      key: "volume",
      title: "成交额",
      value: vol.value,
      unit: "亿",
      level: vol.label
    });
  }

  return result;
});

// 全部单值指标（过滤核心指标，按数据分层展示）
const detailMetrics = computed(() => {
  const singles = overview.value?.singles || [];
  return singles.filter((s: any) => !CORE_SINGLE_SOURCES.includes(s.source));
});

// 过滤整组标灰占位（item_code === '__NA__'），仅展示有效行业
const crowdingValidItems = computed(() =>
  (crowdingItems.value || []).filter((i: any) => i.item_code !== "__NA__")
);

// ECharts 配置
const chartOption = computed(() => {
  const dates = historyData.value.dates || [];
  const values = historyData.value.values || [];
  const levels = historyData.value.levels || [];

  // 计算颜色：根据 level 决定（复用 TEMP_COLORS，与全局 token 一致）
  const colors = levels.map(level => {
    if (level === "偏低" || level === "低估") return TEMP_COLORS.value.low;
    if (level === "偏高" || level === "高估") return TEMP_COLORS.value.high;
    return TEMP_COLORS.value.mid;
  });

  return {
    tooltip: {
      trigger: "axis",
      formatter: (params: any) => {
        const p = params[0];
        const idx = p.dataIndex;
        const level = levels[idx] || "";
        return `${p.axisValue}<br/>综合温度: ${p.value}°<br/>等级: ${level}`;
      }
    },
    grid: {
      left: 50,
      right: 20,
      top: 20,
      bottom: 30
    },
    xAxis: {
      type: "category",
      data: dates,
      axisLabel: {
        rotate: 30,
        fontSize: 11
      }
    },
    yAxis: {
      type: "value",
      min: 0,
      max: 100,
      splitLine: {
        lineStyle: { color: "var(--border-light)", type: "dashed" }
      },
      axisLabel: {
        formatter: "{value}°",
        fontSize: 11
      }
    },
    series: [
      {
        name: "综合温度",
        type: "line",
        data: values,
        smooth: true,
        symbol: "circle",
        symbolSize: 6,
        lineStyle: {
          color: "var(--brand-700)",
          width: 2
        },
        areaStyle: {
          color: {
            type: "linear",
            x: 0,
            y: 0,
            x2: 0,
            y2: 1,
            // 涨色渐变：实时读取 --color-rise（原硬编码 rgba(227, 79, 56, ...) 即其亮色值），
            // 暗色模式自动适配，透明度按原视觉保留
            colorStops: [
              {
                offset: 0,
                color: hexToRgba(getCssVar("--color-rise", "#e34f38"), 0.3)
              },
              {
                offset: 1,
                color: hexToRgba(getCssVar("--color-rise", "#e34f38"), 0.05)
              }
            ]
          }
        },
        itemStyle: {
          color: (params: any) => {
            const idx = params.dataIndex;
            return colors[idx] || "var(--brand-700)";
          }
        },
        markLine: {
          silent: true,
          data: [
            {
              yAxis: 70,
              label: {
                formatter: "偏高",
                color: "var(--text-tertiary)",
                fontSize: 11
              }
            },
            {
              yAxis: 40,
              label: {
                formatter: "适中",
                color: "var(--text-tertiary)",
                fontSize: 11
              }
            },
            {
              yAxis: 25,
              label: {
                formatter: "偏低",
                color: "var(--text-tertiary)",
                fontSize: 11
              }
            }
          ],
          lineStyle: {
            color: "var(--border-default)",
            type: "dashed",
            width: 1
          }
        }
      }
    ]
  };
});

// ================================================================
// 方法
// ================================================================
const fetchOverview = async () => {
  loading.value = true;
  try {
    const res = await getTemperatureOverview();
    overview.value = res.data;
  } catch (e) {
    console.error("获取温度概览失败:", e);
    ElMessage.error("获取数据失败");
  } finally {
    loading.value = false;
  }
};

const fetchHistory = async () => {
  try {
    const res = await getTemperatureHistory(historyDays.value);
    historyData.value = res.data;
  } catch (e) {
    console.error("获取历史趋势失败:", e);
  }
};

const fetchBias = async () => {
  biasLoading.value = true;
  try {
    const res = await getMultiItems("bias");
    const data = res.data;
    if (data && data.items) {
      biasItems.value = data.items;
      biasDate.value = data.date || "";
      biasStale.value =
        Boolean(data.stale) || (data.items || []).some((i: any) => i.stale);
    } else {
      biasItems.value = [];
      biasStale.value = false;
    }
  } catch (e) {
    console.error("获取乖离率数据失败:", e);
    biasItems.value = [];
  } finally {
    biasLoading.value = false;
  }
};

const fetchCrowding = async () => {
  crowdingLoading.value = true;
  try {
    const res = await getMultiItems("industry_crowding");
    const data = res.data;
    if (data && data.items) {
      crowdingItems.value = data.items;
      crowdingDate.value = data.date || "";
      crowdingStale.value =
        Boolean(data.stale) || (data.items || []).some((i: any) => i.stale);
    } else {
      crowdingItems.value = [];
      crowdingStale.value = false;
    }
  } catch (e) {
    console.error("获取行业拥挤度数据失败:", e);
    crowdingItems.value = [];
  } finally {
    crowdingLoading.value = false;
  }
};

// ================================================================
// Header / Footer 公共组件数据
// ================================================================
const headerNavs = useMarketHeaderNavs();

const footerSources = buildMarketFooterSources();

// 温度 store：承载综合温度、股债性价比与市场机会清单
const tempStore = useTemperatureStore();

// ================================================================
// 生命周期
// ================================================================
onMounted(async () => {
  await fetchOverview();
  await fetchHistory();
  await fetchBias();
  await fetchCrowding();
  // NOTE: 与 fetchOverview 各自调用一次 getTemperatureOverview，后续可合并为单一数据源
  await tempStore.fetchTemperature();
});

// 当历史天数变化时重新获取
watch(historyDays, () => {
  fetchHistory();
});
</script>

<style lang="scss" scoped>
/* ===== 响应式 ===== */
@media (width <= 960px) {
  .context-grid {
    grid-template-columns: 1fr;
  }
}

@media (width <= 768px) {
  .page-content {
    padding: 16px;
  }
}

.temperature-page {
  min-height: 100vh;
  background: var(--bg-page);
}

/* 页面内容 */
.page-content {
  max-width: 1280px;
  padding: var(--space-standard) 24px 16px;
  margin: 0 auto;
}

/* 未登录引导条（登录转化） */
.auth-banner {
  max-width: 1280px;
  padding: 10px 24px 0;
  margin: 0 auto;

  &__inner {
    display: flex;
    gap: 16px;
    align-items: center;
    justify-content: space-between;
    padding: 10px 18px;
    font-size: 13px;
    color: var(--text-secondary);
    background: var(--bg-card);
    border: 1px solid var(--brand-400);
    border-radius: 10px;
    box-shadow: var(--shadow-raised);
  }
}

/* 仪表盘区域 */
.dashboard-section {
  margin-bottom: 24px;
}

.context-section {
  margin-bottom: 24px;
}

/* 图表区域 */
.chart-section {
  padding: 20px 24px;
  margin-bottom: 24px;
  background: var(--bg-card);
  border: 1px solid var(--border-light);
  border-radius: 12px;
  box-shadow: var(--shadow-raised);
}

.chart-wrapper {
  width: 100%;
  height: 300px;
}

/* 市场机会（temperature store） */
.opportunity-section {
  margin-bottom: 24px;
}

.opportunity-list {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
  gap: var(--space-compact);
}

.opportunity-item {
  padding: 16px 18px;
  background: var(--bg-card);
  border: 1px solid var(--border-light);
  border-left: 3px solid var(--text-tertiary);
  border-radius: 12px;
  box-shadow: var(--shadow-raised);
}

.opportunity-item--safe {
  border-left-color: var(--temp-low);
}

.opportunity-item--danger {
  border-left-color: var(--temp-high);
}

.opportunity-item--normal {
  border-left-color: var(--temp-mid);
}

.opportunity-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
}

.opportunity-name {
  font-weight: 600;
  color: var(--text-primary);
}

.opportunity-tag {
  padding: 2px 8px;
  font-size: 12px;
  color: var(--text-secondary);
  background: var(--bg-subtle);
  border-radius: 999px;
}

.opportunity-item--safe .opportunity-tag {
  color: var(--temp-low);
  background: color-mix(in srgb, var(--temp-low) 18%, transparent);
}

.opportunity-item--danger .opportunity-tag {
  color: var(--temp-high);
  background: color-mix(in srgb, var(--temp-high) 18%, transparent);
}

.opportunity-desc {
  margin: 0;
  font-size: 13px;
  line-height: 1.6;
  color: var(--text-secondary);
}

/* 表格视觉基线由全站统一主题维护（src/style/el-table.css），勿在本页 :deep 覆盖 */

/* ============================================================
   温度解读 + 市场机会（并排）
   ============================================================ */
.context-grid {
  display: grid;
  grid-template-columns: 1.6fr 1fr;
  gap: 16px;
  align-items: stretch;
}

.context-card,
.opportunity-card {
  overflow: hidden;
  background: var(--bg-card);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-raised);
}

.opportunity-card {
  display: flex;
  flex-direction: column;
  padding: 16px;
}

.opportunity-card :deep(.section-header) {
  margin-bottom: 12px;
}

/* stylelint-disable no-duplicate-selectors */

/* 以下 .opportunity-* 选择器与上方「市场机会区块」(1086 行起, grid 平铺布局) 同名,
   但此处用于「市场机会卡片」(flex 纵向布局, 独立配色与间距), 二者是有意差异化的
   两套视觉而非重复定义。通过局部禁用 no-duplicate-selectors 保留此差异,
   切勿合并或重命名, 否则会破坏卡片内的纵向排列与卡片专属样式。 */
.opportunity-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
  overflow-y: auto;
}

.opportunity-item {
  padding: 12px 14px;
  background: var(--bg-subtle);
  border-left: 4px solid var(--border-light);
  border-radius: 10px;
}

.opportunity-item--safe {
  background: color-mix(in srgb, var(--temp-low) 8%, var(--bg-subtle));
  border-left-color: var(--temp-low);
}

.opportunity-item--danger {
  background: color-mix(in srgb, var(--temp-high) 8%, var(--bg-subtle));
  border-left-color: var(--temp-high);
}

.opportunity-item--neutral {
  background: color-mix(in srgb, var(--temp-mid) 8%, var(--bg-subtle));
  border-left-color: var(--temp-mid);
}

.opportunity-head {
  display: flex;
  gap: 8px;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 6px;
}

.opportunity-name {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
}

.opportunity-tag {
  padding: 2px 8px;
  font-size: 11px;
  color: var(--text-secondary);
  white-space: nowrap;
  background: var(--border-light);
  border-radius: 10px;
}

.opportunity-item--safe .opportunity-tag {
  color: var(--temp-low);
  background: color-mix(in srgb, var(--temp-low) 18%, transparent);
}

.opportunity-item--danger .opportunity-tag {
  color: var(--temp-high);
  background: color-mix(in srgb, var(--temp-high) 18%, transparent);
}

.opportunity-desc {
  margin: 0;
  font-size: 13px;
  line-height: 1.5;
  color: var(--text-secondary);
}

/* stylelint-disable-enable no-duplicate-selectors */

/* ============================================================
   温度计页面样式
   ============================================================ */
</style>
