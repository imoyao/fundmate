<!-- frontend/src/views/temperature/index.vue -->
<template>
  <div class="temperature-page">
    <!-- 顶部导航 -->
    <header class="temp-header">
      <div class="header-inner">
        <div class="logo-area">
          <span class="logo">ShowBuy</span>
          <span class="badge">温度计</span>
        </div>
        <div class="nav-actions">
          <el-button link @click="goToExplore">探市</el-button>
          <el-button link @click="goToDashboard">仪表盘</el-button>
          <el-button type="primary" @click="goToWatchlist">自选</el-button>
        </div>
      </div>
    </header>

    <!-- 页面内容 -->
    <div class="page-content" v-loading="loading">
      <!-- 综合仪表盘 -->
      <section class="dashboard-section">
        <div class="dashboard-grid">
          <!-- 综合温度仪表（大） -->
          <div class="gauge-card">
            <div class="gauge-ring">
              <svg width="120" height="120" viewBox="0 0 120 120">
                <circle cx="60" cy="60" r="50" stroke="var(--bg-soft)" stroke-width="8" fill="none"/>
                <circle
                  class="gauge-fill"
                  cx="60"
                  cy="60"
                  r="50"
                  stroke="var(--temp-mid)"
                  stroke-width="8"
                  fill="none"
                  stroke-linecap="round"
                  :stroke-dasharray="314.16"
                  :stroke-dashoffset="314.16 * (1 - (compositeValue ?? 0) / 100)"
                />
              </svg>
              <div class="gauge-value">
                <span class="gauge-number">{{ compositeValue ?? '--' }}</span>
                <span class="gauge-degree">°</span>
              </div>
            </div>
            <div class="gauge-info">
              <div class="gauge-title">综合温度</div>
              <TemperatureLevelBadge :level="compositeLevel" />
              <div class="gauge-desc">基于多源市场数据计算</div>
              <div class="gauge-updated">更新：{{ updatedAt }}</div>
            </div>
          </div>

          <!-- 核心指标卡片 -->
          <div class="metric-card" v-for="metric in coreMetrics" :key="metric.key">
            <div class="metric-title">{{ metric.label }}</div>
            <div class="metric-value">{{ metric.value !== null ? metric.value : '--' }}</div>
            <div class="metric-unit" v-if="metric.unit">{{ metric.unit }}</div>
            <TemperatureLevelBadge :level="metric.labelText" size="sm" />
          </div>
        </div>
      </section>

      <!-- 温度趋势图 -->
      <section class="chart-section">
        <div class="section-header">
          <h3>综合温度趋势</h3>
          <div class="chart-controls">
            <el-radio-group v-model="historyDays" size="small" @change="fetchHistory">
              <el-radio-button :value="30">30天</el-radio-button>
              <el-radio-button :value="90">90天</el-radio-button>
              <el-radio-button :value="180">半年</el-radio-button>
            </el-radio-group>
          </div>
        </div>
        <div class="chart-wrapper">
          <v-chart ref="chartRef" :option="chartOption" :autoresize="true" style="width:100%;height:300px;" />
        </div>
      </section>

      <!-- 全部温度卡片 -->
      <section class="cards-section">
        <div class="section-header">
          <h3>全部市场温度指标</h3>
        </div>
        <div class="cards-grid">
          <div v-for="item in allSingles" :key="item.source" class="temp-card">
            <div class="temp-card-title">{{ item.name }}</div>
            <div class="temp-card-value">{{ item.value !== null ? item.value : '--' }}</div>
            <div class="temp-card-unit" v-if="item.unit">{{ item.unit }}</div>
            <TemperatureLevelBadge :level="item.label" size="sm" />
          </div>
        </div>
      </section>

      <!-- 行业乖离度排行 -->
      <section class="bias-section">
        <div class="section-header">
          <h3>行业乖离度排行</h3>
          <span class="bias-updated">更新：{{ biasDate || '暂无' }}</span>
        </div>
        <el-alert
          v-if="biasStale"
          type="warning"
          show-icon
          :closable="false"
          class="bias-stale-alert"
          title="数据滞后提示"
          description="东财行情接口暂不可用，当前乖离率基于最近一次成功抓取的价格计算（已标记「滞后」），非实时数据，仅供参考。"
        />
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
    </div>

    <!-- 底部 -->
    <footer class="footer-section">
      <div class="footer-inner">
        <div class="footer-legend">
          <span class="legend-item"><span class="legend-dot legend-low"></span>绿=偏低（机会）</span>
          <span class="legend-item"><span class="legend-dot legend-mid"></span>金=适中</span>
          <span class="legend-item"><span class="legend-dot legend-high"></span>红=偏高（谨慎）</span>
          <span class="legend-note">温度色与涨跌色相互独立</span>
        </div>
        <div class="footer-sources">
          <span class="footer-label">数据来源：</span>
          <span class="footer-source">韭圈儿</span>
          <span class="footer-source">集思录</span>
          <span class="footer-source">且慢</span>
          <span class="footer-source">有知有行</span>
          <span class="footer-source">东方财富</span>
          <span class="footer-source">自算·股债性价比</span>
          <span class="footer-source">乖离率(自算)</span>
        </div>
        <div class="footer-disclaimer">
          <span class="footer-disclaimer-text">市场数据仅供参考，不构成投资建议。</span>
        </div>
        <div class="footer-copyright">© 2026 ShowBuy · 让投资更从容</div>
      </div>
    </footer>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch } from "vue";
import { useRouter } from "vue-router";
import { ElMessage } from "element-plus";
import VChart from "vue-echarts";
import { use } from "echarts/core";
import { CanvasRenderer } from "echarts/renderers";
import { LineChart } from "echarts/charts";
import { TitleComponent, TooltipComponent, LegendComponent, GridComponent } from "echarts/components";
import { getTemperatureOverview, getTemperatureHistory, getMultiItems } from "@/api/temperature";
import TemperatureLevelBadge from "@/components/TemperatureLevelBadge/index.vue";

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

const router = useRouter();

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
      label: "恐惧贪婪",
      value: fear.value,
      labelText: fear.label,
    });
  }

  // 股债性价比
  const selfCalc = overview.value?.composites?.self_calc;
  if (selfCalc) {
    result.push({
      key: "self_calc",
      label: "股债性价比",
      value: selfCalc.percent,
      unit: "%",
      labelText: selfCalc.level,
    });
  }

  // 可转债温度
  const cb = map["jisilu_cb"];
  if (cb) {
    result.push({
      key: "cb",
      label: "可转债",
      value: cb.value,
      unit: "%",
      labelText: cb.label,
    });
  }

  // 成交额
  const vol = map["eastmoney_volume"];
  if (vol) {
    result.push({
      key: "volume",
      label: "成交额",
      value: vol.value,
      unit: "亿",
      labelText: vol.label,
    });
  }

  return result;
});

// 全部单值指标
const allSingles = computed(() => {
  return overview.value?.singles || [];
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

// 导航方法
const goToExplore = () => {
  router.push("/explore");
};

const goToDashboard = () => {
  router.push("/welcome");
};

const goToWatchlist = () => {
  router.push("/watchlist");
};

// ================================================================
// 生命周期
// ================================================================
onMounted(async () => {
  await fetchOverview();
  await fetchHistory();
  await fetchBias();
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

/* 顶部导航 */
.temp-header {
  position: sticky;
  top: 0;
  z-index: 100;
  backdrop-filter: blur(12px);
  background: rgba(255, 255, 255, 0.7);
  border-bottom: 1px solid var(--border-light);

  .header-inner {
    max-width: 1280px;
    margin: 0 auto;
    padding: 0 24px;
    height: 64px;
    display: flex;
    align-items: center;
    justify-content: space-between;
  }

  .logo-area {
    display: flex;
    align-items: center;
    gap: 12px;

    .logo {
      font-weight: 700;
      font-size: 18px;
      color: var(--brand-700);
    }

    .badge {
      font-size: 12px;
      color: var(--text-secondary);
      background: var(--bg-soft);
      padding: 2px 10px;
      border-radius: 12px;
    }
  }

  .nav-actions {
    display: flex;
    align-items: center;
    gap: 16px;
  }
}

/* 页面内容 */
.page-content {
  max-width: 1280px;
  margin: 0 auto;
  padding: 24px 24px 16px;
}

/* 仪表盘区域 */
.dashboard-section {
  margin-bottom: 24px;
}

.dashboard-grid {
  display: grid;
  grid-template-columns: 2fr 1fr 1fr 1fr;
  gap: 16px;
}

.gauge-card {
  background: linear-gradient(135deg, var(--bg-card), var(--brand-100));
  border-radius: 16px;
  padding: 24px 28px;
  border: 1px solid var(--brand-400);
  box-shadow: var(--shadow-raised);
  display: flex;
  align-items: center;
  gap: 24px;
}

.gauge-ring {
  position: relative;
  width: 120px;
  height: 120px;
  flex-shrink: 0;
}

.gauge-ring svg {
  width: 100%;
  height: 100%;
  transform: rotate(-90deg);
}

.gauge-fill {
  transition: stroke-dashoffset 0.8s ease, stroke 0.6s ease;
}

.gauge-value {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 2px;
}

.gauge-number {
  font-size: 32px;
  font-weight: 700;
  color: var(--text-primary);
  font-family: var(--font-mono);
  font-variant-numeric: tabular-nums;
  line-height: 1;
}

.gauge-degree {
  font-size: 16px;
  font-weight: 500;
  color: var(--text-secondary);
}

.gauge-info {
  flex: 1;
}

.gauge-title {
  font-size: 18px;
  font-weight: 600;
  color: var(--text-primary);
}

.gauge-desc {
  font-size: 13px;
  color: var(--text-tertiary);
  margin-top: 4px;
}

.gauge-updated {
  font-size: 12px;
  color: var(--text-tertiary);
  margin-top: 2px;
}

.metric-card {
  background: var(--bg-card);
  border-radius: 12px;
  padding: 16px 18px;
  border: 1px solid var(--border-light);
  box-shadow: var(--shadow-raised);
  display: flex;
  flex-direction: column;
  justify-content: center;
}

.metric-title {
  font-size: 13px;
  color: var(--text-tertiary);
  margin-bottom: 4px;
}

.metric-value {
  font-size: 28px;
  font-weight: 700;
  color: var(--text-primary);
  font-family: var(--font-mono);
  font-variant-numeric: tabular-nums;
  line-height: 1.2;
}

.metric-unit {
  font-size: 13px;
  color: var(--text-tertiary);
  margin-left: 2px;
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

.section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
  flex-wrap: wrap;
  gap: 12px;

  h3 {
    font-size: 16px;
    font-weight: 600;
    color: var(--text-primary);
    margin: 0;
  }

  .chart-controls {
    display: flex;
    gap: 8px;
  }
}

.chart-wrapper {
  width: 100%;
  height: 300px;
}

/* 全部温度卡片 */
.cards-section {
  margin-bottom: 24px;
}

.cards-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
  gap: 12px;
}

.temp-card {
  background: var(--bg-card);
  border-radius: 10px;
  padding: 14px 16px;
  border: 1px solid var(--border-light);
  box-shadow: var(--shadow-raised);

  .temp-card-title {
    font-size: 12px;
    color: var(--text-tertiary);
    margin-bottom: 4px;
  }

  .temp-card-value {
    font-size: 22px;
    font-weight: 700;
    color: var(--text-primary);
    font-family: var(--font-mono);
    font-variant-numeric: tabular-nums;
    display: inline;
  }

  .temp-card-unit {
    font-size: 13px;
    color: var(--text-tertiary);
    margin-left: 2px;
  }
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

.bias-updated {
  font-size: 12px;
  color: var(--text-tertiary);
}

.bias-stale-alert {
  margin-bottom: 12px;
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

/* 底部 */
.footer-section {
  max-width: 1280px;
  margin: 0 auto;
  padding: 16px 24px 32px;
  border-top: 1px solid var(--border-light);
}

.footer-inner {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.footer-legend {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px 16px;
  font-size: 12px;
  color: var(--text-secondary);
}

.legend-item {
  display: inline-flex;
  align-items: center;
}

.legend-dot {
  display: inline-block;
  width: 8px;
  height: 8px;
  border-radius: 50%;
  margin-right: 5px;
}
.legend-low { background: var(--temp-low); }
.legend-mid { background: var(--temp-mid); }
.legend-high { background: var(--temp-high); }

.legend-note {
  color: var(--text-tertiary);
  margin-left: 4px;
}

.footer-sources {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 4px 12px;
}

.footer-label {
  font-size: 12px;
  color: var(--text-tertiary);
  font-weight: 500;
}

.footer-source {
  font-size: 12px;
  color: var(--text-secondary);

  &::before {
    content: "·";
    margin-right: 8px;
    color: var(--text-tertiary);
  }
  &:first-of-type::before {
    display: none;
  }
}

.footer-disclaimer-text {
  font-size: 11px;
  color: var(--text-tertiary);
  line-height: 1.6;
}

.footer-copyright {
  font-size: 11px;
  color: var(--text-disabled);
}

/* ===== 响应式 ===== */
@media (max-width: 1024px) {
  .dashboard-grid {
    grid-template-columns: 1fr 1fr;
  }
  .gauge-card {
    grid-column: span 2;
  }
}

@media (max-width: 768px) {
  .dashboard-grid {
    grid-template-columns: 1fr;
  }
  .gauge-card {
    grid-column: span 1;
    flex-direction: column;
    align-items: center;
    text-align: center;
    padding: 20px;
  }
  .gauge-ring {
    width: 100px;
    height: 100px;
  }
  .gauge-number {
    font-size: 28px;
  }
  .cards-grid {
    grid-template-columns: repeat(2, 1fr);
  }
  .section-header {
    flex-direction: column;
    align-items: flex-start;
  }
  .header-inner {
    flex-wrap: wrap;
    height: auto;
    padding: 12px 16px;
    gap: 8px;
  }
}

@media (max-width: 480px) {
  .cards-grid {
    grid-template-columns: 1fr;
  }
  .metric-card {
    padding: 12px 14px;
  }
  .metric-value {
    font-size: 24px;
  }
  .gauge-number {
    font-size: 24px;
  }
}
</style>
