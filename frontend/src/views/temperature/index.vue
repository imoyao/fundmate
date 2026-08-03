<!-- frontend/src/views/temperature/index.vue -->
<template>
  <div class="temperature-page">
    <!-- 顶部导航（公共组件，与探市完全一致） -->
    <MarketHeader
      :logo="MARKET_LOGO"
      badge="温度计"
      :navs="headerNavs"
    />

    <!-- 页面内容 -->
    <div class="page-content" v-loading="loading">
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

      <!-- 温度解读：承接仪表卡拆出的文字信息（恐贪 / 短中长期温度），与圆环卡配套 -->
      <section class="context-section">
        <TemperatureContextCard
          :temperature="compositeValue"
          :fear-greed="fearGreedValue"
          :fear-greed-label="fearGreedLabel"
          :periods="tempPeriods"
          caption="综合 6 个市场指标与市场情绪推导"
        />
      </section>

      <!-- 温度趋势图 -->
      <section class="chart-section">
        <SectionHeader title="综合温度趋势">
          <template #action>
            <el-radio-group v-model="historyDays" size="small" @change="fetchHistory">
              <el-radio-button :value="30">30天</el-radio-button>
              <el-radio-button :value="90">90天</el-radio-button>
              <el-radio-button :value="180">半年</el-radio-button>
            </el-radio-group>
          </template>
        </SectionHeader>
        <div class="chart-wrapper">
          <v-chart ref="chartRef" :option="chartOption" :autoresize="true" style="width:100%;height:300px;" />
        </div>
      </section>

      <!-- 全部温度卡片（过滤已在顶部展示的核心指标，避免信息重复） -->
      <section class="cards-section">
        <SectionHeader title="全部市场温度指标" />
        <MetricGrid>
          <MetricCard
            v-for="item in detailMetrics"
            :key="item.source"
            :title="item.name"
            :value="item.value"
            :unit="item.unit"
            :level="item.label"
          />
        </MetricGrid>
      </section>

      <!-- 行业乖离度排行 -->
      <section class="bias-section">
        <SectionHeader title="行业乖离度排行">
          <template #action>
            <span class="bias-updated">更新：{{ biasDate || '暂无' }}</span>
            <el-tooltip
              v-if="biasStale"
              content="东财行情接口暂不可用，当前乖离率基于最近一次成功抓取的价格计算，非实时数据，仅供参考。"
              placement="top"
            >
              <span class="bias-stale-pill">数据滞后</span>
            </el-tooltip>
          </template>
        </SectionHeader>
        <el-table :data="biasItems" border style="width:100%" v-loading="biasLoading" max-height="400">
          <el-table-column prop="item_name" label="行业" min-width="100">
            <template #default="{ row }">
              <span>{{ row.item_name }}</span>
              <el-tag v-if="row.stale" size="small" type="warning" effect="plain" class="bias-stale-tag">滞后</el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="data.bias" label="乖离率" width="120" align="right">
            <template #default="{ row }">
              <span :style="{ color: row.data.bias > 5 ? 'var(--temp-high)' : row.data.bias < -5 ? 'var(--temp-low)' : 'var(--text-secondary)' }">
                {{ row.data.bias !== undefined ? row.data.bias.toFixed(2) : '--' }}%
              </span>
            </template>
          </el-table-column>
          <el-table-column prop="data.label" label="信号" width="120" align="center">
            <template #default="{ row }">
              <el-tag :type="row.data.label === '高位区(绿卖)' ? 'danger' : row.data.label === '低位区(红买)' ? 'success' : 'info'" size="small">
                {{ row.data.label || '中性' }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="data.position" label="波段位置" width="120" align="right">
            <template #default="{ row }">
              <span>{{ row.data.position !== undefined ? row.data.position.toFixed(1) : '--' }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="data.close" label="收盘价" width="120" align="right">
            <template #default="{ row }">
              <span>{{ row.data.close !== undefined ? row.data.close.toFixed(2) : '--' }}</span>
            </template>
          </el-table-column>
        </el-table>
        <div v-if="!biasItems.length" class="empty-state">暂无乖离率数据</div>
      </section>

      <!-- 市场机会（来自 temperature store，由综合温度与股债性价比推导） -->
      <section v-if="tempStore.opportunityList.length" class="opportunity-section">
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
              <span class="opportunity-tag">{{ op.tone === 'safe' ? '机会' : op.tone === 'danger' ? '风险' : '中性' }}</span>
            </div>
            <p class="opportunity-desc">{{ op.desc }}</p>
          </div>
        </div>
      </section>
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
      copyright="© 2026 多倍贝 · 让投资更从容"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch } from "vue";
import { ElMessage } from "element-plus";
import VChart from "vue-echarts";
import { use } from "echarts/core";
import { CanvasRenderer } from "echarts/renderers";
import { LineChart } from "echarts/charts";
import { TitleComponent, TooltipComponent, LegendComponent, GridComponent } from "echarts/components";
import { getTemperatureOverview, getTemperatureHistory, getMultiItems } from "@/api/temperature";
import MarketHeader from "@/components/MarketHeader/index.vue";
import PageFooter from "@/components/PageFooter/index.vue";
import TemperatureGaugeCard from "@/components/TemperatureGaugeCard/index.vue";
import MetricCard from "@/components/MetricCard/index.vue";
import MetricGrid from "@/components/MetricGrid/index.vue";
import SectionHeader from "@/components/SectionHeader/index.vue";
import TemperatureContextCard from "@/components/TemperatureContextCard/index.vue";
import { useTemperatureStore } from "@/store/modules/temperature";
import { MARKET_LOGO, useMarketHeaderNavs } from "@/components/MarketHeader/config";
import { buildMarketFooterSources } from "@/components/MarketFooter/config";

// 注册 ECharts 组件
use([CanvasRenderer, LineChart, TitleComponent, TooltipComponent, LegendComponent, GridComponent]);

// 温度三色：动态读取全局 token（src/style/colors.css 的 --temp-*），
// 保持与页面其它元素单一来源、视觉一致（design.md 红线：图表颜色用 getComputedStyle 读取）
function readTempColorVar(name: string): string {
  if (typeof window === "undefined") return "#888";
  const value = getComputedStyle(document.documentElement)
    .getPropertyValue(name)
    .trim();
  return value || "#888";
}

const TEMP_COLORS = {
  low: readTempColorVar("--temp-low"),
  mid: readTempColorVar("--temp-mid"),
  high: readTempColorVar("--temp-high")
};

defineOptions({
  name: "TemperaturePage"
});

// ================================================================
// 数据状态
// ================================================================
const loading = ref(false);
const overview = ref<any>(null);
const historyData = ref<{ dates: string[]; values: (number | null)[]; levels?: string[] }>({ dates: [], values: [] });
const historyDays = ref(90);
const biasItems = ref<any[]>([]);
const biasDate = ref<string>("");
const biasStale = ref(false);
const biasLoading = ref(false);
const chartRef = ref<any>(null);

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
  singles.forEach((s: any) => { map[s.source] = s; });

  const result = [];

  // 恐惧贪婪
  const fear = map["jiucaishuo_fear"];
  if (fear) {
    result.push({
      key: "fear",
      title: "恐惧贪婪",
      value: fear.value,
      level: fear.label,
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
      level: selfCalc.level,
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
      level: cb.label,
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
      level: vol.label,
    });
  }

  return result;
});

// 已在顶部核心指标展示过的 singles source，底部「全部市场温度指标」区域过滤掉，避免同页信息重复
const CORE_SINGLE_SOURCES = ["jiucaishuo_fear", "jisilu_cb", "eastmoney_volume"];

// 全部单值指标（过滤核心指标，按数据分层展示）
const detailMetrics = computed(() => {
  const singles = overview.value?.singles || [];
  return singles.filter((s: any) => !CORE_SINGLE_SOURCES.includes(s.source));
});

// ECharts 配置
const chartOption = computed(() => {
  const dates = historyData.value.dates || [];
  const values = historyData.value.values || [];
  const levels = historyData.value.levels || [];

  // 计算颜色：根据 level 决定（复用 TEMP_COLORS，与全局 token 一致）
  const colors = levels.map((level) => {
    if (level === "偏低" || level === "低估") return TEMP_COLORS.low;
    if (level === "偏高" || level === "高估") return TEMP_COLORS.high;
    return TEMP_COLORS.mid;
  });

  return {
    tooltip: {
      trigger: "axis",
      formatter: (params: any) => {
        const p = params[0];
        const idx = p.dataIndex;
        const level = levels[idx] || "";
        return `${p.axisValue}<br/>综合温度: ${p.value}°<br/>等级: ${level}`;
      },
    },
    grid: {
      left: 50,
      right: 20,
      top: 20,
      bottom: 30,
    },
    xAxis: {
      type: "category",
      data: dates,
      axisLabel: {
        rotate: 30,
        fontSize: 11,
      },
    },
    yAxis: {
      type: "value",
      min: 0,
      max: 100,
      splitLine: {
        lineStyle: { color: "var(--border-light)", type: "dashed" },
      },
      axisLabel: {
        formatter: "{value}°",
        fontSize: 11,
      },
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
          width: 2,
        },
        areaStyle: {
          color: {
            type: "linear",
            x: 0,
            y: 0,
            x2: 0,
            y2: 1,
            colorStops: [
              { offset: 0, color: "rgba(227, 79, 56, 0.3)" },
              { offset: 1, color: "rgba(227, 79, 56, 0.05)" },
            ],
          },
        },
        itemStyle: {
          color: (params: any) => {
            const idx = params.dataIndex;
            return colors[idx] || "var(--brand-700)";
          },
        },
        markLine: {
          silent: true,
          data: [
            { yAxis: 70, label: { formatter: "偏高", color: "var(--text-tertiary)", fontSize: 11 } },
            { yAxis: 40, label: { formatter: "适中", color: "var(--text-tertiary)", fontSize: 11 } },
            { yAxis: 25, label: { formatter: "偏低", color: "var(--text-tertiary)", fontSize: 11 } },
          ],
          lineStyle: {
            color: "var(--border-default)",
            type: "dashed",
            width: 1,
          },
        },
      },
    ],
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
  // NOTE: 与 fetchOverview 各自调用一次 getTemperatureOverview，后续可合并为单一数据源
  await tempStore.fetchTemperature();
});

// 当历史天数变化时重新获取
watch(historyDays, () => {
  fetchHistory();
});
</script>

<style lang="scss" scoped>
/* ============================================================
   温度计页面样式
   ============================================================ */
.temperature-page {
  min-height: 100vh;
  background: var(--bg-page);
}

/* 页面内容 */
.page-content {
  max-width: 1280px;
  margin: 0 auto;
  padding: var(--space-standard) 24px 16px;
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
  background: var(--bg-card);
  border-radius: 12px;
  padding: 20px 24px;
  border: 1px solid var(--border-light);
  box-shadow: var(--shadow-raised);
  margin-bottom: 24px;
}

.chart-wrapper {
  width: 100%;
  height: 300px;
}

/* 全部温度卡片 */
.cards-section {
  margin-bottom: 24px;
}

/* 乖离度排行 */
.bias-section {
  background: var(--bg-card);
  border-radius: 12px;
  padding: 20px 24px;
  border: 1px solid var(--border-light);
  box-shadow: var(--shadow-raised);
  margin-bottom: 24px;
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
  background: var(--bg-card);
  border-radius: 12px;
  padding: 16px 18px;
  border: 1px solid var(--border-light);
  box-shadow: var(--shadow-raised);
  border-left: 3px solid var(--text-tertiary);
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
  font-size: 12px;
  padding: 2px 8px;
  border-radius: 999px;
  background: var(--bg-subtle);
  color: var(--text-secondary);
}

.opportunity-item--safe .opportunity-tag {
  background: color-mix(in srgb, var(--temp-low) 18%, transparent);
  color: var(--temp-low);
}

.opportunity-item--danger .opportunity-tag {
  background: color-mix(in srgb, var(--temp-high) 18%, transparent);
  color: var(--temp-high);
}

.opportunity-desc {
  margin: 0;
  font-size: 13px;
  line-height: 1.6;
  color: var(--text-secondary);
}

.bias-updated {
  font-size: 12px;
  color: var(--text-tertiary);
}

.bias-stale-pill {
  margin-left: 8px;
  padding: 2px 8px;
  border-radius: 6px 6px 6px 0;
  font-size: 11px;
  font-weight: 500;
  line-height: 1.4;
  color: var(--color-warning, #d97706);
  background: color-mix(in srgb, var(--color-warning, #d97706) 12%, transparent);
  border: 1px solid color-mix(in srgb, var(--color-warning, #d97706) 35%, transparent);
  cursor: help;
  white-space: nowrap;
}

.bias-stale-tag {
  margin-left: 6px;
  vertical-align: middle;
}

.empty-state {
  padding: 40px 0;
  text-align: center;
  color: var(--text-tertiary);
  font-size: 14px;
}

/* ===== 响应式 ===== */
@media (max-width: 768px) {
  .header-inner {
    flex-wrap: wrap;
    height: auto;
    padding: 12px 16px;
    gap: 8px;
  }
}
</style>
