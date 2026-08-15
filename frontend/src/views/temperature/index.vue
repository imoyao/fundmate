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
      <section class="bias-section">
        <SectionHeader title="行业乖离度排行">
          <template #action>
            <span class="bias-updated">更新：{{ biasDate || "暂无" }}</span>
            <el-tooltip
              v-if="biasStale"
              content="东财行情接口暂不可用，当前乖离率基于最近一次成功抓取的价格计算，非实时数据，仅供参考。"
              placement="top"
            >
              <span class="bias-stale-pill">数据滞后</span>
            </el-tooltip>
          </template>
        </SectionHeader>
        <el-table
          v-loading="biasLoading"
          :data="biasItems"
          border
          style="width: 100%"
          max-height="520"
          :default-sort="{ prop: 'data.bias', order: 'ascending' }"
        >
          <el-table-column
            prop="item_name"
            label="行业"
            min-width="140"
            sortable
          >
            <template #default="{ row }">
              <span>{{ row.item_name || row.name }}</span>
              <el-tag
                v-if="row.stale"
                size="small"
                type="warning"
                effect="plain"
                class="bias-stale-tag"
                >滞后</el-tag
              >
            </template>
          </el-table-column>
          <el-table-column
            prop="data.bias"
            label="乖离率"
            width="130"
            align="right"
            sortable
          >
            <template #default="{ row }">
              <span :class="biasColorClass(row.data?.bias ?? row.logbias)">
                {{ formatValue(row.data?.bias ?? row.logbias) }}%
              </span>
            </template>
          </el-table-column>
          <el-table-column label="偏离度" min-width="200">
            <template #default="{ row }">
              <div class="bias-cell-bar">
                <div class="bias-cell-track">
                  <div class="bias-cell-zero" />
                  <div
                    class="bias-cell-fill"
                    :class="biasColorClass(row.data?.bias ?? row.logbias)"
                    :style="biasBarStyle(row.data?.bias ?? row.logbias)"
                  />
                </div>
                <div class="bias-cell-labels">
                  <span>低位区</span>
                  <span>高位区</span>
                </div>
              </div>
            </template>
          </el-table-column>
          <el-table-column
            prop="data.position"
            label="波段位置"
            width="120"
            align="right"
            sortable
          >
            <template #default="{ row }">
              <span>{{
                row.data?.position !== undefined
                  ? row.data.position.toFixed(1)
                  : "--"
              }}</span>
            </template>
          </el-table-column>
          <el-table-column
            prop="data.label"
            label="信号"
            width="130"
            align="center"
          >
            <template #default="{ row }">
              <el-tag
                :type="
                  (row.data?.label || row.label) === '高位区(绿卖)'
                    ? 'danger'
                    : (row.data?.label || row.label) === '低位区(红买)'
                      ? 'success'
                      : 'info'
                "
                size="small"
                effect="dark"
              >
                {{ row.data?.label || row.label || "中性" }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column
            prop="data.close"
            label="收盘价"
            width="120"
            align="right"
            sortable
          >
            <template #default="{ row }">
              <span>{{ formatValue(row.data?.close ?? row.close) }}</span>
            </template>
          </el-table-column>
        </el-table>
        <div v-if="!biasItems.length && !biasLoading" class="empty-state">
          暂无乖离率数据
        </div>
      </section>

      <!-- 行业拥挤度排行：表格形式，与乖离度并列（不同维度） -->
      <section class="crowding-section">
        <SectionHeader title="行业拥挤度排行">
          <template #action>
            <span class="bias-updated">更新：{{ crowdingDate || "暂无" }}</span>
            <el-tooltip
              v-if="crowdingStale"
              content="legulegu 数据源暂不可用，当前为最近一次成功计算的结果或占位提示，非实时数据，仅供参考。"
              placement="top"
            >
              <span class="bias-stale-pill">数据滞后</span>
            </el-tooltip>
          </template>
        </SectionHeader>
        <el-table
          v-loading="crowdingLoading"
          :data="crowdingValidItems"
          border
          style="width: 100%"
          max-height="520"
          :default-sort="{ prop: 'data.crowding_pct', order: 'ascending' }"
        >
          <el-table-column
            prop="item_name"
            label="行业"
            min-width="140"
            sortable
          >
            <template #default="{ row }">
              <span>{{ row.item_name }}</span>
              <el-tag
                v-if="row.stale"
                size="small"
                type="warning"
                effect="plain"
                class="bias-stale-tag"
                >滞后</el-tag
              >
            </template>
          </el-table-column>
          <el-table-column
            prop="data.crowding_pct"
            label="拥挤度"
            width="220"
            align="right"
            sortable
          >
            <template #default="{ row }">
              <div class="crowding-cell">
                <span
                  class="crowding-value"
                  :class="crowdingColorClass(row.data?.crowding_pct)"
                >
                  {{
                    row.data?.crowding_pct != null
                      ? row.data.crowding_pct.toFixed(1) + "%"
                      : "--"
                  }}
                </span>
                <div class="crowding-cell-bar">
                  <div class="crowding-cell-track">
                    <div
                      class="crowding-cell-fill"
                      :class="crowdingColorClass(row.data?.crowding_pct)"
                      :style="crowdingBarStyle(row.data?.crowding_pct)"
                    />
                  </div>
                </div>
              </div>
            </template>
          </el-table-column>
          <!-- 成交额占比（历史百分位）：复用拥挤度配色与进度条语义，数据源降级为 null 时显示 -- -->
          <el-table-column
            prop="data.amount_pct_rank"
            label="成交额占比"
            width="220"
            align="right"
            sortable
          >
            <template #default="{ row }">
              <div class="crowding-cell">
                <span
                  class="crowding-value"
                  :class="crowdingColorClass(row.data?.amount_pct_rank)"
                >
                  {{
                    row.data?.amount_pct_rank != null
                      ? row.data.amount_pct_rank.toFixed(1) + "%"
                      : "--"
                  }}
                </span>
                <div class="crowding-cell-bar">
                  <div class="crowding-cell-track">
                    <div
                      class="crowding-cell-fill"
                      :class="crowdingColorClass(row.data?.amount_pct_rank)"
                      :style="crowdingBarStyle(row.data?.amount_pct_rank)"
                    />
                  </div>
                </div>
              </div>
            </template>
          </el-table-column>
          <!-- 换手率（历史百分位）：语义与拥挤度一致，越高越热（红），越低越冷（绿） -->
          <el-table-column
            prop="data.turnover_rank"
            label="换手率"
            width="220"
            align="right"
            sortable
          >
            <template #default="{ row }">
              <div class="crowding-cell">
                <span
                  class="crowding-value"
                  :class="crowdingColorClass(row.data?.turnover_rank)"
                >
                  {{
                    row.data?.turnover_rank != null
                      ? row.data.turnover_rank.toFixed(1) + "%"
                      : "--"
                  }}
                </span>
                <div class="crowding-cell-bar">
                  <div class="crowding-cell-track">
                    <div
                      class="crowding-cell-fill"
                      :class="crowdingColorClass(row.data?.turnover_rank)"
                      :style="crowdingBarStyle(row.data?.turnover_rank)"
                    />
                  </div>
                </div>
              </div>
            </template>
          </el-table-column>
          <el-table-column
            prop="data.multiple"
            label="PB倍数"
            width="110"
            align="right"
            sortable
          >
            <template #default="{ row }">
              <span>{{
                row.data?.multiple != null ? row.data.multiple.toFixed(2) : "--"
              }}</span>
            </template>
          </el-table-column>
          <el-table-column
            prop="data.ind_pb"
            label="行业PB"
            width="110"
            align="right"
            sortable
          >
            <template #default="{ row }">
              <span>{{
                row.data?.ind_pb != null ? row.data.ind_pb.toFixed(2) : "--"
              }}</span>
            </template>
          </el-table-column>
          <el-table-column
            prop="data.mkt_pb"
            label="全A中位PB"
            width="120"
            align="right"
            sortable
          >
            <template #default="{ row }">
              <span>{{
                row.data?.mkt_pb != null ? row.data.mkt_pb.toFixed(2) : "--"
              }}</span>
            </template>
          </el-table-column>
          <el-table-column label="说明" min-width="140">
            <template #default="{ row }">
              <span v-if="!row.data?.hist_ok" class="crowding-note-tag"
                >分位待历史积累</span
              >
              <span v-else class="crowding-note">{{
                row.data?.note || ""
              }}</span>
            </template>
          </el-table-column>
        </el-table>
        <div
          v-if="!crowdingValidItems.length && !crowdingLoading"
          class="empty-state"
        >
          行业拥挤度数据暂不可用（legulegu
          数据源受限，本机运行一次建立历史缓存后自动恢复）。
        </div>
      </section>

      <!-- 全部市场温度指标：紧凑表格 -->
      <section class="cards-section">
        <SectionHeader title="全部市场温度指标" />
        <div class="metric-table">
          <div class="metric-table-head">
            <span class="col-name">指标</span>
            <span class="col-source">来源</span>
            <span class="col-value">数值</span>
            <span class="col-label">等级</span>
          </div>
          <div
            v-for="item in detailMetrics"
            :key="`${item.source}-${item.name}`"
            class="metric-table-row"
            :class="{ stale: item.stale }"
          >
            <div class="col-name">
              <span class="metric-name-text">{{ item.name }}</span>
              <el-tooltip v-if="item.note" :content="item.note" placement="top">
                <el-icon class="info-icon"><Info-Filled /></el-icon>
              </el-tooltip>
            </div>
            <div class="col-source">
              <span class="source-tag">{{ displaySource(item.source) }}</span>
            </div>
            <div
              class="col-value"
              :class="valueColorClass(item.value, item.label)"
            >
              {{ formatValue(item.value) }}{{ item.unit || "" }}
            </div>
            <div class="col-label">
              <TemperatureLevelBadge :level="item.label" size="sm" />
            </div>
          </div>
          <div v-if="!detailMetrics.length" class="empty-state">
            暂无更多指标
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
      copyright="© 2026 多多贝 · 让投资更从容"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch } from "vue";
import { useRouter } from "vue-router";
import { ElMessage } from "element-plus";
import { InfoFilled } from "@element-plus/icons-vue";
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
import TemperatureLevelBadge from "@/components/TemperatureLevelBadge/index.vue";
import { useTemperatureStore } from "@/store/modules/temperature";
import {
  MARKET_LOGO,
  useMarketHeaderNavs
} from "@/components/MarketHeader/config";
import { buildMarketFooterSources } from "@/components/MarketFooter/config";
import { useAuthState } from "@/composables/useAuthState";

// 登录态感知（温度计为公开数据页 D4，仅用于登录转化引导）
const { isAuthenticated } = useAuthState();
const router = useRouter();

const goAuth = () => {
  router.push("/login");
};

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

// 已在顶部核心指标展示过的 singles source，底部「全部市场温度指标」区域过滤掉，避免同页信息重复
const CORE_SINGLE_SOURCES = [
  "jiucaishuo_fear",
  "jisilu_cb",
  "eastmoney_volume"
];

// 全部单值指标（过滤核心指标，按数据分层展示）
const detailMetrics = computed(() => {
  const singles = overview.value?.singles || [];
  return singles.filter((s: any) => !CORE_SINGLE_SOURCES.includes(s.source));
});

// 过滤整组标灰占位（item_code === '__NA__'），仅展示有效行业
const crowdingValidItems = computed(() =>
  (crowdingItems.value || []).filter((i: any) => i.item_code !== "__NA__")
);

// ================================================================
// 展示辅助函数
// ================================================================
function clamp(n: number, min: number, max: number): number {
  return Math.max(min, Math.min(max, n));
}

function formatValue(v: number | null | undefined): string {
  if (v === null || v === undefined) return "--";
  if (Math.abs(v) >= 10000) return v.toFixed(0);
  if (Math.abs(v) >= 100) return v.toFixed(1);
  return v.toFixed(2);
}

function biasColorClass(bias: number): string {
  if (bias >= 15) return "bias-extreme-high";
  if (bias >= 5) return "bias-high";
  if (bias <= -15) return "bias-extreme-low";
  if (bias <= -5) return "bias-low";
  return "bias-neutral";
}

function biasBarStyle(bias: number) {
  // 以 0 为中心，可视范围 [-20, 20] 映射到进度条
  const range = 20;
  const clamped = clamp(bias, -range, range);
  const percent = (Math.abs(clamped) / range) * 50; // 半边最多 50%
  const isPositive = clamped >= 0;
  return {
    width: `${percent}%`,
    left: isPositive ? "50%" : `${50 - percent}%`
  };
}

function valueColorClass(value: number | null, label?: string): string {
  if (value === null || value === undefined) return "";
  const text = String(label || "");
  if (
    text.includes("低") ||
    text.includes("冷") ||
    text.includes("恐惧") ||
    text.includes("低估")
  )
    return "val-low";
  if (
    text.includes("高") ||
    text.includes("热") ||
    text.includes("贪婪") ||
    text.includes("高估")
  )
    return "val-high";
  return "val-mid";
}

// 行业拥挤度档位配色：低=冷(蓝/绿)、中=中性、高=热(红)；复用 val-* 颜色令牌
function crowdingColorClass(pct: number | null | undefined): string {
  if (pct === null || pct === undefined) return "";
  if (pct < 30) return "val-low";
  if (pct > 70) return "val-high";
  return "val-mid";
}

// 拥挤度百分位 0-100 映射到进度条宽度
function crowdingBarStyle(pct: number | null | undefined) {
  const v = pct === null || pct === undefined ? 0 : clamp(pct, 0, 100);
  return { width: `${v}%` };
}

// 来源标识 -> 中文显示名（避免页面出现拼音/英文）
const SOURCE_DISPLAY_NAMES: Record<string, string> = {
  jiucaishuo_fear: "韭圈儿",
  jiucaishuo_medium: "韭圈儿",
  qieman: "且慢",
  youzhiyouxing: "有知有行",
  jisilu_cb: "集思录",
  jisilu_indicator: "集思录",
  eastmoney_volume: "东财",
  eastmoney: "东财",
  self_calc: "自算",
  fulai: "富来智投",
  default: ""
};

function displaySource(source?: string): string {
  if (!source) return "";
  return SOURCE_DISPLAY_NAMES[source] || source;
}

// ECharts 配置
const chartOption = computed(() => {
  const dates = historyData.value.dates || [];
  const values = historyData.value.values || [];
  const levels = historyData.value.levels || [];

  // 计算颜色：根据 level 决定（复用 TEMP_COLORS，与全局 token 一致）
  const colors = levels.map(level => {
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
            colorStops: [
              { offset: 0, color: "rgba(227, 79, 56, 0.3)" },
              { offset: 1, color: "rgba(227, 79, 56, 0.05)" }
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

  .metric-table-head,
  .metric-table-row {
    grid-template-columns: 2fr 80px 80px;
    gap: 8px;
    padding: 10px 12px;
  }

  .metric-table-head .col-source,
  .metric-table-row .col-source {
    display: none;
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

/* 全部温度卡片 */
.cards-section {
  margin-bottom: 24px;
}

/* 乖离度排行 */
.bias-section {
  padding: 20px 24px;
  margin-bottom: 24px;
  background: var(--bg-card);
  border: 1px solid var(--border-light);
  border-radius: 12px;
  box-shadow: var(--shadow-raised);
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

.bias-updated {
  font-size: 12px;
  color: var(--text-tertiary);
}

.bias-stale-pill {
  padding: 2px 8px;
  margin-left: 8px;
  font-size: 11px;
  font-weight: 500;
  line-height: 1.4;
  color: var(--color-warning, #d97706);
  white-space: nowrap;
  cursor: help;
  background: color-mix(
    in srgb,
    var(--color-warning, #d97706) 12%,
    transparent
  );
  border: 1px solid
    color-mix(in srgb, var(--color-warning, #d97706) 35%, transparent);
  border-radius: 6px 6px 6px 0;
}

.bias-stale-tag {
  margin-left: 6px;
  vertical-align: middle;
}

.empty-state {
  padding: 40px 0;
  font-size: 14px;
  color: var(--text-tertiary);
  text-align: center;
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
   乖离率表格单元格内颜色条
   ============================================================ */
.bias-cell-bar {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.bias-cell-track {
  position: relative;
  height: 8px;
  overflow: hidden;
  background: var(--border-default);
  border-radius: 4px;
}

.bias-cell-zero {
  position: absolute;
  top: 0;
  bottom: 0;
  left: 50%;
  z-index: 1;
  width: 2px;
  background: var(--text-tertiary);
  transform: translateX(-50%);
}

.bias-cell-fill {
  position: absolute;
  top: 0;
  height: 100%;
  border-radius: 4px;
  transition:
    width 0.4s ease,
    left 0.4s ease;
}

.bias-cell-fill.bias-low,
.bias-cell-fill.bias-extreme-low {
  background: var(--temp-low);
}

.bias-cell-fill.bias-high,
.bias-cell-fill.bias-extreme-high {
  background: var(--temp-high);
}

.bias-cell-fill.bias-neutral {
  background: var(--temp-mid);
}

.bias-cell-labels {
  display: flex;
  justify-content: space-between;
  font-size: 10px;
  color: var(--text-tertiary);
}

/* ============================================================
   行业拥挤度排行表格
   ============================================================ */
.crowding-section {
  padding: 20px 24px;
  margin-bottom: 24px;
  background: var(--bg-card);
  border: 1px solid var(--border-light);
  border-radius: 12px;
  box-shadow: var(--shadow-raised);
}

.crowding-cell {
  display: flex;
  gap: 10px;
  align-items: center;
  justify-content: flex-end;
}

.crowding-value {
  min-width: 52px;
  font-weight: 600;
  font-variant-numeric: tabular-nums;
  text-align: right;
}

.crowding-cell-bar {
  flex: 1;
  max-width: 120px;
}

.crowding-cell-track {
  position: relative;
  height: 8px;
  overflow: hidden;
  background: var(--border-default);
  border-radius: 4px;
}

.crowding-cell-fill {
  position: absolute;
  top: 0;
  left: 0;
  height: 100%;
  border-radius: 4px;
  transition: width 0.4s ease;
}

.crowding-cell-fill.val-low {
  background: var(--temp-low);
}

.crowding-cell-fill.val-mid {
  background: var(--temp-mid);
}

.crowding-cell-fill.val-high {
  background: var(--temp-high);
}

.crowding-note-tag {
  padding: 2px 8px;
  font-size: 11px;
  color: var(--text-tertiary);
  background: var(--bg-soft);
  border-radius: 6px;
}

.crowding-note {
  font-size: 12px;
  color: var(--text-tertiary);
}

/* 乖离率数值颜色 */
.bias-extreme-high,
.val-high {
  color: var(--temp-high);
}

.bias-high {
  color: color-mix(in srgb, var(--temp-high) 85%, var(--text-primary));
}

.bias-extreme-low,
.val-low {
  color: var(--temp-low);
}

.bias-low {
  color: color-mix(in srgb, var(--temp-low) 85%, var(--text-primary));
}

.bias-neutral,
.val-mid {
  color: var(--text-secondary);
}

/* ============================================================
   全部指标紧凑表格
   ============================================================ */
.metric-table {
  overflow: hidden;
  background: var(--bg-card);
  border: 1px solid var(--border-light);
  border-radius: 12px;
  box-shadow: var(--shadow-raised);
}

.metric-table-head,
.metric-table-row {
  display: grid;
  grid-template-columns: 2fr 1fr 100px 100px;
  gap: 12px;
  align-items: center;
  padding: 12px 16px;
}

.metric-table-head {
  font-size: 12px;
  font-weight: 600;
  color: var(--text-tertiary);
  text-transform: uppercase;
  letter-spacing: 0.04em;
  background: var(--bg-subtle);
}

.metric-table-row {
  font-size: 13px;
  border-top: 1px solid var(--border-light);
  transition: background 0.12s ease;
}

.metric-table-row:hover {
  background: var(--bg-subtle);
}

.metric-table-row.stale {
  opacity: 0.6;
}

.metric-table-row.stale .col-value {
  text-decoration: line-through;
}

.col-name {
  display: flex;
  gap: 6px;
  align-items: center;
  min-width: 0;
}

.metric-name-text {
  overflow: hidden;
  text-overflow: ellipsis;
  font-weight: 500;
  color: var(--text-primary);
  white-space: nowrap;
}

.info-icon {
  flex-shrink: 0;
  color: var(--text-tertiary);
  cursor: help;
}

.col-source {
  overflow: hidden;
  text-overflow: ellipsis;
  font-size: 12px;
  color: var(--text-secondary);
  white-space: nowrap;
}

.source-tag {
  display: inline-block;
  padding: 2px 8px;
  font-size: 11px;
  line-height: 1.4;
  color: var(--text-secondary);
  background: var(--bg-soft);
  border-radius: 6px;
}

.col-value {
  font-weight: 600;
  font-variant-numeric: tabular-nums;
  text-align: right;
}

.col-label {
  text-align: right;
}

/* ============================================================
   温度计页面样式
   ============================================================ */
</style>
